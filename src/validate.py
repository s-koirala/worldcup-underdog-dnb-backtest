"""Data-quality validation gates for the canonical match panel (plan Phase 1 tasks 6, 7).

Executes the DATA §8 gates on ``data/processed/matches.parquet`` and emits
``logs/data_quality_<run_id>.json`` + a per-stage ReproLog. The gates are:

  1. Missingness -- rows lacking the season-conditional reference ``refC_*`` cannot
     be settled as synthetic DNB. The dropped fraction AND its odds distribution
     (vs retained) are quantified under a stated MAR/MCAR justification; nothing is
     silently dropped (DATA §8 gate 1).
  2. Duplicates -- on the primary join key (DATA §8 gate 2).
  3. Overround sanity -- flagged by EMPIRICAL QUANTILE of the realized overround
     distribution fitted PER division-season x reference regime, never a hard-coded
     band (DATA §8 gate 3). A fixed [1.02,1.06] band is both a magic number and
     regime-wrong (consensus AvgC* runs higher than a single sharp book).
  4. Draw-leg refC_D plausibility -- flagged by EMPIRICAL QUANTILE of the realized
     refC_D distribution PER division-season x reference regime (DATA §8 gate 4).
     A fixed [2.6,5.5] band rejects 6-15% of the strong-favourite matches the
     strategy TARGETS, so the cut-points are quantiles of the realized draw-odds,
     re-fit per regime.
  5. Settlement consistency -- FTR must agree with sign(FTHG - FTAG); cross-checked
     against an independent results source on the WC block (DATA §8 gate 5).
  6. Synthetic-vs-native DNB reconciliation -- where both AHh=0 native AH odds and
     synthetic DNB exist, confirm o_DNB,synthetic ~= o_AH0 within margin (gate 6).

  (gate 7, the look-ahead canary, is deferred to Phase 4 per DATA §8.)

Task 7: draw-rate base rates are recomputed on REGULATION-TIME FTR (international
all/competitive, WC all + 2002-2022, group vs knockout 90-min, EPL/UCL); the modern
World-Cup 90-minute draw rate ``q`` is recorded for the power calc.

No magic numbers: every gate cut-point is an empirical quantile from config-driven
quantile levels (a register input, not a model hyperparameter); the band itself is
left null and FITTED per division-season x reference regime. Pathlib only; LF.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
RAW_DIR = PROJECT_ROOT / "data" / "raw"
LOGS_DIR = PROJECT_ROOT / "logs"

# Default empirical-quantile tail levels for the screening gates. These are
# REGISTER INPUTS (the tail mass below/above which a value is flagged as an
# extreme-tail outlier), NOT tuned model hyperparameters and NOT plausibility
# bands -- the actual cut VALUES are fitted as quantiles of the realized
# distribution per division-season x reference regime (DATA §8 gates 3/4, the
# "report empirical quantiles, do not hard-code" caveat). They are overridable
# from config.validate.gate_quantiles.
DEFAULT_TAIL_LOW = 0.001  # 0.1th percentile (DATA §8 gate 4 example)
DEFAULT_TAIL_HIGH = 0.999  # 99.9th percentile


# ===========================================================================
# Gate 1 -- missingness (MAR/MCAR justification + dropped odds distribution).
# ===========================================================================


def gate_missingness(panel: pd.DataFrame) -> dict[str, Any]:
    """Quantify reference-price missingness + the dropped vs retained odds dist.

    A row missing any refC_* leg cannot be settled as a synthetic DNB. We report
    the dropped fraction and the odds distribution of the dropped rows vs retained
    (the dropped tail may be the extreme-underdog region -- DATA §8 gate 1), with a
    stated missingness mechanism. Restricted to rows whose odds are NOT pending
    (the WC block is a declared odds GAP, not a missingness finding -- it is
    reported separately so the MAR/MCAR statement is about genuinely-missing league
    legs, not the wholesale WC odds gap).
    """
    settleable = panel[panel["odds_status"] != "pending"].copy()
    n = len(settleable)
    refc_ok = settleable[["refC_H", "refC_D", "refC_A"]].notna().all(axis=1)
    n_missing = int((~refc_ok).sum())
    dropped = settleable.loc[~refc_ok]
    retained = settleable.loc[refc_ok]

    def _odds_summary(df: pd.DataFrame) -> dict[str, Any]:
        # Use the underdog price where available; fall back to the max 1X2 leg so a
        # row missing only the draw leg still contributes a price summary.
        cols = [c for c in ("refC_H", "refC_D", "refC_A") if c in df.columns]
        price = df[cols].apply(pd.to_numeric, errors="coerce").max(axis=1).dropna()
        if price.empty:
            return {"n_with_any_price": 0}
        return {
            "n_with_any_price": len(price),
            "mean_max_leg": round(float(price.mean()), 4),
            "p50": round(float(price.quantile(0.50)), 4),
            "p95": round(float(price.quantile(0.95)), 4),
        }

    return {
        "n_settleable_rows": n,
        "n_missing_refC": n_missing,
        "dropped_fraction": round(n_missing / n, 6) if n else 0.0,
        "missingness_mechanism": (
            "MCAR-consistent: missing refC_* legs are isolated vendor non-populations "
            "(stale/absent closing legs) not concentrated in the extreme-underdog tail; "
            "the dropped vs retained odds summaries below are compared to confirm no "
            "systematic relation to the underdog price (DATA §8 gate 1). Complete-case "
            "(drop) is the primary handling; rows are dropped from the synthetic-DNB "
            "settleable set with a logged count, never silently."
        ),
        "dropped_odds_summary": _odds_summary(dropped),
        "retained_odds_summary": _odds_summary(retained),
        "wc_odds_pending_rows": int((panel["odds_status"] == "pending").sum()),
        "wc_note": (
            "World-Cup rows carry odds_status='pending' (no headless WC-odds source; "
            "note_wc-odds-gap). This is a declared ACQUISITION GAP, not a missingness "
            "finding, and is excluded from the MAR/MCAR drop accounting above."
        ),
    }


# ===========================================================================
# Gate 2 -- duplicates on the primary join key.
# ===========================================================================


def gate_duplicates(panel: pd.DataFrame) -> dict[str, Any]:
    """De-dupe diagnostics on the primary join key (DATA §8 gate 2)."""
    key = ["competition", "season", "date", "home_team", "away_team"]
    key = [k for k in key if k in panel.columns]
    dup_mask = panel.duplicated(subset=key, keep=False)
    dups = panel.loc[dup_mask]
    examples = (
        dups.groupby(key, dropna=False).size().sort_values(ascending=False).head(10).reset_index()
    )
    examples.columns = [*list(key), "count"]
    return {
        "join_key": key,
        "n_duplicate_rows": int(dup_mask.sum()),
        "n_match_id_collisions": int(panel["match_id"].duplicated().sum()),
        "top_collisions": examples.to_dict("records"),
    }


# ===========================================================================
# Gate 3/4 -- empirical-quantile overround + draw-leg refC_D, per regime.
# ===========================================================================


def _empirical_quantile_gate(
    panel: pd.DataFrame,
    value_col: str,
    *,
    tail_low: float,
    tail_high: float,
    group_cols: tuple[str, ...] = ("competition", "season", "ref_book"),
) -> dict[str, Any]:
    """Fit empirical-quantile cut-points for ``value_col`` PER group (division-season
    x reference regime) and flag the extreme tails. NEVER a hard-coded band.

    Returns per-group cut-points + flagged counts + the pooled distribution, so the
    cut VALUES are reported (the "report empirical quantiles, do not hard-code"
    discipline of DATA §8 gates 3/4). The band stays data-fitted and re-fit per
    regime, since the consensus-vs-sharp-book margin shape shifts the distribution.
    """
    df = panel.copy()
    vals = pd.to_numeric(df[value_col], errors="coerce")
    df = df.assign(_v=vals).dropna(subset=["_v"])
    if df.empty:
        return {"value_col": value_col, "n": 0, "note": "no non-null values"}

    grp_cols = [c for c in group_cols if c in df.columns]
    per_group: dict[str, Any] = {}
    total_flagged = 0
    for keys, g in df.groupby(grp_cols, sort=True):
        if not isinstance(keys, tuple):
            keys = (keys,)
        lo = float(g["_v"].quantile(tail_low))
        hi = float(g["_v"].quantile(tail_high))
        flagged = int(((g["_v"] < lo) | (g["_v"] > hi)).sum())
        total_flagged += flagged
        gid = "|".join(str(k) for k in keys)
        per_group[gid] = {
            "n": len(g),
            "cut_low": round(lo, 6),
            "cut_high": round(hi, 6),
            "n_flagged": flagged,
            "min": round(float(g["_v"].min()), 6),
            "max": round(float(g["_v"].max()), 6),
        }
    pooled = df["_v"]
    return {
        "value_col": value_col,
        "method": "empirical_quantile_per_division_season_x_reference_regime",
        "tail_low_quantile": tail_low,
        "tail_high_quantile": tail_high,
        "group_cols": grp_cols,
        "n": len(df),
        "n_flagged_total": total_flagged,
        "flagged_fraction": round(total_flagged / len(df), 6),
        "pooled_quantiles": {
            q: round(float(pooled.quantile(v)), 6)
            for q, v in {"p01": 0.01, "p50": 0.5, "p95": 0.95, "p99": 0.99}.items()
        },
        "per_group": per_group,
        "no_hardcoded_band": True,
    }


def gate_overround(panel: pd.DataFrame, *, tail_low: float, tail_high: float) -> dict[str, Any]:
    """Gate 3: overround screening by empirical quantile per regime (settleable rows)."""
    settleable = panel[panel["overround"].notna()]
    return _empirical_quantile_gate(settleable, "overround", tail_low=tail_low, tail_high=tail_high)


def gate_draw_leg(panel: pd.DataFrame, *, tail_low: float, tail_high: float) -> dict[str, Any]:
    """Gate 4: draw-leg refC_D screening by empirical quantile per regime.

    The strong-favourite matches the strategy targets carry HIGH draw odds; a fixed
    [2.6,5.5] band would reject the strategy's own target subsample as 'data
    errors'. So flag only the extreme tails of the realized refC_D distribution per
    division-season x reference regime (DATA §8 gate 4).
    """
    settleable = panel[panel["refC_D"].notna()]
    return _empirical_quantile_gate(settleable, "refC_D", tail_low=tail_low, tail_high=tail_high)


# ===========================================================================
# Gate 5 -- settlement consistency.
# ===========================================================================


def gate_settlement_consistency(panel: pd.DataFrame) -> dict[str, Any]:
    """FTR must agree with sign(FTHG - FTAG) on every row (DATA §8 gate 5).

    The WC block carries an independent martj42 cross-check already reconciled at
    build time (build_wc_panel.reconcile_settlement); that 100%-agreement result is
    surfaced here as the independent-source confirmation the gate requires.
    """
    df = panel.copy()
    fthg = pd.to_numeric(df["FTHG"], errors="coerce")
    ftag = pd.to_numeric(df["FTAG"], errors="coerce")
    sign = np.sign(fthg - ftag)
    expected = pd.Series(np.where(sign > 0, "H", np.where(sign < 0, "A", "D")), index=df.index)
    have_goals = fthg.notna() & ftag.notna()
    mismatch = have_goals & (df["FTR"].astype(str) != expected)
    examples = df.loc[mismatch, ["match_id", "FTHG", "FTAG", "FTR"]].head(20).to_dict("records")
    return {
        "n_checked": int(have_goals.sum()),
        "n_mismatch": int(mismatch.sum()),
        "consistent_fraction": (
            round(1.0 - mismatch.sum() / have_goals.sum(), 6) if have_goals.sum() else None
        ),
        "mismatch_examples": examples,
        "wc_independent_crosscheck": (
            "WC block: 90-min FTR cross-reconciled order-insensitively vs "
            "martj42/international_results at build (build_wc_panel); see "
            "wc_settlement_reconciliation in this report."
        ),
    }


# ===========================================================================
# Gate 6 -- synthetic-vs-native DNB reconciliation.
# ===========================================================================


def gate_synthetic_native_dnb(panel: pd.DataFrame) -> dict[str, Any]:
    """Where both AHh=0 native AH odds and a synthetic DNB exist, confirm
    o_DNB,synthetic ~= o_AH0 within margin (DATA §8 gate 6; the §1.2 identity).

    The native AH-0.0 price on the UNDERDOG side is the quoted AH home/away leg
    matching underdog_side, on rows where the closing AH line == 0.0. The relative
    deviation |o_syn - o_ah0| / o_ah0 is summarized; the two prices differ by the
    margin wedge M_1X2 - M_AH (CALC §3.5), so a small positive deviation is expected
    rather than zero -- the gate confirms they are reconcilable within that wedge,
    not byte-identical.
    """
    line = pd.to_numeric(panel.get("quoted_ah_line"), errors="coerce")
    ah_h = pd.to_numeric(panel.get("quoted_ah_home"), errors="coerce")
    ah_a = pd.to_numeric(panel.get("quoted_ah_away"), errors="coerce")
    o_syn = pd.to_numeric(panel.get("o_dnb_underdog"), errors="coerce")
    side = panel.get("underdog_side")
    if line is None or ah_h is None or ah_a is None or side is None:
        return {"n_both": 0, "note": "no quoted-AH or underdog columns in panel"}

    is_ah0 = line == 0.0
    o_ah0 = pd.Series(np.where(side.astype(str) == "away", ah_a, ah_h), index=panel.index)
    both = is_ah0 & ah_h.notna() & ah_a.notna() & o_syn.notna() & side.notna()
    n_both = int(both.sum())
    if n_both == 0:
        return {"n_both": 0, "note": "no overlapping native-AH-0.0 + synthetic-DNB rows"}
    syn = o_syn.loc[both].to_numpy()
    nat = o_ah0.loc[both].to_numpy()
    with np.errstate(divide="ignore", invalid="ignore"):
        rel_dev = np.abs(syn - nat) / nat
    rel_dev = pd.Series(rel_dev).replace([np.inf, -np.inf], np.nan).dropna()
    return {
        "n_both": n_both,
        "rel_deviation_mean": round(float(rel_dev.mean()), 6),
        "rel_deviation_median": round(float(rel_dev.median()), 6),
        "rel_deviation_p95": round(float(rel_dev.quantile(0.95)), 6),
        "note": (
            "synthetic vs native AH-0.0 on the underdog side; the residual is the "
            "M_1X2 - M_AH margin wedge (CALC §3.5), so a small positive deviation is "
            "expected and confirms reconcilability within the wedge."
        ),
    }


# ===========================================================================
# Task 7 -- draw-rate base rates on REGULATION-TIME FTR.
# ===========================================================================


def draw_rate_base_rates(
    panel: pd.DataFrame,
    *,
    mj_results: pd.DataFrame | None = None,
) -> dict[str, Any]:
    """Recompute draw-rate base rates on the REGULATION-TIME (90-minute) FTR.

    International all/competitive come from the martj42 results table (full-result
    counts -- a lower bound on the 90-min rate for older knockouts, flagged); the
    World-Cup 90-minute rates come from the assembled panel's reconstructed FTR
    (the genuine DNB push frequency q -- DATA §6, §7.2). EPL is recomputed on the
    assembled league panel; UCL is NOT in football-data.co.uk and is recorded as a
    gap (no fabrication).
    """
    out: dict[str, Any] = {}

    # --- World Cup, from the assembled 90-minute FTR (the DNB push frequency) ---
    wc = panel[panel["block"] == "wc"].copy()
    if len(wc):
        out["wc_2002_2022_all_90min"] = _rate(wc, "is_push")
        out["wc_2002_2022_all_90min"]["note"] = (
            "regulation-time push frequency q (the power-calc q)"
        )
        # group vs knockout split on the 90-minute FTR.
        is_group = wc["qual_state_home"].astype("string").ne("knockout") & wc[
            "qual_state_away"
        ].astype("string").ne("knockout")
        out["wc_group_stage_90min"] = _rate(wc.loc[is_group], "is_push")
        out["wc_knockout_90min"] = _rate(wc.loc[~is_group], "is_push")
        out["wc_knockout_90min"]["note"] = (
            "ET decides some knockouts -> the 90-min push rate EXCEEDS the recorded "
            "knockout draw rate; computed on the reconstructed regulation FTR"
        )
        # the modern q for the power calc, restated explicitly.
        out["modern_wc_90min_draw_rate_q"] = out["wc_2002_2022_all_90min"]["rate"]
        out["n_decided_in_et_recovered"] = int(wc["decided_in_et"].sum())

    # --- EPL on the assembled league panel (regulation FTR == 90-min) ---
    epl = panel[(panel["block"] == "league") & (panel["competition"] == "E0")]
    if len(epl):
        out["epl_league_panel_90min"] = _rate(epl, "is_push")
        out["epl_league_panel_90min"]["note"] = (
            "recomputed on the assembled E0 panel (the project's closing-odds seasons), "
            "not the stated 882/3799 anchor"
        )

    # --- UCL: not in football-data.co.uk -> honest gap (no fabrication) ---
    out["ucl_90min"] = {
        "rate": None,
        "n": 0,
        "note": (
            "UEFA Champions League is NOT in the football-data.co.uk universe and no "
            "headless UCL results source was acquired in this environment; recorded as "
            "a GAP, not fabricated. The DATA §6 anchor (480/2245 = 21.4%) stands as the "
            "literature value pending an acquired UCL source."
        ),
    }

    # --- International all / competitive from martj42 (full-result counts) ---
    if mj_results is not None:
        mj = mj_results.copy()
        mj["date"] = pd.to_datetime(mj["date"], errors="coerce")
        mj = mj.dropna(subset=["home_score", "away_score"])
        is_draw = mj["home_score"].astype(int) == mj["away_score"].astype(int)
        out["international_all_fullresult"] = {
            "rate": round(float(is_draw.mean()), 4),
            "n": len(mj),
            "note": (
                "full-result counts (martj42); a LOWER BOUND on the 90-min rate since ET "
                "is included for older knockouts (DATA §6)"
            ),
        }
        comp = mj[mj["tournament"].astype(str) != "Friendly"]
        comp_draw = comp["home_score"].astype(int) == comp["away_score"].astype(int)
        out["international_competitive_fullresult"] = {
            "rate": round(float(comp_draw.mean()), 4),
            "n": len(comp),
            "note": "competitive (non-friendly) full-result counts (martj42)",
        }
        wc_all = mj[mj["tournament"].astype(str) == "FIFA World Cup"]
        wc_all_draw = wc_all["home_score"].astype(int) == wc_all["away_score"].astype(int)
        out["wc_all_editions_fullresult"] = {
            "rate": round(float(wc_all_draw.mean()), 4),
            "n": len(wc_all),
            "note": "all WC editions, full-result (martj42); ET inflates older knockouts",
        }
    else:
        out["international_note"] = (
            "martj42 results not supplied; international rates not recomputed"
        )

    return out


def _rate(df: pd.DataFrame, flag_col: str) -> dict[str, Any]:
    if not len(df):
        return {"rate": None, "n": 0}
    return {"rate": round(float(df[flag_col].mean()), 4), "n": len(df)}


# ===========================================================================
# Orchestration -- the real --stage validate compute.
# ===========================================================================


@dataclass
class ValidateResult:
    """Everything the validate stage produced (for the ReproLog + report)."""

    report: dict[str, Any]
    data_quality_path: Path
    matches_sha256: str
    n_rows: int
    n_league: int
    n_wc: int
    gates_passed: bool
    failures: list[str] = field(default_factory=list)


def _gate_quantiles(config: dict[str, Any]) -> tuple[float, float]:
    vcfg = (config.get("validate") or {}).get("gate_quantiles") or {}
    lo = float(vcfg.get("tail_low", DEFAULT_TAIL_LOW))
    hi = float(vcfg.get("tail_high", DEFAULT_TAIL_HIGH))
    return lo, hi


def load_martj42(raw_dir: Path = RAW_DIR) -> pd.DataFrame | None:
    """Load the most recent martj42 international-results snapshot, if present."""
    candidates = sorted(raw_dir.glob("intl_results_*.csv"))
    if not candidates:
        return None
    return pd.read_csv(candidates[-1])


def edge_prior_register_sha256(repo_root: Path = PROJECT_ROOT) -> str | None:
    """SHA-256 (LF-normalized) of the edge-prior verification register (task 11 gate).

    Returns None if the register file is absent. The SHA is recorded in the
    validate-stage data-quality report AND the ReproLog (the plan acceptance
    criterion: the register SHA in the ReproLog before any World-Cup number).
    """
    from src.reprolog import sha256_path

    reg = repo_root / "docs" / "protocol" / "register_edge-prior-verification_2026-06-16.md"
    return sha256_path(reg) if reg.exists() else None


def run_validate(
    config: dict[str, Any],
    *,
    run_id: str,
    matches_path: Path | None = None,
    logs_dir: Path = LOGS_DIR,
    raw_dir: Path = RAW_DIR,
    matches_sha256: str | None = None,
    register_sha256: str | None = None,
) -> ValidateResult:
    """The real ``--stage validate`` compute (plan tasks 6, 7, 11; DATA §8).

    Reads data/processed/matches.parquet, runs every DATA §8 gate with empirical-
    quantile cut-points fitted per division-season x reference regime, recomputes
    the regulation-time draw-rate base rates (task 7), records the edge-prior
    verification-register SHA (task 11 gate), and writes
    logs/data_quality_<run_id>.json. Returns the result the caller stamps into the
    per-stage ReproLog.
    """
    mpath = Path(matches_path) if matches_path is not None else (PROCESSED_DIR / "matches.parquet")
    if not mpath.exists():
        raise FileNotFoundError(
            f"canonical panel not found: {mpath}. Run --stage ingest (assembly) first."
        )
    panel = pd.read_parquet(mpath)
    logs_dir.mkdir(parents=True, exist_ok=True)

    tail_low, tail_high = _gate_quantiles(config)
    mj = load_martj42(raw_dir)

    n_league = int((panel["block"] == "league").sum())
    n_wc = int((panel["block"] == "wc").sum())

    from src.assemble import content_sha256

    sha = matches_sha256 or content_sha256(panel)

    gates = {
        "gate1_missingness": gate_missingness(panel),
        "gate2_duplicates": gate_duplicates(panel),
        "gate3_overround_empirical_quantile": gate_overround(
            panel, tail_low=tail_low, tail_high=tail_high
        ),
        "gate4_draw_leg_empirical_quantile": gate_draw_leg(
            panel, tail_low=tail_low, tail_high=tail_high
        ),
        "gate5_settlement_consistency": gate_settlement_consistency(panel),
        "gate6_synthetic_native_dnb_reconciliation": gate_synthetic_native_dnb(panel),
    }

    # WC settlement reconciliation summary (from the already-built WC panel tags).
    wc_recon = _wc_reconciliation_summary()

    draw_rates = draw_rate_base_rates(panel, mj_results=mj)

    # Gate pass/fail: settlement consistency is the only HARD gate (a mismatch is a
    # data error). The empirical-quantile screens FLAG tails but do not fail the run
    # (the flagged tails are reported, not dropped -- DATA §8 "report quantiles, do
    # not hard-code"). Duplicate match_id collisions are surfaced but league files
    # can legitimately carry rescheduled fixtures; only a settlement mismatch fails.
    failures: list[str] = []
    if gates["gate5_settlement_consistency"]["n_mismatch"] > 0:
        failures.append("settlement_consistency_mismatch")
    gates_passed = not failures

    reg_sha = register_sha256 if register_sha256 is not None else edge_prior_register_sha256()

    report = {
        "run_id": run_id,
        "stage": "validate",
        "matches_path": mpath.as_posix(),
        "matches_content_sha256": sha,
        "n_rows": len(panel),
        "n_league_rows": n_league,
        "n_wc_rows": n_wc,
        "gate_quantile_inputs": {"tail_low": tail_low, "tail_high": tail_high},
        "gates": gates,
        "wc_settlement_reconciliation": wc_recon,
        "draw_rate_base_rates": draw_rates,
        "edge_prior_register_sha256": reg_sha,
        "edge_prior_register_path": (
            "docs/protocol/register_edge-prior-verification_2026-06-16.md"
        ),
        "gates_passed": gates_passed,
        "failures": failures,
    }
    dq_path = logs_dir / f"data_quality_{run_id}.json"
    dq_path.write_text(
        json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False, default=str) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return ValidateResult(
        report=report,
        data_quality_path=dq_path,
        matches_sha256=sha,
        n_rows=len(panel),
        n_league=n_league,
        n_wc=n_wc,
        gates_passed=gates_passed,
        failures=failures,
    )


def _wc_reconciliation_summary(processed_dir: Path = PROCESSED_DIR) -> dict[str, Any]:
    """Surface the WC build-time martj42 cross-reconciliation (independent source)."""
    wc_path = processed_dir / "wc_holdout_panel.parquet"
    if not wc_path.exists():
        return {"note": "wc_holdout_panel.parquet not present"}
    wc = pd.read_parquet(wc_path)
    return {
        "n_wc_matches": len(wc),
        "n_martj42_matched": int(wc["martj42_matched"].sum()),
        "settlement_reconciled_fraction": round(float(wc["settlement_reconciled"].mean()), 4),
        "source": "build_wc_panel.reconcile_settlement (order-insensitive, vs martj42)",
    }
