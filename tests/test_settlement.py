"""Tests for the three-way DNB settlement map (plan Phase 2 task 3; CALC §10).

Exercises the frozen settlement map (design.md §4; CALC §10):
  * underdog win in 90' -> o_DNB; 90-min draw -> push (refund); favourite win -> loss;
  * the 90-minute result governs, INCLUDING knockout matches decided by ET/penalties
    (a penalty-decided 1-1 is a push; ET/penalty goals never change settlement);
  * void/abandoned -> refund and EXCLUDED from the win-ratio denominator;
  * idempotent (re-settling reproduces identical dispositions/returns).

Built on the committed mini_league.csv fixture + a knockout 90-min-draw case.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from src import ingest, pricing, run, selection, settlement

FIXTURE = run.PROJECT_ROOT / "tests" / "fixtures" / "mini_league.csv"


def _fixture_panel(tmp_path) -> pd.DataFrame:
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


# --- scalar settlement map (CALC §10) ---------------------------------------


def test_underdog_win_pays_o_dnb():
    s = settlement.settle_one("A", "away", o_dnb=3.25)
    assert s.disposition == settlement.WIN
    assert s.gross_return == 3.25
    assert s.net_profit == 3.25 - 1.0
    assert s.counts_in_denominator is True


def test_ninety_minute_draw_is_push_refund():
    s = settlement.settle_one("D", "away", o_dnb=3.25)
    assert s.disposition == settlement.PUSH
    assert s.gross_return == 1.0  # stake refunded
    assert s.net_profit == 0.0


def test_favourite_win_is_full_loss():
    s = settlement.settle_one("H", "away", o_dnb=3.25)  # away underdog, home (fav) won
    assert s.disposition == settlement.LOSS
    assert s.gross_return == 0.0
    assert s.net_profit == -1.0


def test_home_underdog_win():
    s = settlement.settle_one("H", "home", o_dnb=2.10)
    assert s.disposition == settlement.WIN
    assert s.gross_return == 2.10


def test_void_refund_excluded_from_denominator():
    for bad in ("V", "ABD", "", None, np.nan, "X"):
        s = settlement.settle_one(bad, "away", o_dnb=3.25)
        assert s.disposition == settlement.VOID
        assert s.gross_return == 1.0  # refund
        assert s.net_profit == 0.0
        assert s.counts_in_denominator is False


def test_void_on_undefined_side_or_nonfinite_odds():
    assert settlement.settle_one("A", None, o_dnb=3.25).disposition == settlement.VOID
    assert settlement.settle_one("A", "away", o_dnb=float("nan")).disposition == settlement.VOID


# --- the knockout 90-min-draw case (the load-bearing CALC §10 rule) ---------


def test_knockout_penalty_decided_1_1_is_a_push_not_a_win_or_loss():
    """A knockout 1-1 after 90' decided on penalties settles as a DNB PUSH.

    The 90-minute result governs; ET/penalty progression is irrelevant. This is the
    exact case the slice brief requires: the 90' FTR is 'D' -> push, even though a winner
    advances after the shootout.
    """
    # 90-min FTR is 'D' regardless of who wins the shootout.
    s = settlement.settle_one("D", "away", o_dnb=2.80)
    assert s.disposition == settlement.PUSH
    assert s.gross_return == 1.0
    assert s.net_profit == 0.0


def test_et_penalty_metadata_never_changes_settlement():
    """settle() reads ONLY the 90' FTR; decided_in_et / penalty_shootout are ignored.

    Two knockout rows with identical 90' FTR='D' but different ET/penalty progression
    both settle as pushes -- proving an ET/penalty goal cannot change the disposition.
    """
    panel = pd.DataFrame(
        {
            "FTR": ["D", "D"],
            "sel_underdog_side": ["away", "home"],
            "o_dnb_underdog": [2.80, 3.10],
            "decided_in_et": [True, False],
            "penalty_shootout": [True, False],
        }
    )
    settled = settlement.settle(panel)
    assert (settled["settle_disposition"] == settlement.PUSH).all()
    assert (settled["settle_gross_return"] == 1.0).all()


# --- vectorized settle() over a panel ---------------------------------------


def test_settle_panel_dispositions_and_returns():
    panel = pd.DataFrame(
        {
            "FTR": ["A", "D", "H", "V"],
            "sel_underdog_side": ["away", "away", "away", "away"],
            "o_dnb_underdog": [3.25, 3.25, 3.25, 3.25],
        }
    )
    s = settlement.settle(panel)
    assert s["settle_disposition"].tolist() == [
        settlement.WIN,
        settlement.PUSH,
        settlement.LOSS,
        settlement.VOID,
    ]
    assert s["settle_gross_return"].tolist() == [3.25, 1.0, 0.0, 1.0]
    assert s["settle_net_profit"].tolist() == [2.25, 0.0, -1.0, 0.0]
    assert s["settle_in_denominator"].tolist() == [True, True, True, False]


def test_settle_is_idempotent():
    panel = pd.DataFrame(
        {
            "FTR": ["A", "D", "H", "V"],
            "sel_underdog_side": ["away", "home", "away", "away"],
            "o_dnb_underdog": [3.25, 2.10, 3.25, 3.25],
        }
    )
    once = settlement.settle(panel)
    twice = settlement.settle(once)  # re-settle the already-settled frame
    for c in ("settle_disposition", "settle_gross_return", "settle_net_profit"):
        assert once[c].tolist() == twice[c].tolist()


def test_win_ratio_excludes_void_keeps_push():
    panel = pd.DataFrame(
        {
            "FTR": ["A", "D", "H", "V"],  # win, push, loss, void
            "sel_underdog_side": ["away", "away", "away", "away"],
            "o_dnb_underdog": [3.25, 3.25, 3.25, 3.25],
        }
    )
    s = settlement.settle(panel)
    # denominator = win + push + loss = 3 (void excluded); wins = 1 -> 1/3.
    assert settlement.win_ratio(s) == 1.0 / 3.0


def test_win_ratio_nan_when_all_void():
    panel = pd.DataFrame(
        {"FTR": ["V", "V"], "sel_underdog_side": ["away", "away"], "o_dnb_underdog": [3.25, 3.25]}
    )
    assert np.isnan(settlement.win_ratio(settlement.settle(panel)))


# --- end-to-end on the mini_league fixture (selection -> settlement) --------


def test_end_to_end_fixture_selection_then_settlement(tmp_path):
    """select_underdog -> settle on the real fixture; dispositions agree with the 90' FTR."""
    panel = _fixture_panel(tmp_path)
    sel = selection.select_underdog(panel)
    settled = settlement.settle(sel)
    # Every eligible row has a real disposition (win/push/loss); none void (all priced).
    elig = settled[settled["eligible"]]
    assert elig["settle_disposition"].isin([settlement.WIN, settlement.PUSH, settlement.LOSS]).all()
    # Cross-check one draw row in the fixture (Fulham 2-2 Liverpool, FTR='D') -> push.
    draw_rows = settled[settled["FTR"] == "D"]
    assert (draw_rows["settle_disposition"] == settlement.PUSH).all()
    # And a winning-underdog row pays its synthetic o_dnb (Southampton 0-1 Man Utd: away
    # 'A', away is the dearer side -> underdog win at o_dnb_underdog).
    won = settled[settled["settle_disposition"] == settlement.WIN].iloc[0]
    expected = pricing.synthetic_dnb(won["sel_underdog_price"], won["refC_D"])
    assert abs(won["settle_gross_return"] - expected) < 1e-9
