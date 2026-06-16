"""Tests for the transaction-cost / execution model (Phase 3 task 9; ADR-0004).

Covers:
  * slippage calibration is a DATA quantile of the open->close move (never asserted);
  * the p50 robust-location default + the p90/p95/p99 stress ladder;
  * net_return: win re-priced at slippage/leg-out effective odds; push/loss/void
    unchanged; the one-tick-adverse leg-out stress shaves an extra tick;
  * the exchange-commission route takes c on net winnings;
  * commission_effective_overround + reconciliation vs the M_1X2 - M_AH wedge;
  * commission-rate selection within the DATA §2.3 [2%,5%] band (midpoint default).

The calibration block is supplied in-memory (a synthetic open_close_moves dict
mirroring the real data_quality structure) so the test does not depend on a freshly
run ingest stage; one test additionally reads the real newest data-quality report when
present, to prove the file path works.
"""

from __future__ import annotations

import json

import pytest
from src import costs

# A synthetic open_close_moves block mirroring src.ingest.open_close_moves output.
_OCM = {
    "n_observable": 1000,
    "n_buckets": 5,
    "pooled": {"mean_abs_move": 0.0657, "p50": 0.0523, "p90": 0.1296, "p95": 0.1630, "p99": 0.2470},
    "by_reference_regime": {
        "pinnacle_close": {"p50": 0.0528, "p90": 0.131, "p95": 0.164, "p99": 0.250},
    },
    "by_odds_bucket": {
        "bucket_0": {"p50": 0.0455, "p90": 0.107, "p95": 0.132, "p99": 0.188},
        "bucket_4": {"p50": 0.0676, "p90": 0.176, "p95": 0.221, "p99": 0.334},
    },
    # Underdog-price quantile edges that delimit the 5 buckets (ascending). A price in
    # [edges[i], edges[i+1]) resolves to bucket_i; the top bucket is right-closed.
    "odds_bucket_edges": [1.10, 1.80, 2.30, 3.00, 4.50, 30.0],
}


# ---------------------------------------------------------------------------
# (i) Slippage calibration.
# ---------------------------------------------------------------------------


def test_slippage_calibration_reads_data_quantile():
    """The slippage VALUE is read from the empirical distribution, not asserted."""
    cal = costs.calibrate_slippage(quantile_level="p50", open_close_moves=_OCM)
    assert cal.value == pytest.approx(0.0523)
    assert cal.quantile_level == "p50"
    assert cal.n_observable == 1000
    # The per-odds-bucket values at the selected level are carried (per-bucket apply).
    assert cal.by_odds_bucket["bucket_4"] == pytest.approx(0.0676)
    # The full stress ladder is reported.
    assert set(cal.ladder) == {"p50", "p90", "p95", "p99"}


def test_slippage_default_level_is_p50_robust_location():
    """The default operating level is p50 (the documented robust-location choice)."""
    cm = costs.from_config({"slippage_quantile": None}, open_close_moves=_OCM)
    assert cm.slippage.quantile_level == "p50"
    assert cm.slippage.value == pytest.approx(0.0523)


def test_slippage_tail_levels_are_larger():
    """Higher quantile levels carry larger slippage (the stress ladder is monotone)."""
    p50 = costs.calibrate_slippage(quantile_level="p50", open_close_moves=_OCM).value
    p99 = costs.calibrate_slippage(quantile_level="p99", open_close_moves=_OCM).value
    assert p99 > p50


def test_slippage_unknown_level_raises():
    with pytest.raises(ValueError, match="must be one of"):
        costs.calibrate_slippage(quantile_level="p42", open_close_moves=_OCM)


def test_slippage_reads_real_data_quality_report_when_present():
    """The file path works against the real newest data_quality_ingest report."""
    report = costs.latest_data_quality_report()
    if report is None:
        pytest.skip("no data_quality_ingest report on disk")
    block = json.loads(report.read_text(encoding="utf-8")).get("open_close_moves")
    if not block or "p50" not in (block.get("pooled") or {}):
        pytest.skip("real report has no open_close_moves.pooled.p50")
    cal = costs.calibrate_slippage(quantile_level="p50", data_quality_report=report)
    assert cal.value > 0.0
    assert cal.n_observable > 0


# ---------------------------------------------------------------------------
# net_return: win re-priced; push/loss unchanged; leg-out stress; commission.
# ---------------------------------------------------------------------------


def test_net_return_win_below_gross_book_route():
    """A win on the book route nets the slippage-shaved effective odds (< gross)."""
    cm = costs.from_config({"slippage_quantile": "p50"}, open_close_moves=_OCM)
    o = 2.857
    net = cm.net_return(o, o)  # gross win return == o
    assert net < o
    # Effective odds = o*(1-s): 2.857*(1-0.0523) = 2.7075.
    assert net == pytest.approx(o * (1.0 - 0.0523), abs=1e-6)


def test_net_return_push_and_loss_unchanged():
    """Push/void (gross 1.0) -> net 1.0; loss (gross 0.0) -> net 0.0 (no cost bite)."""
    cm = costs.from_config({"slippage_quantile": "p50"}, open_close_moves=_OCM)
    assert cm.net_return(2.857, 1.0) == 1.0
    assert cm.net_return(2.857, 0.0) == 0.0


def test_one_tick_adverse_legout_shaves_more():
    """The one-tick-adverse leg-out branch nets strictly less on a win than atomic fill."""
    atomic = costs.from_config(
        {"slippage_quantile": "p50"}, legout_model="atomic_two_leg_fill", open_close_moves=_OCM
    )
    stress = costs.from_config(
        {"slippage_quantile": "p50"},
        legout_model="one_tick_adverse",
        one_tick=0.01,
        open_close_moves=_OCM,
    )
    o = 2.857
    assert stress.net_return(o, o) < atomic.net_return(o, o)
    assert stress.net_return(o, o) == pytest.approx(atomic.net_return(o, o) - 0.01, abs=1e-9)


def test_exchange_route_applies_commission_on_net_winnings():
    """On the exchange route, commission takes c of the net winnings (o_eff - 1)."""
    book = costs.from_config({"slippage_quantile": "p50"}, route="book", open_close_moves=_OCM)
    exch = costs.from_config(
        {"slippage_quantile": "p50", "bfec_commission_rate": 0.05},
        route="exchange",
        open_close_moves=_OCM,
    )
    o = 2.857
    o_eff = float(book.effective_win_odds(o))
    expected = 1.0 + (1.0 - 0.05) * (o_eff - 1.0)
    assert exch.net_return(o, o) == pytest.approx(expected, abs=1e-9)
    assert exch.net_return(o, o) < book.net_return(o, o)  # commission deepens cost


# ---------------------------------------------------------------------------
# (iii) Commission as effective overround + reconciliation vs the wedge.
# ---------------------------------------------------------------------------


def test_commission_rate_band_and_default():
    """The commission rate is in the cited [2%,5%] band; unset -> midpoint 3.5%."""
    assert costs.select_commission_rate(None) == pytest.approx(0.035)
    assert costs.select_commission_rate(0.02) == 0.02
    with pytest.raises(ValueError, match="outside the cited"):
        costs.select_commission_rate(0.10)


def test_commission_effective_overround_nonnegative():
    """The commission's effective overround is >= 0 and rises with the rate."""
    m_low = costs.commission_effective_overround(2.857, 0.02)
    m_high = costs.commission_effective_overround(2.857, 0.05)
    assert 0.0 <= m_low < m_high


def test_commission_reconciles_with_phase1_wedge():
    """The exchange effective overround is reconciled vs the Phase-1 +0.80% wedge.

    At the documented BFEC rate band the effective overround on a typical DNB price is
    of the SAME ORDER as the synthetic-vs-quoted margin wedge (Phase-1 pooled mean
    +0.7985%) -- the reconciliation that puts the exchange route on the same footing
    as the quoted/synthetic route (CALC §3.5).
    """
    rec = costs.reconcile_commission_vs_wedge(2.857, None, 0.007985)
    assert rec.margin_wedge == pytest.approx(0.007985)
    assert rec.effective_overround > 0.0
    # Same order of magnitude as the wedge (the reconciliation is meaningful).
    assert abs(rec.gap_vs_wedge) < 0.02


# ---------------------------------------------------------------------------
# (i') Per-odds-bucket slippage is APPLIED, not just collected (ADR-0004; Phase-3 task 9).
# ---------------------------------------------------------------------------


def test_resolve_odds_bucket_maps_price_to_bucket_via_edges():
    """A bet's underdog price resolves to its bucket from the persisted quantile edges."""
    cal = costs.calibrate_slippage(quantile_level="p50", open_close_moves=_OCM)
    # edges = [1.10, 1.80, 2.30, 3.00, 4.50, 30.0]
    assert cal.resolve_odds_bucket(1.50) == "bucket_0"  # [1.10, 1.80)
    assert cal.resolve_odds_bucket(2.857) == "bucket_2"  # [2.30, 3.00)
    assert cal.resolve_odds_bucket(6.76) == "bucket_4"  # [4.50, 30.0]
    # Out-of-edges prices clamp to the nearest bucket, not None.
    assert cal.resolve_odds_bucket(1.01) == "bucket_0"
    assert cal.resolve_odds_bucket(99.0) == "bucket_4"


def test_slippage_for_bucket_uses_bucket_value_with_pooled_fallback():
    """The per-bucket value bites; an uncalibrated bucket falls back to pooled."""
    cal = costs.calibrate_slippage(quantile_level="p50", open_close_moves=_OCM)
    assert cal.slippage_for_bucket("bucket_4") == pytest.approx(0.0676)  # longshot
    assert cal.slippage_for_bucket("bucket_0") == pytest.approx(0.0455)
    # bucket_2 has no calibration entry in _OCM -> pooled fallback.
    assert cal.slippage_for_bucket("bucket_2") == pytest.approx(0.0523)
    assert cal.slippage_for_bucket(None) == pytest.approx(0.0523)


def test_net_return_applies_per_bucket_slippage_not_pooled():
    """A longshot's larger bucket slippage shaves more than the pooled value (the fix)."""
    cm = costs.from_config({"slippage_quantile": "p50"}, open_close_moves=_OCM)
    o = 6.76  # resolves to bucket_4 (p50 = 0.0676 > pooled 0.0523)
    net_bucket = cm.net_return(o, o)  # bucket resolved from o
    net_pooled = cm.net_return(o, o, slippage_value=_OCM["pooled"]["p50"])  # forced pooled
    # bucket_4 slippage (6.76%) is larger than pooled (5.23%) -> a strictly deeper shave.
    assert net_bucket < net_pooled
    assert net_bucket == pytest.approx(o * (1.0 - 0.0676), abs=1e-9)
    # An explicit odds_bucket label overrides the price-based resolution.
    assert cm.net_return(o, o, odds_bucket="bucket_0") == pytest.approx(
        o * (1.0 - 0.0455), abs=1e-9
    )


def test_push_carries_draw_leg_slippage_only_under_legout_stress():
    """Atomic fill -> push refunds 1.0; one-tick-adverse -> push shaved by draw-leg slippage."""
    atomic = costs.from_config(
        {"slippage_quantile": "p50"}, legout_model="atomic_two_leg_fill", open_close_moves=_OCM
    )
    stress = costs.from_config(
        {"slippage_quantile": "p50"}, legout_model="one_tick_adverse", open_close_moves=_OCM
    )
    o = 6.76  # bucket_4, slippage 0.0676
    # Atomic-fill idealization: push refunds exactly the stake.
    assert atomic.net_return(o, 1.0) == 1.0
    # Leg-out stress: the 1/D draw stake refunds < 1 (draw-leg fills adversely) -> 1 - s.
    assert stress.net_return(o, 1.0) == pytest.approx(1.0 - 0.0676, abs=1e-9)
    assert stress.net_return(o, 1.0) < 1.0
    # Loss is still 0 under both branches (full stake lost regardless of cost).
    assert atomic.net_return(o, 0.0) == 0.0
    assert stress.net_return(o, 0.0) == 0.0
