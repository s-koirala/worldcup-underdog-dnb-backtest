"""Assemble the single canonical PIT-correct match panel (plan Phase 1 task 1 schema).

This module reconciles the two Phase-1 raw deliverables that have already landed on
disk -- the football-data.co.uk league estimation universe (``src/ingest.py`` ->
``data/processed/league_panel.parquet``) and the World-Cup hold-out settlement panel
(``src/build_wc_panel.py`` -> ``data/processed/wc_holdout_panel.parquet``) -- into ONE
canonical table ``data/processed/matches.parquet`` carrying every DATA §7.1 field.

Each row carries, evaluable at kickoff (point-in-time correct; DATA §5):
  * ``refC_H/refC_D/refC_A``  -- the season-conditional closing reference price;
  * ``ref_book``             -- which book/consensus populated refC_* (the cutover log);
  * ``underdog_side``        -- ``argmax(refC_H, refC_A)``;
  * ``o_dnb_underdog``       -- synthetic DNB price ``= refC_side·(refC_D-1)/refC_D``;
  * ``FTR``                  -- the 90-MINUTE Full-Time Result (DNB settlement basis);
  * ``competition`` + ``block`` -- the universe flag (``block in {league, wc}``).

Overround is stripped per match (``overround`` column = raw reciprocal sum) so a
downstream probability comparison can de-vig per row; the raw odds are retained for
settlement (DATA §5.4).

HONEST DATA STATE (verified 2026-06-16; recorded, never fabricated): the World-Cup
block has NO odds source obtainable headlessly (note_wc-odds-gap), so its ``refC_*`` /
``underdog_side`` / ``o_dnb_underdog`` are NULL and the rows carry
``odds_status = 'pending'``. The WC rows are the held-out MATCH LIST + 90-minute FTR +
qual-state, included so the panel is complete and the transfer test is wired; the WC
edge test stays PENDING-ODDS. No odds were invented for any WC row.

Pathlib only; LF-normalized bytes for the content checksum; no magic numbers.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from src.reprolog import sha256_text

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"

# The canonical DATA §7.1 column order for matches.parquet. Every field appears;
# fields undefined for a block carry null (e.g. WC refC_* while odds are pending).
CANONICAL_COLUMNS: tuple[str, ...] = (
    # identity / metadata
    "match_id",
    "block",  # 'league' | 'wc' -- the universe flag (DATA §4.3)
    "competition",  # 'E0','D1',... for league; 'WC2002',... for WC
    "season",  # league 4-digit compaction; WC edition year as str
    "date",  # ISO-ordered local match date
    "kickoff_utc",  # Time/scrape PIT gate (§5); null where absent
    "home_team",
    "away_team",
    "neutral",  # True for most WC; False for league
    "host",  # WC host stratum (host/neutral); null for league
    # settlement (90-minute result)
    "FTHG",
    "FTAG",
    "FTR",  # H/D/A on the 90-MINUTE score -- the DNB settlement (DATA §7.1)
    "is_push",  # FTR == 'D' (the DNB refund)
    "decided_in_et",  # WC: level at 90 but ET changed the recorded result
    "penalty_shootout",  # WC: shootout-decided (still a 90-min push if level)
    # season-conditional reference price + provenance
    "refC_H",
    "refC_D",
    "refC_A",
    "ref_book",  # pinnacle_close / market_avg_close / ... / none_available
    # quoted AH-0.0 (native DNB) where present (league >=2019/20)
    "quoted_ah_line",
    "quoted_ah_home",
    "quoted_ah_away",
    "quoted_ah_missing",  # fail-closed flag (task 2.1)
    # derived betting fields (PIT-correct; null where refC_* is null)
    "overround",  # 1/refC_H + 1/refC_D + 1/refC_A (raw reciprocal sum)
    "underdog_side",  # argmax(refC_H, refC_A)
    "o_dnb_underdog",  # synthetic DNB price on the underdog side (DATA §1.2)
    # CLV / odds availability tags (task 10)
    "synthetic_only",
    "clv_defined",
    "odds_status",  # 'available' (league) | 'pending' (WC, odds gap)
    # WC-only point-in-time qualification-state stratum (task 7.1)
    "qual_state_home",
    "qual_state_away",
    "dead_rubber",
    # provenance
    "data_vendor",
    "snapshot_date",
)

# Run-metadata (provenance) columns that are a function of WHEN/HOW the assembly
# ran, not of the point-in-time source data (DATA §7.1: `data_vendor`,
# `snapshot_date` are `meta`/`provenance`). These are recorded as ReproLog keys 6/7
# and as panel columns for auditability, but MUST be excluded from the content
# checksum: the canonical-panel content SHA is the fingerprint of the source DATA a
# reviewer reproduces, and including the wall-clock snapshot_date made the headline
# matches.parquet hash change every calendar day for byte-identical inputs (the
# major Phase-1 finding). Hashing only the data columns makes the content SHA
# invariant to the run's wall-clock date / vendor label.
RUN_METADATA_COLUMNS: frozenset[str] = frozenset({"data_vendor", "snapshot_date"})


def _overround(h: pd.Series, d: pd.Series, a: pd.Series) -> pd.Series:
    with np.errstate(divide="ignore", invalid="ignore"):
        return 1.0 / h + 1.0 / d + 1.0 / a


def league_to_canonical(
    league_panel: pd.DataFrame, *, data_vendor: str, snapshot_date: str
) -> pd.DataFrame:
    """Map the league estimation panel onto the canonical schema.

    The league panel already carries refC_*/ref_book/underdog_side/o_dnb_underdog
    (derived in src/ingest.attach_reference_price) and a 90-minute FTR (domestic
    matches have no extra time, so the recorded FTR IS the 90-minute result --
    DATA §7.2). Maps football-data column names onto the canonical names.
    """
    lp = league_panel.copy()
    out = pd.DataFrame(index=lp.index)
    out["match_id"] = lp["match_id"].astype(str)
    out["block"] = "league"
    out["competition"] = lp["competition"].astype(str)
    out["season"] = lp["season"].astype(str)
    out["date"] = lp.get("Date", pd.Series([None] * len(lp), index=lp.index)).astype("string")
    out["kickoff_utc"] = lp.get("Time", pd.Series([None] * len(lp), index=lp.index)).astype(
        "string"
    )
    out["home_team"] = lp["HomeTeam"].astype(str)
    out["away_team"] = lp["AwayTeam"].astype(str)
    # Domestic league matches are NOT at a neutral venue (the book prices venue;
    # the underdog definition is venue-robust -- DATA §4.4-risk-2).
    out["neutral"] = pd.Series([False] * len(lp), index=lp.index, dtype="boolean")
    # WC-only stratum: typed nullable-string so the concat with the WC block needs
    # no dtype inference from an all-NA column (avoids the pandas concat warning).
    out["host"] = pd.Series([pd.NA] * len(lp), index=lp.index, dtype="string")

    out["FTHG"] = pd.to_numeric(lp["FTHG"], errors="coerce")
    out["FTAG"] = pd.to_numeric(lp["FTAG"], errors="coerce")
    out["FTR"] = lp["FTR"].astype(str)  # already the 90-minute result for league
    out["is_push"] = out["FTR"].eq("D").astype("boolean")
    # no extra time / shootouts in domestic league fixtures.
    out["decided_in_et"] = pd.Series([False] * len(lp), index=lp.index, dtype="boolean")
    out["penalty_shootout"] = pd.Series([False] * len(lp), index=lp.index, dtype="boolean")

    for c in ("refC_H", "refC_D", "refC_A"):
        out[c] = pd.to_numeric(lp[c], errors="coerce")
    out["ref_book"] = lp["ref_book"].astype("string")

    out["quoted_ah_line"] = pd.to_numeric(lp.get("quoted_ah_line"), errors="coerce")
    out["quoted_ah_home"] = pd.to_numeric(lp.get("quoted_ah_home"), errors="coerce")
    out["quoted_ah_away"] = pd.to_numeric(lp.get("quoted_ah_away"), errors="coerce")
    out["quoted_ah_missing"] = lp.get(
        "quoted_ah_missing", pd.Series([True] * len(lp), index=lp.index)
    ).astype("boolean")

    out["overround"] = _overround(out["refC_H"], out["refC_D"], out["refC_A"])
    out["underdog_side"] = lp["underdog_side"].astype("string")
    out["o_dnb_underdog"] = pd.to_numeric(lp["o_dnb_underdog"], errors="coerce")

    # CLV: native AH (the genuine entry+closing pair) exists only from 2019/20
    # (DATA §2.2, task 10). synthetic_only where the quoted AH-0.0 pair is absent;
    # clv_defined requires a genuine entry+closing pair -- in the closing-only
    # football-data feed there is a single closing price, so CLV is undefined for
    # the synthetic route. A row with a present quoted AH line is the only one that
    # could later carry a defined CLV; absent line-movement data, clv_defined=False
    # for all league rows here and is resolved when an entry price is sourced.
    out["synthetic_only"] = out["quoted_ah_missing"].astype("boolean")
    out["clv_defined"] = pd.Series([False] * len(lp), index=lp.index, dtype="boolean")
    out["odds_status"] = "available"

    # league has no tournament qual-state -> typed nullable-string null (so the
    # concat with the WC block, where these are populated, needs no dtype inference).
    out["qual_state_home"] = pd.Series([pd.NA] * len(lp), index=lp.index, dtype="string")
    out["qual_state_away"] = pd.Series([pd.NA] * len(lp), index=lp.index, dtype="string")
    out["dead_rubber"] = pd.Series([False] * len(lp), index=lp.index, dtype="boolean")

    out["data_vendor"] = data_vendor
    out["snapshot_date"] = snapshot_date
    return out


def wc_to_canonical(
    wc_panel: pd.DataFrame,
    *,
    data_vendor: str,
    snapshot_date: str,
    mj_results: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Map the World-Cup hold-out panel onto the canonical schema.

    The WC panel carries a reconstructed 90-minute FTR (``ftr_90``), qual-state,
    dead-rubber, and CLV tags, but NO odds (PENDING-ODDS; note_wc-odds-gap). The
    refC_* / underdog_side / o_dnb_underdog fields are therefore NULL and
    ``odds_status = 'pending'`` -- NOT fabricated.

    The host stratum (EDGE §4.3) is derived from the martj42 ``neutral`` flag when
    that table is supplied (a non-neutral WC match is a host match); otherwise
    ``host`` is left null and the stratum is resolved when odds + venue are joined.
    """
    wc = wc_panel.copy()
    out = pd.DataFrame(index=wc.index)
    out["match_id"] = wc["match_id"].astype(str)
    out["block"] = "wc"
    out["competition"] = "WC" + wc["year"].astype(int).astype(str)
    out["season"] = wc["year"].astype(int).astype(str)
    out["date"] = wc["match_date"].astype("string")
    out["kickoff_utc"] = wc.get("match_time", pd.Series([None] * len(wc), index=wc.index)).astype(
        "string"
    )
    out["home_team"] = wc["home_team_name"].astype(str)
    out["away_team"] = wc["away_team_name"].astype(str)

    # Host stratum from martj42 `neutral` (a non-neutral WC fixture is a host game).
    host, neutral = _wc_host_neutral(wc, mj_results)
    out["neutral"] = neutral
    out["host"] = host

    out["FTHG"] = pd.to_numeric(wc["fthg_90"], errors="coerce")
    out["FTAG"] = pd.to_numeric(wc["ftag_90"], errors="coerce")
    out["FTR"] = wc["ftr_90"].astype(str)  # the 90-MINUTE result (reconstructed)
    out["is_push"] = wc["is_push_90"].astype("boolean")
    out["decided_in_et"] = wc["decided_in_et"].astype("boolean")
    out["penalty_shootout"] = wc["penalty_shootout"].astype(bool).astype("boolean")

    # ODDS PENDING -> reference price / derived betting fields are NULL (gap, not
    # fabricated). When a ToS-cleared WC-odds snapshot is frozen, these are filled.
    for c in ("refC_H", "refC_D", "refC_A"):
        out[c] = np.nan
    out["ref_book"] = pd.Series(["none_available"] * len(wc), index=wc.index, dtype="string")
    out["quoted_ah_line"] = np.nan
    out["quoted_ah_home"] = np.nan
    out["quoted_ah_away"] = np.nan
    out["quoted_ah_missing"] = pd.Series([True] * len(wc), index=wc.index, dtype="boolean")
    out["overround"] = np.nan
    out["underdog_side"] = pd.Series([pd.NA] * len(wc), index=wc.index, dtype="string")
    out["o_dnb_underdog"] = np.nan

    out["synthetic_only"] = wc["synthetic_only"].astype("boolean")
    out["clv_defined"] = wc["clv_defined"].astype("boolean")
    out["odds_status"] = "pending"

    out["qual_state_home"] = wc["home_qual_state"].astype("string")
    out["qual_state_away"] = wc["away_qual_state"].astype("string")
    out["dead_rubber"] = wc["dead_rubber"].astype("boolean")

    out["data_vendor"] = data_vendor
    out["snapshot_date"] = snapshot_date
    return out


def _wc_host_neutral(
    wc: pd.DataFrame, mj_results: pd.DataFrame | None
) -> tuple[pd.Series, pd.Series]:
    """Return (host, neutral) per WC row from the martj42 `neutral` flag.

    martj42 records a per-match `neutral` boolean (True at a neutral venue). A WC
    match with neutral=False is a HOST match (one side is at home). Matched
    order-insensitively on (date, frozenset{normalized names}); unmatched rows fall
    back to neutral=True (the WC default) with host=null. No fabrication: an
    unmatched row is conservatively the WC-typical neutral case, flagged by a null
    host so the stratum is resolved when venue data is joined.
    """
    import unicodedata

    n = len(wc)
    if mj_results is None or "neutral" not in mj_results.columns:
        return (
            pd.Series([pd.NA] * n, index=wc.index, dtype="string"),
            pd.Series([True] * n, index=wc.index, dtype="boolean"),
        )

    def _norm(name: str) -> str:
        s = unicodedata.normalize("NFKD", str(name))
        s = "".join(c for c in s if not unicodedata.combining(c))
        return " ".join(s.lower().split())

    mj = mj_results.copy()
    mj["date_str"] = pd.to_datetime(mj["date"]).dt.strftime("%Y-%m-%d")
    idx: dict[tuple[str, frozenset[str]], bool] = {}
    for _, m in mj.iterrows():
        if pd.isna(m.get("home_score")) or pd.isna(m.get("away_score")):
            continue
        key = (m["date_str"], frozenset({_norm(m["home_team"]), _norm(m["away_team"])}))
        idx[key] = bool(m["neutral"])

    host_vals: list[Any] = []
    neutral_vals: list[Any] = []
    for date, h, a in zip(
        wc["match_date"], wc["home_team_name"], wc["away_team_name"], strict=True
    ):
        key = (str(date), frozenset({_norm(h), _norm(a)}))
        is_neutral = idx.get(key)
        if is_neutral is None:
            host_vals.append(pd.NA)
            neutral_vals.append(True)
        else:
            neutral_vals.append(is_neutral)
            host_vals.append("neutral" if is_neutral else "host")
    return (
        pd.Series(host_vals, index=wc.index, dtype="string"),
        pd.Series(neutral_vals, index=wc.index, dtype="boolean"),
    )


@dataclass
class AssembleResult:
    """The assembled canonical panel + provenance for the ReproLog."""

    panel: pd.DataFrame
    n_league: int
    n_wc: int
    panel_path: Path | None
    content_sha256: str
    dataset_checksums: dict[str, str]


def assemble_matches(
    league_panel: pd.DataFrame,
    wc_panel: pd.DataFrame,
    *,
    league_vendor: str,
    wc_vendor: str,
    snapshot_date: str,
    mj_results: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Concatenate the league + WC blocks into the canonical schema, sorted by
    (block, date, match_id) for deterministic downstream reductions (ARCH §3.2)."""
    lg = league_to_canonical(league_panel, data_vendor=league_vendor, snapshot_date=snapshot_date)
    wc = wc_to_canonical(
        wc_panel, data_vendor=wc_vendor, snapshot_date=snapshot_date, mj_results=mj_results
    )
    # Ensure every canonical column exists in both blocks before concat (so the
    # concat never has to infer dtypes from an all-NA / absent column -- the source
    # of the pandas empty/all-NA concat FutureWarning).
    for sub in (lg, wc):
        for c in CANONICAL_COLUMNS:
            if c not in sub.columns:
                sub[c] = pd.NA
    lg = lg[list(CANONICAL_COLUMNS)]
    wc = wc[list(CANONICAL_COLUMNS)]
    panel = pd.concat([lg, wc], ignore_index=True)
    return panel.sort_values(["block", "date", "match_id"], kind="stable").reset_index(drop=True)


def content_sha256(panel: pd.DataFrame) -> str:
    """Deterministic content checksum: sorted DATA columns, LF CSV rendering (ARCH §3.2).

    Parquet bytes are not byte-stable across writer versions, so the dataset
    checksum is taken over a canonical CSV serialization a reviewer can reproduce
    (plan task 10c LF normalization).

    The run-metadata / provenance columns (``RUN_METADATA_COLUMNS`` =
    ``snapshot_date``/``data_vendor``; DATA §7.1) are EXCLUDED from the hash: they
    are a function of when/how the assembly ran (e.g. ``snapshot_date =
    datetime.now().date()``), not of the point-in-time source data, so including
    them made the headline matches.parquet hash a function of the wall-clock
    calendar date -- byte-identical inputs hashing differently on different days
    (the major Phase-1 finding). The content SHA now fingerprints ONLY the
    point-in-time data columns and is invariant to the run date / vendor label; the
    provenance fields remain in the panel + the ReproLog (keys 6/7).
    """
    cols = sorted(c for c in panel.columns if c not in RUN_METADATA_COLUMNS)
    return sha256_text(panel[cols].to_csv(index=False, lineterminator="\n"))


def write_matches(panel: pd.DataFrame, *, processed_dir: Path = PROCESSED_DIR) -> tuple[Path, str]:
    """Write data/processed/matches.parquet + a content checksum (returns path, sha)."""
    processed_dir.mkdir(parents=True, exist_ok=True)
    out = processed_dir / "matches.parquet"
    panel.to_parquet(out, index=False)
    return out, content_sha256(panel)
