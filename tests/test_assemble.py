"""Tests for the canonical-panel assembly (plan Phase 1 task 1 schema).

Covers:
  * the league + WC blocks map onto every DATA §7.1 canonical field;
  * a penalty-decided 1-1 WC match propagates as a DNB push (FTR='D', is_push=True)
    into the assembled canonical panel (the load-bearing 90-min settlement rule);
  * the WC odds gap is NOT fabricated: WC refC_*/underdog_side/o_dnb_underdog are
    null and odds_status='pending';
  * the content checksum is deterministic (same content -> same SHA).

In-memory fixtures (no network); the live assembly is exercised by --stage ingest.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from src import assemble


def _league_fixture() -> pd.DataFrame:
    """Minimal league panel shaped like src.ingest.attach_reference_price output."""
    return pd.DataFrame(
        {
            "match_id": ["E0_2223_A_B", "E0_2223_C_D"],
            "competition": ["E0", "E0"],
            "season": [2223, 2223],
            "Date": ["01/02/2023", "02/02/2023"],
            "Time": ["15:00", "17:30"],
            "HomeTeam": ["A", "C"],
            "AwayTeam": ["B", "D"],
            "FTHG": [2.0, 1.0],
            "FTAG": [1.0, 1.0],
            "FTR": ["H", "D"],
            "refC_H": [2.95, 1.80],
            "refC_D": [3.35, 3.60],
            "refC_A": [2.55, 4.50],
            "ref_book": ["pinnacle_close", "pinnacle_close"],
            "quoted_ah_line": [0.0, 0.0],
            "quoted_ah_home": [1.95, 2.10],
            "quoted_ah_away": [1.95, 1.80],
            "quoted_ah_missing": [False, False],
            "underdog_side": ["home", "away"],
            "o_dnb_underdog": [2.95 * (3.35 - 1) / 3.35, 4.50 * (3.60 - 1) / 3.60],
        }
    )


def _wc_fixture() -> pd.DataFrame:
    """Minimal WC hold-out panel shaped like src.build_wc_panel.assemble_panel output."""
    return pd.DataFrame(
        {
            "match_id": ["WC-2006-FINAL", "WC-2006-GRP"],
            "year": [2006, 2006],
            "tournament_id": ["WC-2006", "WC-2006"],
            "match_date": ["2006-07-09", "2006-06-12"],
            "match_time": ["20:00", "18:00"],
            "stage_name": ["final", "group stage"],
            "group_name": ["not applicable", "Group A"],
            "group_stage": [0, 1],
            "knockout_stage": [1, 0],
            "home_team_name": ["Italy", "Germany"],
            "away_team_name": ["France", "Costa Rica"],
            "home_team_score": [1, 4],  # FULL result incl. ET (Italy won on pens)
            "away_team_score": [1, 2],
            "extra_time": [1, 0],
            "penalty_shootout": [1, 0],
            "fthg_90": [1, 4],  # 90-min reconstruction
            "ftag_90": [1, 2],
            "ftr_90": ["D", "H"],
            "is_push_90": [True, False],
            "decided_in_et": [False, False],
            "home_qual_state": ["knockout", "live"],
            "away_qual_state": ["knockout", "live"],
            "dead_rubber": [False, False],
            "synthetic_only": [True, True],
            "clv_defined": [False, False],
        }
    )


def test_canonical_schema_complete_both_blocks():
    panel = assemble.assemble_matches(
        _league_fixture(),
        _wc_fixture(),
        league_vendor="football-data.co.uk",
        wc_vendor="jfjelstul+martj42",
        snapshot_date="2026-06-16",
    )
    # Every DATA §7.1 canonical column present, in canonical order.
    assert list(panel.columns) == list(assemble.CANONICAL_COLUMNS)
    assert set(panel["block"]) == {"league", "wc"}
    assert (panel["block"] == "league").sum() == 2
    assert (panel["block"] == "wc").sum() == 2


def test_penalty_decided_1_1_is_dnb_push_in_canonical_panel():
    """A penalty-decided 1-1 WC final settles as a DNB push in the assembled panel:
    FTR='D', is_push=True (90-minute settlement; CALC §10; plan task 5)."""
    panel = assemble.assemble_matches(
        _league_fixture(),
        _wc_fixture(),
        league_vendor="fd",
        wc_vendor="jf",
        snapshot_date="2026-06-16",
    )
    final = panel[panel["match_id"] == "WC-2006-FINAL"].iloc[0]
    assert final["FTR"] == "D"
    assert bool(final["is_push"]) is True
    assert bool(final["penalty_shootout"]) is True
    # 90-minute goals carried, FULL-result ET winner does NOT change settlement.
    assert (final["FTHG"], final["FTAG"]) == (1, 1)


def test_wc_odds_gap_is_null_not_fabricated():
    """The WC block carries NO odds: refC_*/underdog_side/o_dnb_underdog are null and
    odds_status='pending' -- the honest gap, never invented (data-integrity rule)."""
    panel = assemble.assemble_matches(
        _league_fixture(), _wc_fixture(), league_vendor="fd", wc_vendor="jf", snapshot_date="d"
    )
    wc = panel[panel["block"] == "wc"]
    assert wc["refC_H"].isna().all()
    assert wc["refC_D"].isna().all()
    assert wc["refC_A"].isna().all()
    assert wc["underdog_side"].isna().all()
    assert wc["o_dnb_underdog"].isna().all()
    assert (wc["odds_status"] == "pending").all()


def test_league_block_carries_derived_betting_fields():
    """The league block carries refC_*, ref_book, underdog_side, o_dnb_underdog,
    overround, and a 90-minute FTR on every row (the acceptance criterion)."""
    panel = assemble.assemble_matches(
        _league_fixture(), _wc_fixture(), league_vendor="fd", wc_vendor="jf", snapshot_date="d"
    )
    lg = panel[panel["block"] == "league"]
    for c in ("refC_H", "refC_D", "refC_A", "ref_book", "underdog_side", "o_dnb_underdog", "FTR"):
        assert lg[c].notna().all(), c
    # overround = reciprocal sum (raw, stripped per match for de-vig downstream).
    row0 = lg.iloc[0]
    expected_or = 1 / row0["refC_H"] + 1 / row0["refC_D"] + 1 / row0["refC_A"]
    assert (
        row0["overround"] == np.float64(expected_or) or abs(row0["overround"] - expected_or) < 1e-9
    )
    assert (lg["odds_status"] == "available").all()


def test_content_sha256_is_deterministic():
    panel = assemble.assemble_matches(
        _league_fixture(), _wc_fixture(), league_vendor="fd", wc_vendor="jf", snapshot_date="d"
    )
    assert assemble.content_sha256(panel) == assemble.content_sha256(panel.copy())


def test_content_sha256_invariant_to_snapshot_date():
    """REGRESSION (major Phase-1 finding): the canonical-panel content SHA must be a
    function of the point-in-time SOURCE DATA only, never the run's wall-clock date.

    The same byte-identical league+WC inputs assembled under three different
    snapshot_dates (and vendor labels) must produce the SAME content checksum --
    otherwise a reviewer re-running ingest on a different calendar day gets a
    different matches.parquet hash for identical raw data, breaking the
    reproducible-from-snapshot acceptance criterion. snapshot_date/data_vendor are
    DATA §7.1 provenance columns and are excluded from the hash."""
    league, wc = _league_fixture(), _wc_fixture()
    shas = set()
    metas = (
        ("football-data.co.uk", "jfjelstul+martj42", "2026-06-16"),
        ("football-data.co.uk", "jfjelstul+martj42", "2026-06-17"),
        ("a-different-vendor", "another-wc-source", "2027-01-01"),
    )
    for lv, wv, snap in metas:
        panel = assemble.assemble_matches(
            league.copy(), wc.copy(), league_vendor=lv, wc_vendor=wv, snapshot_date=snap
        )
        # The provenance columns DO differ across runs (carried for auditability)...
        assert (panel["snapshot_date"] == snap).all()
        shas.add(assemble.content_sha256(panel))
    # ...but the content checksum is invariant to them.
    assert len(shas) == 1, f"content SHA varied with run metadata: {shas}"


def test_content_sha256_changes_when_source_data_changes():
    """The content SHA still RESPONDS to a genuine point-in-time data change (so the
    exclusion of run-metadata columns did not blind the hash to real edits)."""
    league = _league_fixture()
    base = assemble.assemble_matches(
        league.copy(), _wc_fixture(), league_vendor="fd", wc_vendor="jf", snapshot_date="d"
    )
    perturbed_league = league.copy()
    perturbed_league.loc[0, "refC_H"] = perturbed_league.loc[0, "refC_H"] + 0.10
    perturbed = assemble.assemble_matches(
        perturbed_league, _wc_fixture(), league_vendor="fd", wc_vendor="jf", snapshot_date="d"
    )
    assert assemble.content_sha256(base) != assemble.content_sha256(perturbed)
