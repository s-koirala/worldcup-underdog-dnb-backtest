"""Tests for underdog labelling + eligibility selection (plan Phase 2 task 2; CALC §2).

Exercises the frozen design (design.md §3, config/baseline.yaml `selection`):
  * underdog = argmax(refC_H, refC_A) (= min implied win prob), tie-break -> away,
    matching src.ingest bit-for-bit;
  * the SWEPT coin-flip exclusion band (min_price_gap / tau_tie) -- None pre-sweep so no
    near-tie exclusion; require_strict_underdog is the rejected branch (False in config);
  * eligibility filters (both 1X2 present, draw price present, liquidity proxy) with a
    recorded reason and NO silent drops;
  * tau (underdog STRENGTH) is NOT asserted here (selected out-of-fold in Phase 4).

Built on the committed mini_league.csv fixture via the real ingest path.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from src import ingest, run, selection

FIXTURE = run.PROJECT_ROOT / "tests" / "fixtures" / "mini_league.csv"


def _fixture_panel(tmp_path) -> pd.DataFrame:
    """The mini_league fixture through the real ingest refC/underdog derivation."""
    raw = tmp_path / "2223_E0.csv"
    ingest.write_with_sha256(raw, FIXTURE.read_bytes())
    cfg = run.load_config(run.PROJECT_ROOT / "config" / "baseline.yaml")["ingest"]
    ah = cfg["quoted_ah_pinnacle_close"]
    vf = ingest.validate_file(
        raw, season=2223, division="E0", ah_home=ah["home"], ah_away=ah["away"], ah_line=ah["line"]
    )
    vf = ingest.attach_reference_price(
        vf,
        cutover_season=cfg["reference_cutover_season"],
        reference_columns=cfg["reference_columns"],
        ah_home=ah["home"],
        ah_away=ah["away"],
        ah_line=ah["line"],
    )
    return vf.df


# --- underdog side / price (CALC §2.1; tie-break consistency with src.ingest) ----


def test_underdog_side_is_argmax_win_price():
    """Underdog = the side with the HIGHER decimal win price (lower implied prob)."""
    h = pd.Series([2.95, 1.80, 1.45])
    a = pd.Series([2.55, 4.50, 7.20])
    side = selection.underdog_side(h, a)
    # row0: H=2.95 > A=2.55 -> home; row1,2: away dearer -> away.
    assert list(side) == ["home", "away", "away"]


def test_underdog_side_tiebreak_matches_ingest_away_on_exact_tie():
    """Exact win-price ties resolve to 'away' (refC_A >= refC_H), as src.ingest does."""
    side = selection.underdog_side(pd.Series([2.50]), pd.Series([2.50]))
    assert side.iloc[0] == "away"


def test_underdog_min_implied_prob_equivalence():
    """'higher decimal odds' and 'lower implied win prob 1/o' are the SAME ordering."""
    h, a = pd.Series([3.00, 1.50]), pd.Series([2.00, 6.00])
    side = selection.underdog_side(h, a)
    price = selection.underdog_win_price(h, a)
    for i in range(len(h)):
        # the chosen side has the lower raw implied prob (= higher price).
        r_h, r_a = 1 / h.iloc[i], 1 / a.iloc[i]
        chosen_r = 1 / price.iloc[i]
        assert chosen_r == pytest.approx(min(r_h, r_a))
        assert side.iloc[i] == ("away" if a.iloc[i] >= h.iloc[i] else "home")


def test_underdog_side_na_when_price_missing():
    """Underdog side is <NA> (undefined, not guessed) when a win price is missing."""
    side = selection.underdog_side(pd.Series([np.nan, 2.0]), pd.Series([3.0, np.nan]))
    assert side.isna().all()


def test_win_price_gap_and_favourite_price():
    h, a = pd.Series([2.95, 1.80]), pd.Series([2.55, 4.50])
    assert selection.win_price_gap(h, a).tolist() == pytest.approx([0.40, 2.70])
    assert selection.favourite_win_price(h, a).tolist() == pytest.approx([2.55, 1.80])


def test_selection_consistent_with_ingest_underdog_side_on_fixture(tmp_path):
    """select_underdog's side label matches src.ingest's underdog_side on the fixture."""
    panel = _fixture_panel(tmp_path)
    sel = selection.select_underdog(panel)
    same = sel["sel_underdog_side"].astype("string") == panel["underdog_side"].astype("string")
    assert same.all()


# --- near-tie band (the frozen swept branch) --------------------------------


def test_no_near_tie_exclusion_pre_sweep():
    """min_price_gap=None (pre-Phase-4-sweep) -> no near-tie exclusion; all priced rows eligible."""
    panel = pd.DataFrame(
        {
            "refC_H": [2.00, 2.01],
            "refC_D": [3.40, 3.40],
            "refC_A": [2.02, 4.00],
            "ref_book": ["pinnacle_close", "pinnacle_close"],
        }
    )
    sel = selection.select_underdog(panel, selection.SelectionConfig(min_price_gap=None))
    assert sel["eligible"].all()


def test_swept_min_price_gap_excludes_coin_flips():
    """A resolved tau_tie band excludes near-coin-flip matches (|gap| < band)."""
    panel = pd.DataFrame(
        {
            "refC_H": [2.00, 2.00],
            "refC_D": [3.40, 3.40],
            "refC_A": [2.05, 4.00],  # gap 0.05 (coin-flip) vs 2.00 (clear underdog)
            "ref_book": ["pinnacle_close", "pinnacle_close"],
        }
    )
    sel = selection.select_underdog(panel, selection.SelectionConfig(min_price_gap=0.50))
    assert not bool(sel.loc[0, "eligible"])
    assert sel.loc[0, "ineligible_reason"] == selection.REASON_NEAR_TIE
    assert bool(sel.loc[1, "eligible"])


def test_strict_tie_branch_excludes_only_exact_ties():
    """The rejected require_strict_underdog branch drops exact ties only (gap == 0)."""
    panel = pd.DataFrame(
        {
            "refC_H": [2.50, 2.50],
            "refC_D": [3.40, 3.40],
            "refC_A": [2.50, 2.55],  # exact tie vs a 0.05 near-tie
            "ref_book": ["pinnacle_close", "pinnacle_close"],
        }
    )
    sel = selection.select_underdog(panel, selection.SelectionConfig(require_strict_underdog=True))
    assert not bool(sel.loc[0, "eligible"])  # exact tie excluded
    assert bool(sel.loc[1, "eligible"])  # 0.05 near-tie kept (strict branch is exact-only)


def test_selection_config_from_baseline_yaml_is_the_swept_branch():
    """The FROZEN config: require_strict_underdog False, min_price_gap null (swept band)."""
    cfg = run.load_config(run.PROJECT_ROOT / "config" / "baseline.yaml")
    sc = selection.SelectionConfig.from_config(cfg)
    assert sc.require_strict_underdog is False
    assert sc.min_price_gap is None  # null until the Phase-4 sweep resolves tau_tie


# --- eligibility filters + no silent drops ----------------------------------


def test_eligibility_filters_with_recorded_reasons_no_silent_drops():
    panel = pd.DataFrame(
        {
            "refC_H": [2.00, np.nan, 2.00, 2.00],
            "refC_D": [3.40, 3.40, np.nan, 3.40],
            "refC_A": [4.00, 4.00, 4.00, 4.00],
            "ref_book": ["pinnacle_close", "pinnacle_close", "pinnacle_close", "none_available"],
        }
    )
    sel = selection.select_underdog(panel)
    # No rows dropped: every input row is present in the output.
    assert len(sel) == len(panel)
    assert bool(sel.loc[0, "eligible"]) is True
    assert sel.loc[1, "ineligible_reason"] == selection.REASON_MISSING_WIN_PRICE
    assert sel.loc[2, "ineligible_reason"] == selection.REASON_MISSING_DRAW_PRICE
    assert sel.loc[3, "ineligible_reason"] == selection.REASON_NO_REFERENCE_BOOK


def test_pending_wc_rows_are_ineligible_no_reference():
    """WC odds-gap rows (odds_status='pending', ref_book='none_available') are ineligible."""
    panel = pd.DataFrame(
        {
            "refC_H": [np.nan],
            "refC_D": [np.nan],
            "refC_A": [np.nan],
            "ref_book": ["none_available"],
            "odds_status": ["pending"],
        }
    )
    sel = selection.select_underdog(panel)
    assert not bool(sel.loc[0, "eligible"])


def test_fixture_eligible_rows_have_underdog_and_price(tmp_path):
    """On the mini_league fixture every eligible row carries a side + a finite price."""
    panel = _fixture_panel(tmp_path)
    sel = selection.select_underdog(panel)
    elig = sel[sel["eligible"]]
    assert len(elig) > 0
    assert elig["sel_underdog_side"].isin(["home", "away"]).all()
    assert np.isfinite(elig["sel_underdog_price"].to_numpy(dtype="float64")).all()
