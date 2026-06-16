"""Build the World-Cup hold-out settlement panel + emit a ReproLog.

Phase 1 slice (plan tasks 4, 5, 10). Orchestrates:
  1. download the genuinely-accessible RESULTS sources (jfjelstul + martj42) to
     data/raw/ with provenance + LF-checksum sidecars (src.provenance);
  2. reconstruct the 90-minute FTR from jfjelstul goals.csv (src.wc_holdout);
  3. build the team-name alias crosswalk -> data/external/team_aliases.csv;
  4. derive the point-in-time qualification-state feature (32-team era);
  5. tag clv_defined / synthetic_only (no WC odds obtained -> all False/True);
  6. cross-reconcile 90-min FTR vs martj42 (independent settlement check);
  7. write data/processed/wc_holdout_panel.parquet;
  8. emit logs/reprolog_<run_id>.json with dataset_checksums pinned (the
     committed-by-checksum snapshots, reproducible-from-snapshot).

The WC ODDS columns are intentionally absent (no headless source; gap recorded);
the panel is the held-out MATCH LIST + 90-min FTR + qual-state, so the transfer
test is PENDING-ODDS while Phases 2-4 run on the league universe.

Usage: python -m src.build_wc_panel [--snapshot-date YYYY-MM-DD]
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from src import provenance, reprolog, run, wc_holdout

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = PROJECT_ROOT / "data" / "raw"
EXTERNAL_DIR = PROJECT_ROOT / "data" / "external"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"

# Source-of-record raw URLs (RESULTS only -- odds gap recorded separately).
SOURCES = {
    "jfjelstul_matches": (
        "https://raw.githubusercontent.com/jfjelstul/worldcup/master/data-csv/matches.csv",
        "jfjelstul/worldcup matches.csv (academic FIFA World Cup DB, GitHub master)",
    ),
    "jfjelstul_goals": (
        "https://raw.githubusercontent.com/jfjelstul/worldcup/master/data-csv/goals.csv",
        "jfjelstul/worldcup goals.csv (per-goal minute + match_period; 90-min reconstruction)",
    ),
    "jfjelstul_penalties": (
        "https://raw.githubusercontent.com/jfjelstul/worldcup/master/data-csv/penalty_kicks.csv",
        "jfjelstul/worldcup penalty_kicks.csv (shootout cross-check)",
    ),
    "martj42_results": (
        "https://raw.githubusercontent.com/martj42/international_results/master/results.csv",
        "martj42/international_results results.csv (independent settlement cross-check)",
    ),
    "martj42_shootouts": (
        "https://raw.githubusercontent.com/martj42/international_results/master/shootouts.csv",
        "martj42/international_results shootouts.csv (penalty-decided knockout cross-check)",
    ),
}

RAW_FILENAMES = {
    "jfjelstul_matches": "wc_jfjelstul_matches",
    "jfjelstul_goals": "wc_jfjelstul_goals",
    "jfjelstul_penalties": "wc_jfjelstul_penalties",
    "martj42_results": "intl_results",
    "martj42_shootouts": "intl_shootouts",
}


def fetch_sources(snapshot_date: str, raw_dir: Path | None = None) -> dict[str, str]:
    """Download every RESULTS source to data/raw/ with provenance + checksum.

    Returns a dataset-id -> sha256 map suitable for the ReproLog dataset_checksums.
    """
    rdir = Path(raw_dir) if raw_dir is not None else RAW_DIR
    checksums: dict[str, str] = {}
    for key, (url, label) in SOURCES.items():
        dest_name = f"{RAW_FILENAMES[key]}_{snapshot_date}.csv"
        rec = provenance.fetch_to_raw(
            url, dest_name, source_label=label, snapshot_date=snapshot_date, raw_dir=rdir
        )
        checksums[dest_name] = rec["sha256_lf"]
    return checksums


def assemble_panel(snapshot_date: str, raw_dir: Path | None = None) -> pd.DataFrame:
    """Read the downloaded sources and build the WC hold-out panel (2002-2022)."""
    rdir = Path(raw_dir) if raw_dir is not None else RAW_DIR
    jf_matches = pd.read_csv(rdir / f"wc_jfjelstul_matches_{snapshot_date}.csv")
    jf_goals = pd.read_csv(rdir / f"wc_jfjelstul_goals_{snapshot_date}.csv")
    mj_results = pd.read_csv(rdir / f"intl_results_{snapshot_date}.csv")

    jf_matches["year"] = jf_matches["tournament_id"].str.extract(r"WC-(\d{4})").astype(int)
    wc = jf_matches[jf_matches["year"].isin(wc_holdout.PROJECT_WC_YEARS)].copy()

    # 1) 90-minute FTR reconstruction (the DNB settlement basis).
    wc = wc_holdout.reconstruct_90min_scores(wc, jf_goals)

    # 2) qualification-state feature (per edition; 32-team era).
    qual_frames = []
    for _, ydf in wc.groupby("year"):
        qual_frames.append(wc_holdout.qual_state_32team(ydf))
    qual = pd.concat(qual_frames, ignore_index=True)
    # Pivot to home/away qual-state per match.
    qmap = qual.set_index(["match_id", "team_id"])["qual_state"].to_dict()
    wc["home_qual_state"] = [
        qmap.get((mid, tid)) for mid, tid in zip(wc["match_id"], wc["home_team_id"], strict=True)
    ]
    wc["away_qual_state"] = [
        qmap.get((mid, tid)) for mid, tid in zip(wc["match_id"], wc["away_team_id"], strict=True)
    ]
    # Dead-rubber flag: a group match where BOTH teams' status is already decided
    # (both qualified or both eliminated -> no sporting stake; EDGE §4.4). Headline
    # use restricted to the 32-team era (all of 2002-2022).
    wc["dead_rubber"] = wc.apply(
        lambda r: bool(
            r["group_stage"] == 1
            and r["home_qual_state"] in ("qualified", "eliminated")
            and r["away_qual_state"] in ("qualified", "eliminated")
        ),
        axis=1,
    )

    # 3) CLV / synthetic-only tagging (no WC odds obtained -> all clv_defined=False).
    wc["has_entry_and_closing"] = False  # no odds source obtained (gap)
    wc = wc_holdout.tag_clv_defined(wc, year_col="year")

    # 4) independent, ORDER-INSENSITIVE settlement cross-check vs martj42 (DATA
    #    §2.5): a WC fixture is the same regardless of which source calls which
    #    side "home" (host/neutral conventions differ). The full incl-ET result
    #    is compared after re-orienting to the panel's home/away order.
    wc = wc_holdout.reconcile_settlement(wc, mj_results)

    # Canonical panel columns (DATA §7.1 subset that is defined without odds).
    cols = [
        "match_id",
        "year",
        "tournament_id",
        "match_date",
        "match_time",
        "stage_name",
        "group_name",
        "group_stage",
        "knockout_stage",
        "home_team_name",
        "away_team_name",
        "home_team_score",
        "away_team_score",
        "extra_time",
        "penalty_shootout",
        "fthg_90",
        "ftag_90",
        "ftr_90",
        "is_push_90",
        "decided_in_et",
        "home_qual_state",
        "away_qual_state",
        "dead_rubber",
        "synthetic_only",
        "clv_defined",
        "ftr_full_jfjelstul",
        "ftr_full_martj42",
        "martj42_matched",
        "settlement_reconciled",
    ]
    return wc[cols].sort_values(["year", "match_date", "match_id"]).reset_index(drop=True)


def build(
    snapshot_date: str | None = None,
    *,
    raw_dir: Path | None = None,
    external_dir: Path | None = None,
    processed_dir: Path | None = None,
    logs_dir: Path | None = None,
    fetch: bool = True,
) -> dict:
    """Full build: fetch -> assemble -> crosswalk -> write -> ReproLog.

    Returns a summary dict (counts, fractions, reconciliation, paths).
    """
    snap = snapshot_date or datetime.now(UTC).strftime("%Y-%m-%d")
    rdir = Path(raw_dir) if raw_dir is not None else RAW_DIR
    edir = Path(external_dir) if external_dir is not None else EXTERNAL_DIR
    pdir = Path(processed_dir) if processed_dir is not None else PROCESSED_DIR
    edir.mkdir(parents=True, exist_ok=True)
    pdir.mkdir(parents=True, exist_ok=True)

    if fetch:
        checksums = fetch_sources(snap, raw_dir=rdir)
    else:
        # Reuse existing raw files but STILL pin their checksums from disk, so the
        # ReproLog records the input-snapshot hashes regardless of whether this
        # invocation downloaded them (reproducible-from-snapshot; plan §D.4).
        checksums = {}
        for key in SOURCES:
            dest_name = f"{RAW_FILENAMES[key]}_{snap}.csv"
            dest = rdir / dest_name
            if dest.exists():
                checksums[dest_name] = reprolog.sha256_path(dest)

    panel = assemble_panel(snap, raw_dir=rdir)

    # Crosswalk.
    jf_matches = pd.read_csv(rdir / f"wc_jfjelstul_matches_{snap}.csv")
    jf_matches["year"] = jf_matches["tournament_id"].str.extract(r"WC-(\d{4})").astype(int)
    jf_wc = jf_matches[jf_matches["year"].isin(wc_holdout.PROJECT_WC_YEARS)]
    mj_results = pd.read_csv(rdir / f"intl_results_{snap}.csv")
    mj_results["date"] = pd.to_datetime(mj_results["date"])
    mj_results["year"] = mj_results["date"].dt.year
    mj_wc = mj_results[
        (mj_results["tournament"] == "FIFA World Cup")
        & (mj_results["year"].isin(wc_holdout.PROJECT_WC_YEARS))
    ]
    crosswalk = wc_holdout.build_team_alias_crosswalk(jf_wc, mj_wc)
    crosswalk_path = edir / "team_aliases.csv"
    crosswalk.to_csv(crosswalk_path, index=False, lineterminator="\n")

    # Write the panel.
    panel_path = pdir / "wc_holdout_panel.parquet"
    panel.to_parquet(panel_path, index=False)
    # Also a CSV mirror (human-auditable; LF) and checksum the parquet bytes.
    panel_csv = pdir / "wc_holdout_panel.csv"
    panel.to_csv(panel_csv, index=False, lineterminator="\n")
    checksums["wc_holdout_panel.csv"] = reprolog.sha256_path(panel_csv)
    checksums["team_aliases.csv"] = reprolog.sha256_path(crosswalk_path)

    # ReproLog (ingest sub-stream; data_vendor names the RESULTS sources, odds gap noted).
    # The root seed is read from config (NOT a literal here) -- the single
    # no-magic-number exemption lives in config/baseline.yaml (plan task 9.1).
    root_seed = run.root_seed_from_config(run.load_config(Path("config/baseline.yaml")))
    run_id = f"wc-ingest-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}"
    vendor = (
        "jfjelstul/worldcup + martj42/international_results (RESULTS only; WC odds gap recorded)"
    )
    record = reprolog.build(
        run_id=run_id,
        rng_seed=root_seed,
        dataset_checksums=checksums,
        data_vendor=vendor,
        snapshot_date=snap,
        logs_dir=logs_dir,
    )
    repro_path = record.emit(logs_dir=logs_dir)

    # Summary metrics.
    summary = {
        "snapshot_date": snap,
        "n_matches": len(panel),
        "n_by_year": panel.groupby("year").size().to_dict(),
        "n_push_90": int(panel["is_push_90"].sum()),
        "draw_rate_90": round(float(panel["is_push_90"].mean()), 4),
        "n_decided_in_et": int(panel["decided_in_et"].sum()),
        "et_matches_with_90min_draw": panel[panel["decided_in_et"]][
            ["year", "home_team_name", "away_team_name", "home_team_score", "away_team_score"]
        ].to_dict("records"),
        "n_penalty_shootout": int(panel["penalty_shootout"].sum()),
        "clv_defined_fraction": round(float(panel["clv_defined"].mean()), 4),
        "synthetic_only_fraction": round(float(panel["synthetic_only"].mean()), 4),
        "settlement_reconciled_fraction": round(float(panel["settlement_reconciled"].mean()), 4),
        "n_martj42_matched": int(panel["martj42_matched"].sum()),
        "crosswalk_n_teams": len(crosswalk),
        "crosswalk_matched_both": int(crosswalk["matched_both"].sum()),
        "dataset_checksums": checksums,
        "reprolog_path": repro_path.as_posix(),
        "panel_path": panel_path.as_posix(),
        "crosswalk_path": crosswalk_path.as_posix(),
        "odds_status": "PENDING-ODDS: no headless WC odds source obtainable; results panel only",
    }
    return summary


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m src.build_wc_panel")
    p.add_argument("--snapshot-date", default=None, help="YYYY-MM-DD (default: today UTC)")
    p.add_argument("--no-fetch", action="store_true", help="reuse existing raw files")
    args = p.parse_args(argv)
    summary = build(args.snapshot_date, fetch=not args.no_fetch)
    import json

    print(json.dumps(summary, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
