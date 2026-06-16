"""Tests for the DATA §8 validate gates + draw-rate base rates (plan Phase 1 tasks 6, 7).

The load-bearing test is the EMPIRICAL-QUANTILE gate behaviour: the draw-leg (and
overround) gates must fit their cut-points per division-season x reference regime
from the realized distribution -- NOT a hard-coded band. A fixed [2.6, 5.5] draw-odds
window rejects 6-15% of the strong-favourite matches the strategy targets (DATA §8
gate 4); the empirical-quantile gate must KEEP those high-draw-odds rows.

In-memory fixtures (no network).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from src import validate


def _panel_with_draw_odds(refc_d_values, *, season=2324, ref_book="pinnacle_close", comp="E0"):
    """Canonical-ish panel with controlled refC_D (and matching refC_H/refC_A)."""
    n = len(refc_d_values)
    rng = np.random.default_rng(0)
    return pd.DataFrame(
        {
            "block": ["league"] * n,
            "competition": [comp] * n,
            "season": [str(season)] * n,
            "date": [f"2024-01-{i % 28 + 1:02d}" for i in range(n)],
            "home_team": [f"H{i}" for i in range(n)],
            "away_team": [f"A{i}" for i in range(n)],
            "match_id": [f"{comp}_{season}_{i}" for i in range(n)],
            "FTHG": rng.integers(0, 4, n).astype(float),
            "FTAG": rng.integers(0, 4, n).astype(float),
            "FTR": ["H"] * n,
            "is_push": [False] * n,
            "refC_H": [1.5] * n,
            "refC_D": list(refc_d_values),
            "refC_A": [7.0] * n,
            "ref_book": [ref_book] * n,
            "overround": [1.05] * n,
            "underdog_side": ["away"] * n,
            "o_dnb_underdog": [3.0] * n,
            "odds_status": ["available"] * n,
            "quoted_ah_line": [np.nan] * n,
            "quoted_ah_home": [np.nan] * n,
            "quoted_ah_away": [np.nan] * n,
            "qual_state_home": [pd.NA] * n,
            "qual_state_away": [pd.NA] * n,
            "dead_rubber": [False] * n,
        }
    )


def test_draw_leg_gate_keeps_high_draw_odds_strong_favourite_matches():
    """A strong-favourite cluster of HIGH draw odds (6-12, the strategy's target
    region) must NOT be flagged by the empirical-quantile gate -- only the extreme
    tails are. A fixed [2.6,5.5] band would reject all the >5.5 rows."""
    # 96 typical draw odds (3.0-5.0) + 4 high strong-favourite draw odds (7-12).
    typical = list(np.linspace(3.0, 5.0, 96))
    high = [7.0, 8.5, 10.0, 12.0]
    panel = _panel_with_draw_odds(typical + high)
    out = validate.gate_draw_leg(panel, tail_low=0.001, tail_high=0.999)
    # The empirical-quantile gate flags ONLY the extreme tails (the single most
    # extreme low and/or high value at the 0.1/99.9 percentiles), NOT the whole >5.5
    # cluster a fixed [2.6,5.5] band would reject (it would flag all 4 high rows).
    n_high = sum(1 for v in (typical + high) if v > 5.5)
    assert n_high == 4  # a fixed 5.5 band would reject all 4
    assert out["n_flagged_total"] <= 2  # only extreme tails (<= one per tail)
    # The high strong-favourite draw odds (>5.5) are overwhelmingly KEPT, not rejected.
    assert out["n_flagged_total"] < n_high
    # Cut-points are fitted from the data (the high tail is reflected), not [2.6,5.5].
    grp = next(iter(out["per_group"].values()))
    assert grp["cut_high"] > 5.5  # the empirical upper cut exceeds the discredited 5.5
    assert out["no_hardcoded_band"] is True


def test_gate_fits_cutpoints_per_division_season_x_reference_regime():
    """The gate fits SEPARATE cut-points per (competition, season, ref_book) group;
    a Pinnacle group and a consensus group get distinct cuts (DATA §8 gate 4)."""
    p_pin = _panel_with_draw_odds(
        np.linspace(3.0, 5.0, 50), season=2425, ref_book="pinnacle_close", comp="E0"
    )
    p_avg = _panel_with_draw_odds(
        np.linspace(4.0, 9.0, 50), season=2526, ref_book="market_avg_close", comp="E0"
    )
    panel = pd.concat([p_pin, p_avg], ignore_index=True)
    out = validate.gate_draw_leg(panel, tail_low=0.001, tail_high=0.999)
    groups = out["per_group"]
    # Two distinct regime groups, each with its own fitted cut-points.
    assert len(groups) == 2
    cuts = {gid: g["cut_high"] for gid, g in groups.items()}
    # the consensus (avg) regime has the higher draw-odds spread -> a higher cut.
    avg_key = next(k for k in cuts if "market_avg_close" in k)
    pin_key = next(k for k in cuts if "pinnacle_close" in k)
    assert cuts[avg_key] > cuts[pin_key]


def test_settlement_consistency_flags_a_real_mismatch():
    panel = _panel_with_draw_odds(np.linspace(3.0, 5.0, 3))
    # Force a genuine FTR-vs-score mismatch on the first row.
    panel.loc[0, "FTHG"] = 0.0
    panel.loc[0, "FTAG"] = 2.0
    panel.loc[0, "FTR"] = "H"  # but away won 0-2 -> should be 'A'
    out = validate.gate_settlement_consistency(panel)
    assert out["n_mismatch"] >= 1


def test_missingness_separates_wc_pending_from_league_drop():
    """WC odds_status='pending' rows are NOT counted as a missingness finding; only
    genuinely-missing league refC legs are (DATA §8 gate 1)."""
    league = _panel_with_draw_odds(np.linspace(3.0, 5.0, 4))
    league.loc[0, "refC_D"] = np.nan  # one genuine missing league leg
    wc = _panel_with_draw_odds(np.linspace(3.0, 5.0, 2))
    wc["block"] = "wc"
    wc["odds_status"] = "pending"
    wc[["refC_H", "refC_D", "refC_A"]] = np.nan
    panel = pd.concat([league, wc], ignore_index=True)
    out = validate.gate_missingness(panel)
    assert out["n_settleable_rows"] == 4  # WC pending excluded
    assert out["n_missing_refC"] == 1  # only the genuine league null
    assert out["wc_odds_pending_rows"] == 2


def test_draw_rate_base_rates_record_modern_wc_q():
    """The modern WC 90-min draw rate q is recorded from the assembled is_push."""
    wc = pd.DataFrame(
        {
            "block": ["wc"] * 4,
            "competition": ["WC2018"] * 4,
            "season": ["2018"] * 4,
            "is_push": [True, False, True, False],
            "decided_in_et": [False, False, True, False],
            "qual_state_home": ["live", "live", "knockout", "knockout"],
            "qual_state_away": ["live", "live", "knockout", "knockout"],
            "dead_rubber": [False, False, False, False],
        }
    )
    out = validate.draw_rate_base_rates(wc, mj_results=None)
    assert out["modern_wc_90min_draw_rate_q"] == 0.5  # 2/4
    assert out["wc_group_stage_90min"]["n"] == 2
    assert out["wc_knockout_90min"]["n"] == 2
    # UCL recorded as an honest gap (not in football-data), never fabricated.
    assert out["ucl_90min"]["rate"] is None
