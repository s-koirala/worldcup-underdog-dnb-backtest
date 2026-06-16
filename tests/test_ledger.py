"""Tests for the chronological PnL ledger (Phase 3 task 2; ARCH §2.2).

Covers the two load-bearing invariants:
  * CONSERVATION: equity_t = equity_0 + sum(pnl_{<=t}) on BOTH gross and net columns;
  * NON-ANTICIPATION: permuting FUTURE settled results never changes an earlier stake
    (the ledger sizes from the running bankroll BEFORE settling each bet);

plus:
  * every entry carries BOTH gross and net PnL; net <= gross on wins (costs bite);
  * the negative-edge Kelly pass records zero-stake "do not bet" entries and a flat
    equity path (the honest-prior all-negative-edge case; slice brief / STAKE §7.3);
  * gross-only mode (no cost model) sets net == gross, explicitly;
  * the real league panel passes conservation under a fixed-fraction pass with costs.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from src import costs, ledger, settlement

_OCM = {
    "n_observable": 1000,
    "pooled": {"p50": 0.0523, "p90": 0.1296, "p95": 0.1630, "p99": 0.2470},
    "by_odds_bucket": {},
}


def _toy_bets(
    results: list[str],
    *,
    o_dnb: list[float] | None = None,
    p_win: list[float] | None = None,
    p_draw: list[float] | None = None,
) -> pd.DataFrame:
    """A tiny settled bet table: away-underdog DNB, per-row-varying signal + 90-min results.

    Builds the (p_win, p_draw, o_dnb_underdog, settle_*) columns the ledger consumes.
    The signal defaults are a CONSTANT positive-edge cell (back-compat for the
    conservation tests), but the per-row ``o_dnb``/``p_win``/``p_draw`` overrides let the
    non-anticipation test build a NON-DEGENERATE panel (each bet a distinct stake) so the
    permutation property is not satisfied trivially by identical inputs.
    """
    n = len(results)
    df = pd.DataFrame(
        {
            "date": [f"{(i % 28) + 1:02d}/01/2020" for i in range(n)],
            "match_id": [f"m{i:03d}" for i in range(n)],
            "underdog_side": ["away"] * n,
            "o_dnb_underdog": list(o_dnb) if o_dnb is not None else [2.857] * n,
            # positive-edge (p_win*o_dnb conditional > 1) so Kelly stakes
            "p_win": list(p_win) if p_win is not None else [0.40] * n,
            "p_draw": list(p_draw) if p_draw is not None else [0.28] * n,
            "FTR": results,
        }
    )
    return settlement.settle(df, side_col="underdog_side", odds_col="o_dnb_underdog")


# ---------------------------------------------------------------------------
# Conservation.
# ---------------------------------------------------------------------------


def test_conservation_gross_and_net():
    """equity_t = equity_0 + sum(pnl_{<=t}) on both gross and net (ARCH §2.2)."""
    bets = _toy_bets(["A", "H", "D", "A", "H", "D", "A", "A"])
    cm = costs.from_config({"slippage_quantile": "p50"}, open_close_moves=_OCM)
    r = ledger.build_ledger(
        bets, scheme="fixed_fraction", scheme_params={"phi": 0.05}, cost_model=cm
    )
    assert ledger.check_conservation(r) is True
    # Spot-check the identity directly.
    led = r.ledger
    assert led["net_bankroll_after"].iloc[-1] == pytest.approx(
        r.initial_bankroll + led["net_pnl"].sum()
    )
    assert led["gross_bankroll_after"].iloc[-1] == pytest.approx(
        r.initial_bankroll + led["gross_pnl"].sum()
    )


def test_every_entry_has_gross_and_net_pnl():
    """Each ledger row carries both gross and net PnL; net <= gross on wins (costs)."""
    bets = _toy_bets(["A", "A", "D", "H"])
    cm = costs.from_config({"slippage_quantile": "p50"}, open_close_moves=_OCM)
    r = ledger.build_ledger(
        bets, scheme="fixed_fraction", scheme_params={"phi": 0.05}, cost_model=cm
    )
    led = r.ledger
    assert {"gross_pnl", "net_pnl", "gross_return", "net_return"} <= set(led.columns)
    win_rows = led[led["settle_disposition"] == settlement.WIN]
    assert (win_rows["net_pnl"] <= win_rows["gross_pnl"] + 1e-12).all()  # costs bite on wins
    # Push rows net exactly 0 PnL (stake refunded).
    push_rows = led[led["settle_disposition"] == settlement.PUSH]
    assert (push_rows["net_pnl"].abs() < 1e-12).all()
    assert (push_rows["gross_pnl"].abs() < 1e-12).all()


def test_gross_only_mode_sets_net_equal_gross():
    """With no cost model, net == gross (an explicitly gross-only ledger; ADR-0004)."""
    bets = _toy_bets(["A", "D", "H", "A"])
    r = ledger.build_ledger(bets, scheme="fixed_fraction", scheme_params={"phi": 0.05})
    led = r.ledger
    placed = led[led["stake"] > 0.0]
    assert np.allclose(placed["net_pnl"], placed["gross_pnl"])
    assert r.final_net_bankroll == pytest.approx(r.final_gross_bankroll)


# ---------------------------------------------------------------------------
# Honest-prior: all-negative-edge Kelly -> zero-stake "do not bet" entries.
# ---------------------------------------------------------------------------


def test_negative_edge_kelly_records_zero_stake_entries():
    """All-negative-edge Kelly stakes 0 on every bet -> flat equity, recorded (not empty)."""
    # CALC §8.2 negative-EV cell: p_W=0.2105, p_D=0.2632 at o=3.25 -> f*=0.
    n = 6
    df = pd.DataFrame(
        {
            "date": [f"{i + 1:02d}/01/2020" for i in range(n)],
            "match_id": [f"m{i}" for i in range(n)],
            "underdog_side": ["away"] * n,
            "o_dnb_underdog": [3.25] * n,
            "p_win": [0.2105] * n,
            "p_draw": [0.2632] * n,
            "FTR": ["A", "H", "D", "A", "H", "A"],
        }
    )
    df = settlement.settle(df, side_col="underdog_side", odds_col="o_dnb_underdog")
    cm = costs.from_config({"slippage_quantile": "p50"}, open_close_moves=_OCM)
    r = ledger.build_ledger(df, scheme="kelly", cost_model=cm)
    assert r.n_bets == n  # every bet is RECORDED (not dropped)
    assert r.n_staked == 0  # but staked 0 (do not bet)
    assert r.final_net_bankroll == pytest.approx(r.initial_bankroll)  # flat equity
    assert ledger.check_conservation(r) is True


# ---------------------------------------------------------------------------
# Non-anticipation: permuting future results never changes an earlier stake.
# ---------------------------------------------------------------------------


def test_non_anticipation_permuting_future_results_preserves_stakes():
    """Stake_t is invariant to ANY reordering of results at positions > t (STAT §9.2).

    The strong non-anticipation property the module docstring claims is "permuting
    FUTURE results never changes an earlier stake". The degenerate panel (constant
    o_dnb/p_win/p_draw, distinct ascending dates) makes any shared prefix trivially
    identical for reasons unrelated to non-anticipation -- it cannot catch a stake that
    reads its OWN result (a lag-0 leak) or a forward leak. This test instead:

      * uses a NON-DEGENERATE panel (o_dnb, p_win, p_draw vary per row, so the per-bet
        stake is a distinct function of the signal -- a leak would actually move it);
      * permutes the FULL result vector via a TRUE permutation of the same outcome
        multiset restricted to positions > t (the 0..t-1 prefix held fixed), and asserts
        ``stake_t`` is unchanged against a reference ledger -- for EVERY bet t.

    A lag-0 leak (stake_t reading FTR_t) or a forward leak (stake_t reading FTR_{>t})
    would change stake_t under the permutation; the identical-prefix construction the
    prior test used could not detect either.
    """
    rng = np.random.default_rng(20260616)
    n = 8
    # NON-DEGENERATE signal: distinct price / probabilities per bet (positive-edge cells,
    # so Kelly stakes a strictly bet-specific, non-trivial fraction on each).
    o_dnb = list(rng.uniform(2.4, 4.0, n))
    p_win = list(rng.uniform(0.38, 0.46, n))
    p_draw = list(rng.uniform(0.22, 0.30, n))
    base_results = list(rng.choice(["A", "H", "D"], size=n))
    cm = costs.from_config({"slippage_quantile": "p50"}, open_close_moves=_OCM)

    def _stakes(results: list[str]) -> np.ndarray:
        r = ledger.build_ledger(
            _toy_bets(results, o_dnb=o_dnb, p_win=p_win, p_draw=p_draw),
            scheme="fractional_kelly",
            scheme_params={"lam": 0.5},
            cost_model=cm,
        )
        return r.ledger["stake"].to_numpy()

    reference = _stakes(base_results)
    # For every bet t, build a results vector that is IDENTICAL on 0..t-1 but is a true
    # permutation of the SAME outcome multiset on positions >= t (so FTR_t itself may
    # change), and assert stake_t is unchanged. Sweeping t over all bets exercises the
    # lag-0 leak (t's own result) and every forward leak.
    for t in range(n):
        suffix = base_results[t:]
        # Reorder the >= t block until FTR_t actually differs (when the multiset allows),
        # so the lag-0 channel is genuinely probed, not coincidentally identical.
        perm_suffix = suffix[:]
        for _ in range(20):
            perm_suffix = list(rng.permutation(suffix))
            if len(set(suffix)) == 1 or perm_suffix[0] != suffix[0]:
                break
        permuted = base_results[:t] + perm_suffix
        s = _stakes(permuted)
        # The 0..t prefix stakes (including stake_t) must match the reference exactly:
        # stake_t saw only the settled outcomes of bets < t (the prefix is identical),
        # never its own (position t) or any later (> t) permuted result.
        assert np.allclose(s[: t + 1], reference[: t + 1]), (
            f"stake_0..{t} changed when results at positions >= {t} were permuted "
            "(non-anticipation violated: a stake read its own or a future result)"
        )


# ---------------------------------------------------------------------------
# Real league panel integration.
# ---------------------------------------------------------------------------


def test_real_league_panel_conserves_under_fixed_fraction():
    """The full league panel passes conservation under a fixed-fraction pass with costs."""
    from src import run as run_mod

    matches = run_mod.PROJECT_ROOT / "data" / "processed" / "matches.parquet"
    if not matches.exists():
        pytest.skip("canonical matches.parquet not materialised")
    panel = pd.read_parquet(matches)
    bets = ledger.prepare_settled_bets(panel, devig_method="shin", block="league")
    assert len(bets) > 1000  # the estimation universe reaches the 10^3-10^4 scale
    cm = costs.from_config({"slippage_quantile": "p50"})
    r = ledger.build_ledger(
        bets.head(2000), scheme="fixed_fraction", scheme_params={"phi": 0.01}, cost_model=cm
    )
    assert ledger.check_conservation(r) is True
    # Net growth is strictly below gross (costs bite on the negative-EV strategy).
    s = ledger.ledger_summary(r)
    assert s["net_growth_multiple"] <= s["gross_growth_multiple"]


def test_real_league_panel_kelly_is_all_do_not_bet():
    """Honest prior on the real panel: full Kelly stakes 0 everywhere (no positive-EV cell)."""
    from src import run as run_mod

    matches = run_mod.PROJECT_ROOT / "data" / "processed" / "matches.parquet"
    if not matches.exists():
        pytest.skip("canonical matches.parquet not materialised")
    panel = pd.read_parquet(matches)
    bets = ledger.prepare_settled_bets(panel, devig_method="shin", block="league")
    cm = costs.from_config({"slippage_quantile": "p50"})
    r = ledger.build_ledger(bets, scheme="kelly", cost_model=cm)
    assert r.n_staked == 0  # the all-negative-edge honest-prior verdict (slice brief)
    assert ledger.check_conservation(r) is True
