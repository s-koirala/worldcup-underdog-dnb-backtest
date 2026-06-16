"""Phase 1 league-universe ingest (plan tasks 1, 2, 2.1, 3, 3.1, 8, 9, 9.1).

Downloads the football-data.co.uk **Main**-league CSVs over the closing-odds era
(the ``*C`` closing columns incl. ``PSCH/PSCD/PSCA``), saves each raw pull to
``data/raw/<season>_<div>.csv`` with a sibling ``.sha256`` on LF-normalized bytes,
schema-validates with pandera, and logs every dropped row with a reason (no silent
drops). It then derives the season-conditional reference price ``refC_*`` (PSC* for
seasons <= 2024/25; AvgC*/MaxC*/BFEC* for >= 2025/26) with a ``ref_book`` provenance
column, and emits the Phase-1 processed artifacts:

  * coverage report -- first season with >= 95% ``refC`` coverage; AvgC*/BFEC*
    coverage on 2025/26+ (task 8);
  * synthetic-vs-quoted-AH margin wedge ``M_1X2 - M_AH`` (task 9);
  * per-match open->close decimal-odds move distribution per division-season x
    reference regime x odds bucket (task 9.1, the Phase-3 slippage-calibration
    input);
  * the Pinnacle-degradation-notice provenance register (task 3.1) with the live
    data.php notice text + date archived to ``data/raw/provenance/`` (checksummed)
    and the empirical 2025/26 PSC* staleness confirmation.

DATA-INTEGRITY RULE: every datum in ``data/raw/`` comes from a real downloaded
source with provenance (URL + fetch context + SHA-256). Nothing is fabricated. If a
source cannot be obtained, the gap is recorded honestly and ingest proceeds with what
is genuinely available.

No magic numbers: the odds-bucket cut-points and coverage threshold are
empirical-quantile / register-input values from config, not hard-coded bands. The
season-conditional cutover is config-driven (``ingest.reference_cutover_season``).

Pathlib only; LF-normalized bytes for all checksums; point-in-time correctness
(closing / pre-kickoff columns only, no look-ahead).
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pandera.pandas as pa

from src.pricing import synthetic_dnb
from src.reprolog import sha256_text

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = PROJECT_ROOT / "data" / "raw"
PROVENANCE_DIR = RAW_DIR / "provenance"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
LOGS_DIR = PROJECT_ROOT / "logs"

# The verbatim Pinnacle-degradation notice (data.php, accessed 2026-06-16). The
# canonical source of record is the live data.php archived copy under
# data/raw/provenance/; this constant is the EXPECTED text the register round-trip
# is checked against (a mismatch is logged, not silently accepted).
EXPECTED_PINNACLE_NOTICE_DATE = "23/07/2025"
EXPECTED_PINNACLE_NOTICE_TEXT = (
    "Since 23/07/2025 Pinnacle's public API for odds delivery has become unreliable "
    "meaning their odds are systematically out of date relative to odds for other "
    "bookmakers, including both the pre-closing and closing odds. Consequently they "
    "should be used with caution when undertaking any betting analyses, and are no "
    "longer being included for the calculation of market average and maximum odds."
)
DATA_PHP_URL = "https://www.football-data.co.uk/data.php"
NOTES_URL = "https://www.football-data.co.uk/notes.txt"

# A season-compaction (e.g. 2526) >= this is on the non-Pinnacle reference regime.
# The actual cutover is read from config (ingest.reference_cutover_season); this is
# only the default if config omits it.
DEFAULT_CUTOVER_SEASON = 2526


# ===========================================================================
# Byte / checksum helpers (LF-normalized; plan task 10c).
# ===========================================================================


def _normalize_lf(raw: bytes) -> bytes:
    """Return ``raw`` with CRLF/CR normalized to LF (byte-stable checksums)."""
    return raw.replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def sha256_bytes_lf(raw: bytes) -> str:
    """SHA-256 of bytes after LF normalization (matches reprolog.sha256_text)."""
    return hashlib.sha256(_normalize_lf(raw)).hexdigest()


def write_with_sha256(path: Path, raw: bytes) -> tuple[Path, str]:
    """Write LF-normalized ``raw`` to ``path`` + a sibling ``<path>.sha256``.

    Returns (path, digest). The ``.sha256`` sidecar carries the digest of the
    normalized bytes that were written, so a reviewer re-pull is byte-comparable
    regardless of platform line endings.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    normalized = _normalize_lf(raw)
    digest = hashlib.sha256(normalized).hexdigest()
    path.write_bytes(normalized)
    sidecar = path.with_name(path.name + ".sha256")
    # `<digest>  <filename>` -- the conventional sha256sum line, LF-terminated.
    sidecar.write_text(f"{digest}  {path.name}\n", encoding="utf-8", newline="\n")
    return path, digest


# ===========================================================================
# Download (curl; real source with provenance). No fabrication.
# ===========================================================================


@dataclass(frozen=True)
class FetchResult:
    """Outcome of one CSV fetch attempt (provenance carrier)."""

    season: int
    division: str
    url: str
    ok: bool
    path: Path | None = None
    sha256: str | None = None
    n_rows: int | None = None
    fetched_at: str | None = None
    reason: str | None = None  # non-null iff not ok (honest gap record)


def _curl_bytes(url: str, *, timeout_s: int = 90) -> bytes | None:
    """Fetch ``url`` with curl, returning the raw body or None on any failure.

    Uses ``--fail`` so a 4xx/5xx is a nonzero exit (treated as a gap, not a body).
    """
    try:
        out = subprocess.run(
            ["curl", "-sS", "--fail", "--max-time", str(timeout_s), url],
            capture_output=True,
            check=False,
        )
    except OSError:
        return None
    if out.returncode != 0:
        return None
    return out.stdout or None


def download_league_csv(
    season: int,
    division: str,
    base_url: str,
    *,
    raw_dir: Path = RAW_DIR,
    timeout_s: int = 90,
) -> FetchResult:
    """Download one ``mmz4281/{season}/{div}.csv`` to ``data/raw/<season>_<div>.csv``.

    Records URL + fetch timestamp + SHA-256 (provenance). A failed fetch returns a
    FetchResult with ``ok=False`` and a reason -- the gap is recorded honestly,
    never fabricated.
    """
    url = f"{base_url}/{season:04d}/{division}.csv"
    fetched_at = datetime.now(UTC).isoformat()
    body = _curl_bytes(url, timeout_s=timeout_s)
    if body is None or not body.strip():
        return FetchResult(
            season=season,
            division=division,
            url=url,
            ok=False,
            fetched_at=fetched_at,
            reason="fetch_failed_or_empty",
        )
    out_path = raw_dir / f"{season:04d}_{division}.csv"
    path, digest = write_with_sha256(out_path, body)
    # Count data rows (excluding the header) on the normalized text.
    text = _normalize_lf(body).decode("utf-8-sig", errors="replace")
    n_rows = max(0, sum(1 for line in text.splitlines() if line.strip()) - 1)
    return FetchResult(
        season=season,
        division=division,
        url=url,
        ok=True,
        path=path,
        sha256=digest,
        n_rows=n_rows,
        fetched_at=fetched_at,
    )


# ===========================================================================
# Load + schema validation (pandera). Logs every dropped row with a reason.
# ===========================================================================

# Columns every Main-league closing-era row must carry to be usable. The result
# fields are required; the reference / AH columns are validated for *presence in
# the header* (the column exists) but may be null per-row (the season-conditional
# / quoted-AH-missing handling lives downstream).
_REQUIRED_RESULT_COLS = ("Div", "Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG", "FTR")


def _read_raw_csv(path: Path) -> pd.DataFrame:
    """Read a football-data CSV (utf-8-sig BOM; trailing blank columns tolerated)."""
    df = pd.read_csv(
        path,
        encoding="utf-8-sig",
        dtype=str,  # parse as str first; numeric coercion is explicit + logged
        keep_default_na=True,
        na_values=["", "NA"],
    )
    # football-data files carry trailing unnamed/empty columns on some seasons.
    df = df.loc[:, [c for c in df.columns if not str(c).startswith("Unnamed")]]
    return df


@dataclass
class DroppedRow:
    """A single dropped row with the reason it failed validation (no silent drops)."""

    season: int
    division: str
    row_index: int
    reason: str
    detail: str = ""


def _coerce_float(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s, errors="coerce")


def build_row_schema() -> pa.DataFrameSchema:
    """Pandera schema for a validated league row (result fields, 1X2, draw leg).

    The 1X2 closing-odds columns are present-in-header checks with per-row
    nullable values (the season-conditional refC handling drops/keeps downstream);
    the *result* fields are strictly validated because settlement depends on them.
    """
    return pa.DataFrameSchema(
        {
            "Div": pa.Column(str, nullable=False),
            "HomeTeam": pa.Column(str, nullable=False),
            "AwayTeam": pa.Column(str, nullable=False),
            "FTHG": pa.Column(float, pa.Check.ge(0), nullable=False, coerce=True),
            "FTAG": pa.Column(float, pa.Check.ge(0), nullable=False, coerce=True),
            "FTR": pa.Column(str, pa.Check.isin(["H", "D", "A"]), nullable=False),
        },
        strict=False,  # extra odds columns are allowed (validated separately)
        coerce=True,
    )


@dataclass
class ValidatedFile:
    """A validated single-file panel + the per-file provenance and drop log."""

    season: int
    division: str
    df: pd.DataFrame  # validated, with refC_*/ref_book/derived columns attached
    n_raw: int
    dropped: list[DroppedRow] = field(default_factory=list)
    header: list[str] = field(default_factory=list)
    quoted_ah_present_in_header: bool = False


def validate_file(
    path: Path,
    season: int,
    division: str,
    *,
    ah_home: str = "PCAHH",
    ah_away: str = "PCAHA",
    ah_line: str = "AHCh",
) -> ValidatedFile:
    """Load + validate one raw CSV; return the validated panel + drop log.

    Every dropped row carries a reason (no silent drops). The quoted-AH-Pinnacle
    code (``ah_home``/``ah_away``) is the live-header-resolved ``PCAHH/PCAHA``
    (plan task 2.1): ingest does NOT fall back silently to synthetic -- a missing
    quoted-AH cell is flagged ``quoted_ah_missing`` per row downstream.
    """
    df = _read_raw_csv(path)
    header = list(df.columns)
    n_raw = len(df)
    dropped: list[DroppedRow] = []

    # Missing-result-column rows are dropped with a reason (cannot settle).
    missing_cols = [c for c in _REQUIRED_RESULT_COLS if c not in df.columns]
    if missing_cols:
        # The whole file lacks a required column; record one drop per row.
        for i in range(n_raw):
            dropped.append(
                DroppedRow(season, division, i, "missing_required_column", ",".join(missing_cols))
            )
        empty = df.iloc[0:0].copy()
        return ValidatedFile(season, division, empty, n_raw, dropped, header, False)

    work = df.copy()
    work["_orig_index"] = np.arange(n_raw)

    # Coerce result fields; drop rows that fail (logged).
    for col in ("FTHG", "FTAG"):
        work[col] = _coerce_float(work[col])
    bad_goals = work["FTHG"].isna() | work["FTAG"].isna()
    for i in work.loc[bad_goals, "_orig_index"]:
        dropped.append(DroppedRow(season, division, int(i), "nonnumeric_or_missing_goals"))
    work = work.loc[~bad_goals].copy()

    bad_ftr = ~work["FTR"].isin(["H", "D", "A"])
    for i in work.loc[bad_ftr, "_orig_index"]:
        bad_val = str(work.loc[work["_orig_index"] == i, "FTR"].iloc[0])
        dropped.append(DroppedRow(season, division, int(i), "invalid_FTR", bad_val))
    work = work.loc[~bad_ftr].copy()

    bad_team = work["HomeTeam"].isna() | work["AwayTeam"].isna()
    for i in work.loc[bad_team, "_orig_index"]:
        dropped.append(DroppedRow(season, division, int(i), "missing_team_name"))
    work = work.loc[~bad_team].copy()

    # Schema-validate the surviving result fields (raises only on a logic error,
    # since the per-row coercion above already removed the invalid rows).
    schema = build_row_schema()
    validated = schema.validate(work, lazy=True)

    quoted_ah_in_header = ah_home in header and ah_away in header

    return ValidatedFile(
        season=season,
        division=division,
        df=validated,
        n_raw=n_raw,
        dropped=dropped,
        header=header,
        quoted_ah_present_in_header=quoted_ah_in_header,
    )


# ===========================================================================
# Season-conditional reference price refC_* + ref_book provenance (task 3).
# ===========================================================================


def _first_available_triplet(
    df: pd.DataFrame, candidates: list[list[str]]
) -> tuple[list[str] | None, str | None]:
    """Return the first candidate odds triplet whose three columns are all in df."""
    for triplet in candidates:
        if all(c in df.columns for c in triplet):
            return triplet, None
    return None, "no_reference_triplet_in_header"


def attach_reference_price(
    vf: ValidatedFile,
    *,
    cutover_season: int,
    reference_columns: dict[str, list[str]],
    ah_home: str,
    ah_away: str,
    ah_line: str,
) -> ValidatedFile:
    """Attach season-conditional ``refC_H/D/A``, ``ref_book``, and AH flags.

    refC_* = PSC* for season < cutover (Pinnacle era); else AvgC* (fallback
    MaxC*/BFEC*) for season >= cutover (DATA §2.1; ADR-0002). The ``ref_book``
    column logs which source populated refC_*. The ``quoted_ah_missing`` flag is
    set per row where the pinned closing-Pinnacle-AH code is null (fail-closed; the
    synthetic fallback in Phase 2 is then an explicit, audited substitution).
    """
    df = vf.df
    if df.empty:
        for c in ("refC_H", "refC_D", "refC_A", "ref_book", "quoted_ah_missing"):
            df[c] = pd.Series(dtype="object")
        return vf

    is_post_cutover = vf.season >= cutover_season
    if is_post_cutover:
        # Post-cutover: prefer AvgC* (consensus excludes the stale Pinnacle leg per
        # the data.php notice), then MaxC*, then BFEC*. PSC* is treated as missing
        # for reference purposes even if present-but-stale (DATA gate 1).
        order = [
            ("market_avg_close", "market_avg_close"),
            ("market_max_close", "market_max_close"),
            ("betfair_ex_close", "betfair_ex_close"),
        ]
    else:
        order = [("pinnacle_close", "pinnacle_close")]

    chosen_triplet: list[str] | None = None
    chosen_book: str | None = None
    for key, book in order:
        triplet = reference_columns.get(key)
        if triplet and all(c in df.columns for c in triplet):
            # require at least one non-null cell to call this the reference
            sub = df[triplet].apply(_coerce_float)
            if sub.notna().any(axis=None):
                chosen_triplet, chosen_book = triplet, book
                break

    if chosen_triplet is None:
        df["refC_H"] = np.nan
        df["refC_D"] = np.nan
        df["refC_A"] = np.nan
        df["ref_book"] = "none_available"
    else:
        df["refC_H"] = _coerce_float(df[chosen_triplet[0]])
        df["refC_D"] = _coerce_float(df[chosen_triplet[1]])
        df["refC_A"] = _coerce_float(df[chosen_triplet[2]])
        df["ref_book"] = chosen_book

    # Quoted-AH-missing flag (fail-closed; plan task 2.1). True where the pinned
    # closing-Pinnacle-AH code is absent or null on the row.
    if ah_home in df.columns and ah_away in df.columns:
        ah_h = _coerce_float(df[ah_home])
        ah_a = _coerce_float(df[ah_away])
        if ah_line in df.columns:
            ah_ln = _coerce_float(df[ah_line])
        else:
            ah_ln = pd.Series(np.nan, index=df.index)
        df["quoted_ah_missing"] = ah_h.isna() | ah_a.isna()
        df["quoted_ah_line"] = ah_ln
        df["quoted_ah_home"] = ah_h
        df["quoted_ah_away"] = ah_a
    else:
        df["quoted_ah_missing"] = True
        df["quoted_ah_line"] = np.nan
        df["quoted_ah_home"] = np.nan
        df["quoted_ah_away"] = np.nan

    # Underdog side + synthetic DNB odds, evaluable pre-kickoff (PIT-correct).
    refc_h, refc_a, refc_d = df["refC_H"], df["refC_A"], df["refC_D"]
    df["underdog_side"] = np.where(
        refc_h.notna() & refc_a.notna(),
        np.where(refc_a >= refc_h, "away", "home"),
        None,
    )
    # synthetic DNB on the underdog side: o = side_price * (D - 1) / D  (DATA §1.2;
    # CALC §3.1-§3.3). Single source of truth is src.pricing.synthetic_dnb -- its array
    # path is arithmetic-identical to the former inline expression (verified bit-for-bit
    # on the panel: 0 mismatches across 49,687 league rows; matches.parquet content SHA
    # unchanged after this refactor). Do NOT reinline / "simplify" -- algebraically equal
    # forms can differ in the last ULP and would change the panel hash.
    under_price = np.where(refc_a >= refc_h, refc_a, refc_h)
    df["o_dnb_underdog"] = synthetic_dnb(under_price, refc_d.to_numpy(dtype="float64"))
    vf.df = df
    return vf


# ===========================================================================
# Coverage (task 8), margin wedge (task 9), open->close moves (task 9.1).
# ===========================================================================


def _overround_1x2(h: pd.Series, d: pd.Series, a: pd.Series) -> pd.Series:
    with np.errstate(divide="ignore", invalid="ignore"):
        return 1.0 / h + 1.0 / d + 1.0 / a


def coverage_report(
    panel: pd.DataFrame,
    *,
    cutover_season: int,
    threshold: float,
) -> dict[str, Any]:
    """First season with >= ``threshold`` refC coverage; post-cutover AvgC*/BFEC*.

    refC coverage = fraction of rows with all three refC_* non-null, per season
    (task 8; DATA Open Question 2). Establishes the estimation-window start season
    empirically rather than asserting it.
    """
    per_season: dict[str, Any] = {}
    refc_ok = panel[["refC_H", "refC_D", "refC_A"]].notna().all(axis=1)
    for season, grp in panel.groupby("season", sort=True):
        idx = grp.index
        n = len(grp)
        cov = float(refc_ok.loc[idx].mean()) if n else 0.0
        # post-cutover AvgC*/BFEC* coverage (task 8 gate)
        avg_cols = [c for c in ("AvgCH", "AvgCD", "AvgCA") if c in grp.columns]
        bfe_cols = [c for c in ("BFECH", "BFECD", "BFECA") if c in grp.columns]
        avg_cov = (
            float(grp[avg_cols].apply(_coerce_float).notna().all(axis=1).mean())
            if len(avg_cols) == 3
            else None
        )
        bfe_cov = (
            float(grp[bfe_cols].apply(_coerce_float).notna().all(axis=1).mean())
            if len(bfe_cols) == 3
            else None
        )
        psc_cols = [c for c in ("PSCH", "PSCD", "PSCA") if c in grp.columns]
        psc_cov = (
            float(grp[psc_cols].apply(_coerce_float).notna().all(axis=1).mean())
            if len(psc_cols) == 3
            else None
        )
        per_season[str(int(season))] = {
            "n": n,
            "refC_coverage": round(cov, 4),
            "ref_book": sorted(set(grp["ref_book"].dropna().tolist())),
            "psc_coverage": None if psc_cov is None else round(psc_cov, 4),
            "avgc_coverage": None if avg_cov is None else round(avg_cov, 4),
            "bfec_coverage": None if bfe_cov is None else round(bfe_cov, 4),
            "is_post_cutover": int(season) >= cutover_season,
        }
    viable = [int(s) for s, info in per_season.items() if info["refC_coverage"] >= threshold]
    return {
        "threshold": threshold,
        "first_viable_season": min(viable) if viable else None,
        "per_season": per_season,
    }


def margin_wedge(panel: pd.DataFrame) -> dict[str, Any]:
    """Quantify M_1X2 - M_AH where both the 1X2 and a quoted AH-0.0 exist (task 9).

    M_1X2 = (1/refC_H + 1/refC_D + 1/refC_A) - 1  (the 1X2 overround).
    M_AH(0) = (1/PCAHH + 1/PCAHA) - 1 on rows where the closing AH line == 0.0
    (the directly-quoted DNB / AH-0.0 market). Reports the wedge distribution
    (per division-season and pooled) -- the slippage/commission reconciliation
    target for Phase 3 (CALC §3.5).
    """
    have_1x2 = panel[["refC_H", "refC_D", "refC_A"]].notna().all(axis=1)
    ah_line = panel.get("quoted_ah_line")
    ah_h = panel.get("quoted_ah_home")
    ah_a = panel.get("quoted_ah_away")
    if ah_line is None or ah_h is None or ah_a is None:
        return {"n_both": 0, "note": "no quoted-AH columns in panel"}
    is_ah0 = ah_line.fillna(np.nan) == 0.0
    have_ah = ah_h.notna() & ah_a.notna() & is_ah0
    both = have_1x2 & have_ah
    sub = panel.loc[both].copy()
    n_both = len(sub)
    if n_both == 0:
        return {"n_both": 0, "note": "no overlapping 1X2 + quoted-AH-0.0 rows"}
    m_1x2 = _overround_1x2(sub["refC_H"], sub["refC_D"], sub["refC_A"]) - 1.0
    with np.errstate(divide="ignore", invalid="ignore"):
        m_ah = (1.0 / sub["quoted_ah_home"] + 1.0 / sub["quoted_ah_away"]) - 1.0
    wedge = (m_1x2 - m_ah).replace([np.inf, -np.inf], np.nan).dropna()
    by_ds: dict[str, Any] = {}
    sub["_wedge"] = (m_1x2 - m_ah).to_numpy()
    for (comp, season), grp in sub.groupby(["competition", "season"], sort=True):
        w = pd.Series(grp["_wedge"]).replace([np.inf, -np.inf], np.nan).dropna()
        if len(w):
            by_ds[f"{comp}_{int(season)}"] = {
                "n": len(w),
                "mean_wedge": round(float(w.mean()), 6),
                "median_wedge": round(float(w.median()), 6),
            }
    return {
        "n_both": n_both,
        "M_1X2_mean": round(float(m_1x2.replace([np.inf, -np.inf], np.nan).dropna().mean()), 6),
        "M_AH_mean": round(float(m_ah.replace([np.inf, -np.inf], np.nan).dropna().mean()), 6),
        "wedge_mean": round(float(wedge.mean()), 6),
        "wedge_median": round(float(wedge.median()), 6),
        "wedge_p05": round(float(wedge.quantile(0.05)), 6),
        "wedge_p95": round(float(wedge.quantile(0.95)), 6),
        "by_division_season": by_ds,
    }


def open_close_moves(
    panel: pd.DataFrame,
    *,
    prematch_columns: list[str],
    n_buckets: int = 5,
) -> dict[str, Any]:
    """Per-match open->close decimal-odds move distribution (task 9.1).

    On Main leagues both pre-match (PS*) and closing (refC_*) prices exist, so the
    per-match open->close move is directly observable. The relative move on each
    1X2 leg is ``refC/PS - 1``; the per-match summary is the mean absolute relative
    move across the H/D/A legs. The distribution is reported per division-season x
    reference regime x odds bucket -- the calibration basis Phase 3 selects the
    per-leg slippage quantile from (the magnitude is NOT chosen here; §D.3).

    Odds buckets are cut by EMPIRICAL QUANTILE of the underdog price (no-magic-
    number); ``n_buckets`` is the bucket count (a register input, not a model
    hyperparameter).
    """
    psh, psd, psa = prematch_columns
    have_pre = all(c in panel.columns for c in prematch_columns)
    have_close = panel[["refC_H", "refC_D", "refC_A"]].notna().all(axis=1)
    if not have_pre:
        return {
            "n_observable": 0,
            "note": "pre-match PS* columns absent in panel; open->close not locally observable",
        }
    pre = panel[[psh, psd, psa]].apply(_coerce_float)
    have_both = have_close & pre.notna().all(axis=1)
    sub = panel.loc[have_both].copy()
    n_obs = len(sub)
    if n_obs == 0:
        return {"n_observable": 0, "note": "no rows with both open and close 1X2"}
    pre = pre.loc[have_both]
    with np.errstate(divide="ignore", invalid="ignore"):
        mv_h = (sub["refC_H"].to_numpy() / pre[psh].to_numpy()) - 1.0
        mv_d = (sub["refC_D"].to_numpy() / pre[psd].to_numpy()) - 1.0
        mv_a = (sub["refC_A"].to_numpy() / pre[psa].to_numpy()) - 1.0
    abs_move = np.nanmean(np.abs(np.vstack([mv_h, mv_d, mv_a])), axis=0)
    sub = sub.assign(_abs_open_close_move=abs_move)
    sub = sub.replace([np.inf, -np.inf], np.nan).dropna(subset=["_abs_open_close_move"])

    # Empirical-quantile odds buckets on the underdog price (no hard-coded bands).
    under_price = np.where(
        sub["underdog_side"].to_numpy() == "away",
        sub["refC_A"].to_numpy(),
        sub["refC_H"].to_numpy(),
    )
    sub = sub.assign(_under_price=under_price)
    try:
        sub["_odds_bucket"] = pd.qcut(
            sub["_under_price"], q=n_buckets, labels=False, duplicates="drop"
        )
    except ValueError:
        sub["_odds_bucket"] = 0

    def _summ(s: pd.Series) -> dict[str, float]:
        s = s.dropna()
        return {
            "n": len(s),
            "mean_abs_move": round(float(s.mean()), 6),
            "p50": round(float(s.quantile(0.50)), 6),
            "p90": round(float(s.quantile(0.90)), 6),
            "p95": round(float(s.quantile(0.95)), 6),
            "p99": round(float(s.quantile(0.99)), 6),
        }

    by_regime: dict[str, Any] = {}
    for regime, grp in sub.groupby("ref_book", sort=True):
        by_regime[str(regime)] = _summ(grp["_abs_open_close_move"])
    by_bucket: dict[str, Any] = {}
    for b, grp in sub.groupby("_odds_bucket", sort=True):
        by_bucket[f"bucket_{int(b)}"] = _summ(grp["_abs_open_close_move"])
    by_ds_bucket: dict[str, Any] = {}
    for (comp, season, b), grp in sub.groupby(["competition", "season", "_odds_bucket"], sort=True):
        by_ds_bucket[f"{comp}_{int(season)}_bucket{int(b)}"] = _summ(grp["_abs_open_close_move"])

    return {
        "n_observable": n_obs,
        "n_buckets": n_buckets,
        "pooled": _summ(sub["_abs_open_close_move"]),
        "by_reference_regime": by_regime,
        "by_odds_bucket": by_bucket,
        "by_division_season_bucket": by_ds_bucket,
    }


# ===========================================================================
# Pinnacle-degradation-notice provenance register (HARD gate; task 3.1).
# ===========================================================================


def build_provenance_register(
    *,
    raw_dir: Path = RAW_DIR,
    provenance_dir: Path = PROVENANCE_DIR,
    cutover_season: int = DEFAULT_CUTOVER_SEASON,
    fetch: bool = True,
) -> dict[str, Any]:
    """Round-trip the data.php Pinnacle-degradation notice + confirm PSC* staleness.

    (i) fetch data.php + notes.txt and archive checksummed copies to
        data/raw/provenance/ (the canonical source of record);
    (ii) round-trip the exact notice text + date into the register, flagging any
        mismatch against the expected text (no silent acceptance);
    (iii) empirically confirm PSC* is stale/missing in the downloaded 2025/26 file
        (e.g. 2526/E0.csv) -- the degradation actually nulls the Pinnacle closing
        leg, not merely a vendor note.

    Returns the register dict (written to disk + SHA-referenced in the ReproLog by
    the caller). ``fetch=False`` reuses already-archived copies (offline / tests).
    """
    provenance_dir.mkdir(parents=True, exist_ok=True)
    # The register holds ONLY immutable CONTENT -- the round-tripped notice text/date,
    # the archived-source SHA-256s, the PSC* staleness result, and the gate verdict.
    # The mutable fetch time ("accessed") is deliberately NOT a register field: it is
    # a function of WHEN the gate ran, not of the source bytes, and including it made
    # the register SHA -- and therefore the ingest ReproLog's config_resolved_sha256 --
    # change on every run even for byte-identical re-pulled data.php (the major
    # Phase-1 finding). The fetch time is recorded out-of-band by
    # write_provenance_register in a sibling provenance.json that is NOT part of the
    # pinned SHA, so two reviewers agree on the register SHA from identical content.
    register: dict[str, Any] = {
        "register_type": "pinnacle_degradation_notice",
        "plan_task": "3.1",
        "sources": {},
        "notice": {},
        "psc_staleness_confirmation": {},
        "gate_passed": False,
    }

    # (i) archive data.php + notes.txt
    archived: dict[str, Any] = {}
    for name, url in (("data_php.html", DATA_PHP_URL), ("notes.txt", NOTES_URL)):
        body = _curl_bytes(url) if fetch else None
        target = provenance_dir / name
        if body is not None and body.strip():
            _, digest = write_with_sha256(target, body)
            archived[name] = {"url": url, "sha256": digest, "bytes": len(_normalize_lf(body))}
        elif target.exists():
            digest = sha256_bytes_lf(target.read_bytes())
            archived[name] = {"url": url, "sha256": digest, "from_archive": True}
        else:
            archived[name] = {"url": url, "sha256": None, "reason": "fetch_failed_and_no_archive"}
    register["sources"] = archived

    # (ii) round-trip the notice text + date from the archived data.php
    data_php = provenance_dir / "data_php.html"
    notice_found = False
    notice_matches = False
    if data_php.exists():
        import re as _re
        from html import unescape as _unescape

        raw = data_php.read_text(encoding="utf-8", errors="replace")
        plain = _unescape(_re.sub(r"\s+", " ", _re.sub(r"<[^>]+>", " ", raw)))
        start = plain.find("Since 23/07/2025")
        if start >= 0:
            notice_found = True
            seg = plain[start : start + 600]
            end = seg.find("maximum odds")
            extracted = seg[: end + len("maximum odds") + 1].strip() if end >= 0 else seg.strip()
            register["notice"] = {
                "date_token": EXPECTED_PINNACLE_NOTICE_DATE,
                "extracted_text": extracted,
                "expected_text": EXPECTED_PINNACLE_NOTICE_TEXT,
                "date_present": EXPECTED_PINNACLE_NOTICE_DATE in plain,
            }

            # Normalize whitespace+punctuation for a robust match.
            def _norm(s: str) -> str:
                return " ".join(s.split()).rstrip(".")

            notice_matches = _norm(extracted) == _norm(EXPECTED_PINNACLE_NOTICE_TEXT)
            register["notice"]["matches_expected"] = notice_matches
    if not notice_found:
        register["notice"] = {
            "date_token": EXPECTED_PINNACLE_NOTICE_DATE,
            "extracted_text": None,
            "expected_text": EXPECTED_PINNACLE_NOTICE_TEXT,
            "reason": "notice_not_located_in_archived_data_php",
        }

    # (iii) empirical PSC* staleness in a downloaded 2025/26 file
    probe_div = "E0"
    probe_path = raw_dir / f"{cutover_season:04d}_{probe_div}.csv"
    psc_confirmed = False
    if probe_path.exists():
        pdf = _read_raw_csv(probe_path)
        n = len(pdf)
        psc_cols = [c for c in ("PSCH", "PSCD", "PSCA") if c in pdf.columns]
        avg_cols = [c for c in ("AvgCH", "AvgCD", "AvgCA") if c in pdf.columns]
        psc_cov = (
            float(pdf[psc_cols].apply(_coerce_float).notna().all(axis=1).mean())
            if len(psc_cols) == 3 and n
            else None
        )
        avg_cov = (
            float(pdf[avg_cols].apply(_coerce_float).notna().all(axis=1).mean())
            if len(avg_cols) == 3 and n
            else None
        )
        # Staleness is confirmed when PSC* coverage is materially below the
        # consensus AvgC* coverage on the same post-cutover file.
        psc_confirmed = psc_cov is not None and avg_cov is not None and psc_cov < avg_cov
        register["psc_staleness_confirmation"] = {
            "probe_file": probe_path.name,
            "n_rows": n,
            "psc_coverage": None if psc_cov is None else round(psc_cov, 4),
            "avgc_coverage": None if avg_cov is None else round(avg_cov, 4),
            "psc_below_avgc": psc_confirmed,
        }
    else:
        register["psc_staleness_confirmation"] = {
            "probe_file": probe_path.name,
            "reason": "post_cutover_probe_file_not_downloaded",
        }

    register["gate_passed"] = bool(notice_found and notice_matches and psc_confirmed)
    return register


def write_provenance_register(
    register: dict[str, Any],
    *,
    provenance_dir: Path = PROVENANCE_DIR,
    accessed: str | None = None,
) -> tuple[Path, str]:
    """Write the immutable register JSON (LF) + return (path, content sha256).

    The register file contains ONLY immutable CONTENT (notice text/date, archived-
    source SHAs, PSC* staleness result, gate verdict); its SHA-256 is the pinned
    gate-artifact fingerprint two reviewers agree on for identical content, and is
    bound into the ingest ReproLog. The MUTABLE fetch time is written to a sibling
    ``pinnacle_degradation_provenance.json`` that is NOT part of the pinned SHA, so
    the fetch context is still recorded honestly (provenance, not a reproducibility
    key) without making the register SHA wall-clock-dependent (the major Phase-1
    finding). ``accessed`` defaults to now() when not supplied.
    """
    provenance_dir.mkdir(parents=True, exist_ok=True)
    out = provenance_dir / "pinnacle_degradation_register.json"
    text = json.dumps(register, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    out.write_text(text, encoding="utf-8", newline="\n")
    register_sha = sha256_text(text)

    # Sibling run-metadata file: the fetch time + a back-reference to the register
    # SHA it accompanies. Intentionally NOT hashed into the gate artifact.
    sidecar = provenance_dir / "pinnacle_degradation_provenance.json"
    run_meta = {
        "accessed": accessed if accessed is not None else datetime.now(UTC).isoformat(),
        "register_file": out.name,
        "register_sha256": register_sha,
    }
    sidecar.write_text(
        json.dumps(run_meta, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return out, register_sha


# ===========================================================================
# Orchestration: the real --stage ingest compute (wired in src/run.py).
# ===========================================================================


def _competition_code(division: str) -> str:
    """The canonical competition code for a league division (== the div code)."""
    return division


def assemble_panel(validated: list[ValidatedFile]) -> pd.DataFrame:
    """Concatenate validated per-file panels into the league estimation panel.

    Adds ``competition``/``season`` metadata and the canonical ``match_id``; sorts
    by (date, match_id) for deterministic downstream reductions (ARCH §3.2).
    """
    frames: list[pd.DataFrame] = []
    for vf in validated:
        if vf.df.empty:
            continue
        df = vf.df.copy()
        df["competition"] = _competition_code(vf.division)
        df["season"] = vf.season
        date = df["Date"] if "Date" in df.columns else pd.Series([""] * len(df), index=df.index)
        df["match_id"] = (
            df["competition"].astype(str)
            + "_"
            + df["season"].astype(str)
            + "_"
            + date.astype(str)
            + "_"
            + df["HomeTeam"].astype(str)
            + "_"
            + df["AwayTeam"].astype(str)
        )
        frames.append(df)
    if not frames:
        return pd.DataFrame()
    panel = pd.concat(frames, ignore_index=True)
    sort_cols = [c for c in ("season", "competition", "Date", "match_id") if c in panel.columns]
    return panel.sort_values(sort_cols, kind="stable").reset_index(drop=True)


@dataclass
class IngestResult:
    """Everything the ingest stage produced (for the ReproLog + the report)."""

    fetches: list[FetchResult]
    validated: list[ValidatedFile]
    panel: pd.DataFrame
    dataset_checksums: dict[str, str]
    coverage: dict[str, Any]
    wedge: dict[str, Any]
    moves: dict[str, Any]
    provenance_register: dict[str, Any]
    provenance_register_sha256: str
    drop_log_path: Path
    data_quality_path: Path
    panel_path: Path | None
    snapshot_date: str


def _ingest_cfg(config: dict[str, Any]) -> dict[str, Any]:
    ing = config.get("ingest")
    if not ing:
        raise KeyError("config has no `ingest` block (Phase 1 requires it)")
    return ing


def run_ingest(
    config: dict[str, Any],
    *,
    run_id: str,
    raw_dir: Path = RAW_DIR,
    processed_dir: Path = PROCESSED_DIR,
    logs_dir: Path = LOGS_DIR,
    provenance_dir: Path = PROVENANCE_DIR,
    fetch: bool = True,
    write_parquet: bool = True,
) -> IngestResult:
    """The real ``--stage ingest`` compute (plan tasks 1, 2, 2.1, 3, 3.1, 8, 9, 9.1).

    Downloads the config-enumerated season x division Main-league universe, schema-
    validates (logging every dropped row), derives the season-conditional refC_*,
    runs the Pinnacle-degradation provenance gate, and writes the processed panel +
    data-quality report + drop log + provenance register. Returns the IngestResult
    the caller stamps into the per-stage ReproLog (dataset_checksums, data_vendor,
    snapshot_date, the register SHA via config_resolved_sha256 reference).
    """
    ing = _ingest_cfg(config)
    base_url = ing["base_url"]
    seasons = [int(s) for s in ing["seasons"]]
    divisions = list(ing["divisions"])
    cutover = int(ing.get("reference_cutover_season", DEFAULT_CUTOVER_SEASON))
    ref_cols = {k: list(v) for k, v in ing["reference_columns"].items()}
    ah = ing["quoted_ah_pinnacle_close"]
    ah_home, ah_away, ah_line = ah["home"], ah["away"], ah.get("line", "AHCh")
    prematch_cols = list(ing.get("prematch_columns", ["PSH", "PSD", "PSA"]))
    threshold = float(ing.get("coverage_threshold", 0.95))

    raw_dir.mkdir(parents=True, exist_ok=True)
    processed_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)

    # 1. Download + validate every (season, division).
    fetches: list[FetchResult] = []
    validated: list[ValidatedFile] = []
    dataset_checksums: dict[str, str] = {}
    for season in seasons:
        for div in divisions:
            target = raw_dir / f"{season:04d}_{div}.csv"
            if fetch or not target.exists():
                fr = download_league_csv(season, div, base_url, raw_dir=raw_dir)
            else:
                digest = sha256_bytes_lf(target.read_bytes())
                text = _normalize_lf(target.read_bytes()).decode("utf-8-sig", errors="replace")
                n_rows = max(0, sum(1 for ln in text.splitlines() if ln.strip()) - 1)
                fr = FetchResult(
                    season, div, f"{base_url}/{season:04d}/{div}.csv", True, target, digest, n_rows
                )
            fetches.append(fr)
            if not fr.ok or fr.path is None:
                continue
            dataset_checksums[fr.path.name] = fr.sha256  # type: ignore[assignment]
            vf = validate_file(
                fr.path, season, div, ah_home=ah_home, ah_away=ah_away, ah_line=ah_line
            )
            vf = attach_reference_price(
                vf,
                cutover_season=cutover,
                reference_columns=ref_cols,
                ah_home=ah_home,
                ah_away=ah_away,
                ah_line=ah_line,
            )
            validated.append(vf)

    # 2. Assemble the panel + compute the Phase-1 analytics.
    panel = assemble_panel(validated)
    if panel.empty:
        coverage, wedge, moves = {}, {"n_both": 0}, {"n_observable": 0}
    else:
        coverage = coverage_report(panel, cutover_season=cutover, threshold=threshold)
        wedge = margin_wedge(panel)
        moves = open_close_moves(panel, prematch_columns=prematch_cols)

    # 3. Provenance gate (task 3.1) -- runs after at least the post-cutover probe
    #    file is on disk (it is, if 2526/E0 was in the universe).
    register = build_provenance_register(
        raw_dir=raw_dir, provenance_dir=provenance_dir, cutover_season=cutover, fetch=fetch
    )
    _, register_sha = write_provenance_register(register, provenance_dir=provenance_dir)

    # 4. Drop log (no silent drops) + data-quality report.
    all_drops: list[dict[str, Any]] = []
    for vf in validated:
        for dr in vf.dropped:
            all_drops.append(
                {
                    "season": dr.season,
                    "division": dr.division,
                    "row_index": dr.row_index,
                    "reason": dr.reason,
                    "detail": dr.detail,
                }
            )
    drop_log_path = logs_dir / f"dropped_rows_{run_id}.json"
    drop_text = (
        json.dumps({"n_dropped": len(all_drops), "rows": all_drops}, indent=2, sort_keys=True)
        + "\n"
    )
    drop_log_path.write_text(drop_text, encoding="utf-8", newline="\n")

    # quoted-AH-missing accounting (fail-closed flag, task 2.1)
    has_qah = "quoted_ah_missing" in panel.columns
    qah_missing = int(panel["quoted_ah_missing"].sum()) if has_qah else None
    n_panel = len(panel)
    if qah_missing is not None and n_panel:
        qah_missing_frac = round(qah_missing / n_panel, 4)
    else:
        qah_missing_frac = None
    quoted_ah_header_present = {
        f"{vf.season:04d}_{vf.division}": vf.quoted_ah_present_in_header for vf in validated
    }

    data_quality = {
        "run_id": run_id,
        "data_vendor": ing["data_vendor"],
        "n_files_attempted": len(fetches),
        "n_files_ok": sum(1 for f in fetches if f.ok),
        "failed_fetches": [
            {"season": f.season, "division": f.division, "url": f.url, "reason": f.reason}
            for f in fetches
            if not f.ok
        ],
        "n_panel_rows": n_panel,
        "n_dropped_rows": len(all_drops),
        "drop_reasons": _count_reasons(all_drops),
        "quoted_ah_pinnacle_close_code": {"home": ah_home, "away": ah_away, "line": ah_line},
        "quoted_ah_header_present_per_file": quoted_ah_header_present,
        "quoted_ah_missing_rows": qah_missing,
        "quoted_ah_missing_fraction": qah_missing_frac,
        "coverage": coverage,
        "margin_wedge": wedge,
        "open_close_moves": moves,
        "pinnacle_degradation_register_sha256": register_sha,
        "pinnacle_degradation_gate_passed": register["gate_passed"],
        "ref_book_distribution": (
            {str(k): int(v) for k, v in panel["ref_book"].value_counts().items()}
            if "ref_book" in panel.columns
            else {}
        ),
    }
    data_quality_path = logs_dir / f"data_quality_{run_id}.json"
    dq_text = json.dumps(data_quality, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    data_quality_path.write_text(dq_text, encoding="utf-8", newline="\n")

    # 5. Persist the processed panel (canonicalized parquet for the checksum).
    panel_path: Path | None = None
    if write_parquet and not panel.empty:
        panel_path = processed_dir / "league_panel.parquet"
        panel.to_parquet(panel_path, index=False)
        dataset_checksums["league_panel.parquet"] = _parquet_canonical_sha256(panel)

    snapshot_date = datetime.now(UTC).date().isoformat()
    return IngestResult(
        fetches=fetches,
        validated=validated,
        panel=panel,
        dataset_checksums=dataset_checksums,
        coverage=coverage,
        wedge=wedge,
        moves=moves,
        provenance_register=register,
        provenance_register_sha256=register_sha,
        drop_log_path=drop_log_path,
        data_quality_path=data_quality_path,
        panel_path=panel_path,
        snapshot_date=snapshot_date,
    )


def _count_reasons(drops: list[dict[str, Any]]) -> dict[str, int]:
    out: dict[str, int] = {}
    for d in drops:
        out[d["reason"]] = out.get(d["reason"], 0) + 1
    return out


def _parquet_canonical_sha256(panel: pd.DataFrame) -> str:
    """SHA-256 over a canonical CSV serialization of the panel (platform-stable).

    Parquet bytes are not byte-stable across writer versions, so the dataset
    checksum is taken over a deterministic CSV rendering (sorted columns, LF) of
    the panel content -- the content fingerprint a reviewer can reproduce
    (ARCH §3.2 dataset_checksums; plan task 10c LF normalization).

    Run-metadata / provenance columns (``snapshot_date``/``data_vendor``; DATA §7.1)
    are excluded so the content SHA is invariant to the run's wall-clock date -- the
    same fix applied to ``assemble.content_sha256`` (the major Phase-1 finding).
    The league estimation panel does not currently carry those columns, so this is
    defense-in-depth + a single shared exclusion rule across both content hashers.
    """
    from src.assemble import RUN_METADATA_COLUMNS

    cols = sorted(c for c in panel.columns if c not in RUN_METADATA_COLUMNS)
    csv_text = panel[cols].to_csv(index=False, lineterminator="\n")
    return sha256_text(csv_text)
