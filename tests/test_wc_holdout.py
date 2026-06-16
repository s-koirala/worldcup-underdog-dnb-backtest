"""Tests for the World-Cup hold-out settlement panel (plan Phase 1 tasks 4, 5, 10).

Covers the load-bearing acceptance criteria:
  * 90-minute FTR reconstruction excludes extra-time goals (CALC §10);
  * a penalty-decided level match settles as a DNB PUSH (task 5; DATA OQ 4);
  * an ET-decided non-penalty match that was level at 90 settles as a push;
  * the alias-crosswalk historical-name bridge (Serbia and Montenegro);
  * tiebreak-safe group qualification-state arithmetic (task 7.1);
  * CLV / synthetic-only tagging (task 10).

These use small in-memory fixtures (no network); the network build is exercised
by the build script itself and the committed provenance sidecars.
"""

from __future__ import annotations

import pandas as pd
from src import wc_holdout


def _match_row(match_id, home_id, away_id, hs, as_, et=0, pen=0, stage="quarter-finals"):
    """Minimal jfjelstul-shaped match row."""
    return {
        "match_id": match_id,
        "home_team_id": home_id,
        "away_team_id": away_id,
        "home_team_name": home_id,
        "away_team_name": away_id,
        "home_team_score": hs,
        "away_team_score": as_,
        "extra_time": et,
        "penalty_shootout": pen,
        "stage_name": stage,
        "group_stage": 0 if "group" not in stage else 1,
        "knockout_stage": 0 if "group" in stage else 1,
        "group_name": "not applicable",
        "match_date": "2018-07-01",
    }


def _goal(match_id, side, period):
    """Minimal jfjelstul goals row: side in {'home','away'}, with match_period."""
    return {
        "match_id": match_id,
        "home_team": 1 if side == "home" else 0,
        "away_team": 1 if side == "away" else 0,
        "match_period": period,
    }


def test_90min_excludes_extra_time_goals():
    """A goal scored in extra time must NOT count toward the 90-minute score."""
    matches = pd.DataFrame([_match_row("M1", "A", "B", hs=1, as_=0, et=1)])
    # One goal, scored in extra time -> 90-min score is 0-0.
    goals = pd.DataFrame([_goal("M1", "home", "extra time, second half")])
    out = wc_holdout.reconstruct_90min_scores(matches, goals)
    assert out.loc[0, "fthg_90"] == 0
    assert out.loc[0, "ftag_90"] == 0
    assert out.loc[0, "ftr_90"] == "D"
    assert bool(out.loc[0, "is_push_90"]) is True
    # full result was 1-0 (H) but 90-min was a draw -> ET changed the outcome.
    assert bool(out.loc[0, "decided_in_et"]) is True


def test_penalty_decided_level_match_is_dnb_push():
    """A penalty-decided knockout level at 90 minutes settles as a DNB push
    regardless of the shootout winner (plan task 5; CALC §10)."""
    matches = pd.DataFrame([_match_row("M2", "ITA", "FRA", hs=1, as_=1, et=1, pen=1)])
    goals = pd.DataFrame(
        [
            _goal("M2", "home", "first half"),  # 1 regulation goal each
            _goal("M2", "away", "second half"),
        ]
    )
    out = wc_holdout.reconstruct_90min_scores(matches, goals)
    assert out.loc[0, "fthg_90"] == 1
    assert out.loc[0, "ftag_90"] == 1
    assert out.loc[0, "ftr_90"] == "D"
    assert bool(out.loc[0, "is_push_90"]) is True
    # level at 90 already a draw in the full result -> not an ET-changed outcome.
    assert bool(out.loc[0, "decided_in_et"]) is False


def test_regulation_goals_decide_normally():
    """A match decided in regulation keeps its 90-minute result."""
    matches = pd.DataFrame([_match_row("M3", "A", "B", hs=2, as_=1, stage="group stage")])
    goals = pd.DataFrame(
        [
            _goal("M3", "home", "first half"),
            _goal("M3", "home", "second half, stoppage time"),
            _goal("M3", "away", "second half"),
        ]
    )
    out = wc_holdout.reconstruct_90min_scores(matches, goals)
    assert (out.loc[0, "fthg_90"], out.loc[0, "ftag_90"]) == (2, 1)
    assert out.loc[0, "ftr_90"] == "H"
    assert bool(out.loc[0, "is_push_90"]) is False


def test_manual_alias_bridges_serbia_montenegro():
    """The reviewed historical-name alias maps 'Serbia' -> 'Serbia and Montenegro'."""
    assert wc_holdout._norm("Serbia") == "serbia and montenegro"
    assert wc_holdout._norm("Serbia and Montenegro") == "serbia and montenegro"


def test_order_insensitive_settlement_reconciliation():
    """Settlement reconciles even when the two sources swap home/away order."""
    panel = pd.DataFrame(
        [
            {
                "match_date": "2018-06-25",
                "home_team_name": "Spain",
                "away_team_name": "Russia",
                "home_team_score": 2,
                "away_team_score": 2,
            }
        ]
    )
    # martj42 lists Russia (host) as home, with the reversed score.
    mj = pd.DataFrame(
        [
            {
                "date": "2018-06-25",
                "home_team": "Russia",
                "away_team": "Spain",
                "home_score": 2,
                "away_score": 2,
            }
        ]
    )
    out = wc_holdout.reconcile_settlement(panel, mj)
    assert bool(out.loc[0, "martj42_matched"]) is True
    assert bool(out.loc[0, "settlement_reconciled"]) is True
    assert out.loc[0, "ftr_full_jfjelstul"] == "D"


def test_settlement_reorients_home_away_winner():
    """A non-draw result is re-oriented to the panel's home/away when sources swap."""
    panel = pd.DataFrame(
        [
            {
                "match_date": "2014-07-13",
                "home_team_name": "Germany",
                "away_team_name": "Argentina",
                "home_team_score": 1,
                "away_team_score": 0,
            }
        ]
    )
    # martj42: Argentina home, lost 0-1 (i.e. away win from its perspective).
    mj = pd.DataFrame(
        [
            {
                "date": "2014-07-13",
                "home_team": "Argentina",
                "away_team": "Germany",
                "home_score": 0,
                "away_score": 1,
            }
        ]
    )
    out = wc_holdout.reconcile_settlement(panel, mj)
    # panel says Germany (home) won -> 'H'; reorient martj42 'A' (Germany away win) to 'H'.
    assert out.loc[0, "ftr_full_jfjelstul"] == "H"
    assert out.loc[0, "ftr_full_martj42"] == "H"
    assert bool(out.loc[0, "settlement_reconciled"]) is True


def test_qual_status_matchday1_is_live():
    """Before any group match is played, every team is 'live'."""
    assert wc_holdout._group_qual_status("X", {}, played_count_before=0) == "live"


def test_qual_status_clinched_when_only_one_team_can_reach():
    """A team on 6 pts after 2 games (2 wins) with rivals far behind is clinched."""
    standings = {
        "me": {"pts": 6, "gd": 4, "played": 2},
        "r1": {"pts": 1, "gd": -2, "played": 2},
        "r2": {"pts": 1, "gd": -1, "played": 2},
        "r3": {"pts": 0, "gd": -1, "played": 2},
    }
    # rivals max = 1+3=4, 1+3=4, 0+3=3 -> none can reach 6 -> clinched.
    assert wc_holdout._group_qual_status("me", standings, played_count_before=6) == "qualified"


def test_qual_status_not_clinched_when_a_level_finish_is_possible():
    """Tiebreak-safe: a rival that can FINISH LEVEL on points blocks the clinch
    (the South Africa 2002 case: 4 pts is not safe when a rival can reach 4)."""
    standings = {
        "me": {"pts": 4, "gd": 1, "played": 2},
        "rich": {"pts": 6, "gd": 4, "played": 2},  # already above, max 9
        "chaser": {"pts": 1, "gd": -2, "played": 2},  # max 1+3 = 4 == me -> can tie
        "dead": {"pts": 0, "gd": -3, "played": 2},  # max 3 < 4
    }
    # rich (>=4) and chaser (>=4) can both reach my points -> two could overtake
    # -> NOT clinched.
    assert wc_holdout._group_qual_status("me", standings, played_count_before=6) == "live"


def test_qual_status_eliminated():
    """Two teams certain to finish above my max -> eliminated."""
    standings = {
        "me": {"pts": 0, "gd": -5, "played": 2},  # max 0+3 = 3
        "a": {"pts": 4, "gd": 3, "played": 2},  # floor 4 > 3
        "b": {"pts": 6, "gd": 4, "played": 2},  # floor 6 > 3
        "c": {"pts": 1, "gd": -2, "played": 2},
    }
    assert wc_holdout._group_qual_status("me", standings, played_count_before=6) == "eliminated"


def test_clv_tagging_no_odds_all_undefined():
    """With no entry+closing pair, every WC row is clv_defined=False; pre-2019
    rows are synthetic_only (plan task 10)."""
    panel = pd.DataFrame(
        {"year": [2002, 2018, 2022], "has_entry_and_closing": [False, False, False]}
    )
    out = wc_holdout.tag_clv_defined(panel)
    assert list(out["synthetic_only"]) == [True, True, False]  # 2022 >= 2019 boundary
    assert list(out["clv_defined"]) == [False, False, False]  # no entry+closing anywhere
