"""WC-input checksum-binding tests (Phase-1 major-finding remediation).

The canonical ``data/processed/matches.parquet`` includes the 384-row World-Cup
settlement block, but the WC RESULTS inputs (jfjelstul/martj42 snapshots, the WC
hold-out panel) were only pinned in a separate out-of-band wc-ingest ReproLog --
never bound by checksum into the ingest/validate stages that emit the headline
canonical-panel hash. These tests lock the fix:

  * ``assemble_canonical_panel`` fails closed (``WCPanelMissingError``) when the WC
    hold-out panel is absent rather than silently emitting a league-only panel under
    the canonical hash;
  * with ``require_wc=False`` it still materialises the league-only panel (offline);
  * ``wc_source_checksums`` pins every on-disk WC input (raw RESULTS snapshots, the
    WC panel CSV mirror + content fingerprint, the team-alias crosswalk);
  * the assembly returns the WC checksum map so ``run_ingest_stage`` folds it into
    the ingest ReproLog ``dataset_checksums`` -- the transitive binding the finding
    requires.

In-memory / tmp fixtures only; no network. Nothing is fabricated as real odds (the
WC block carries the honest pending-odds gap, identical to the assemble tests).
"""

from __future__ import annotations

import types

import pandas as pd
import pytest
from src import assemble, reprolog, run


def _league_panel() -> pd.DataFrame:
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


def _wc_panel() -> pd.DataFrame:
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
            "home_team_score": [1, 4],
            "away_team_score": [1, 2],
            "extra_time": [1, 0],
            "penalty_shootout": [1, 0],
            "fthg_90": [1, 4],
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


def _ingest_result() -> types.SimpleNamespace:
    """A stand-in for the IngestResult fields assemble_canonical_panel reads."""
    return types.SimpleNamespace(panel=_league_panel(), snapshot_date="2026-06-16")


def _config() -> dict:
    return run.load_config(run.PROJECT_ROOT / "config" / "baseline.yaml")


def _seed_wc_inputs(tmp_path) -> tuple:
    """Write a WC panel (parquet + CSV mirror), the WC raw RESULTS snapshots, and a
    team-alias crosswalk into a tmp data/ tree; return (processed_dir, raw_dir)."""
    pdir = tmp_path / "data" / "processed"
    rdir = tmp_path / "data" / "raw"
    edir = tmp_path / "data" / "external"
    pdir.mkdir(parents=True, exist_ok=True)
    rdir.mkdir(parents=True, exist_ok=True)
    edir.mkdir(parents=True, exist_ok=True)

    wc = _wc_panel()
    wc.to_parquet(pdir / "wc_holdout_panel.parquet", index=False)
    (pdir / "wc_holdout_panel.csv").write_text(
        wc.to_csv(index=False, lineterminator="\n"), encoding="utf-8", newline="\n"
    )

    # Minimal but genuine-shaped WC raw RESULTS snapshots (one per build_wc_panel
    # prefix). These are tmp test fixtures, NOT presented as the analysis sources.
    snap = "2026-06-16"
    raw_rows = "h,a\n1,2\n"
    for prefix in run.WC_RAW_SOURCE_PREFIXES:
        (rdir / f"{prefix}{snap}.csv").write_text(raw_rows, encoding="utf-8", newline="\n")

    # martj42 results with a `neutral` flag (host-stratum source).
    (rdir / "intl_results_2026-06-16.csv").write_text(
        "date,home_team,away_team,home_score,away_score,tournament,neutral\n"
        "2006-07-09,Italy,France,1,1,FIFA World Cup,True\n",
        encoding="utf-8",
        newline="\n",
    )
    (edir / "team_aliases.csv").write_text(
        "team,alias\nItaly,Italy\n", encoding="utf-8", newline="\n"
    )
    return pdir, rdir


def test_assemble_fails_closed_when_wc_panel_absent(tmp_path):
    pdir = tmp_path / "processed"
    rdir = tmp_path / "raw"
    pdir.mkdir()
    rdir.mkdir()
    with pytest.raises(run.WCPanelMissingError):
        run.assemble_canonical_panel(
            _config(), _ingest_result(), processed_dir=pdir, raw_dir=rdir, require_wc=True
        )


def test_assemble_league_only_when_require_wc_false(tmp_path):
    pdir = tmp_path / "processed"
    rdir = tmp_path / "raw"
    pdir.mkdir()
    rdir.mkdir()
    mpath, sha, counts, wc_checks = run.assemble_canonical_panel(
        _config(), _ingest_result(), processed_dir=pdir, raw_dir=rdir, require_wc=False
    )
    assert mpath is not None and sha is not None and len(sha) == 64
    assert counts == {"n_league": 2, "n_wc": 0}
    assert wc_checks == {}  # no WC block -> no WC inputs bound


def test_wc_source_checksums_pins_every_input(tmp_path):
    pdir, rdir = _seed_wc_inputs(tmp_path)
    checks = run.wc_source_checksums(processed_dir=pdir, raw_dir=rdir, wc_panel=_wc_panel())
    # Every WC raw RESULTS snapshot is bound by checksum.
    for prefix in run.WC_RAW_SOURCE_PREFIXES:
        assert f"{prefix}2026-06-16.csv" in checks
    # The WC panel content fingerprint + CSV mirror + crosswalk are bound.
    assert "wc_holdout_panel.content" in checks
    assert "wc_holdout_panel.csv" in checks
    assert "team_aliases.csv" in checks
    # Every value is a valid lowercase 64-hex SHA-256.
    for v in checks.values():
        assert len(v) == 64 and v == v.lower()
    # The content fingerprint matches the canonical content checksum of the panel.
    assert checks["wc_holdout_panel.content"] == assemble.content_sha256(_wc_panel())
    # The raw-source SHA matches the LF-normalized path SHA (== build_wc_panel value).
    raw = rdir / "wc_jfjelstul_matches_2026-06-16.csv"
    assert checks["wc_jfjelstul_matches_2026-06-16.csv"] == reprolog.sha256_path(raw)


def test_assembly_returns_wc_checksums_for_reprolog_binding(tmp_path):
    pdir, rdir = _seed_wc_inputs(tmp_path)
    mpath, sha, counts, wc_checks = run.assemble_canonical_panel(
        _config(), _ingest_result(), processed_dir=pdir, raw_dir=rdir, require_wc=True
    )
    assert counts == {"n_league": 2, "n_wc": 2}
    assert mpath is not None and sha is not None
    # The WC inputs are returned so run_ingest_stage folds them into the ingest
    # ReproLog dataset_checksums (the transitive binding the finding requires).
    assert wc_checks  # non-empty
    assert "wc_holdout_panel.content" in wc_checks
    assert any(k.startswith("wc_jfjelstul_matches_") for k in wc_checks)
    assert any(k.startswith("intl_results_") for k in wc_checks)
