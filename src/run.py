"""Per-phase runnable entrypoint with a stage selector and a --dry-run gate.

Phase 0 task 9 (per-phase entrypoints), task 3 (ReproLog dry-run validation),
task 9.1 (deterministic per-stage RNG sub-stream), task 10 (cross-platform).

Usage
-----
    python -m src.run --config config/baseline.yaml --dry-run
    python -m src.run --config config/baseline.yaml --stage ingest --dry-run

``--dry-run`` resolves the config, derives the named stage's RNG sub-stream from
``(root_seed, stage_name)`` (order-independent; src.seeding), emits a ReproLog
that validates against the committed 13-named-key JSON Schema (src.reprolog), and
exits WITHOUT running compute (Phase 0 acceptance). The real per-stage compute is
implemented in later phases; this module is the Phase-0 scaffold that every stage
target (Makefile) invokes.

Determinism / cross-platform (plan §D.4, §D.7):
  * ``config_resolved_sha256`` is computed on the canonical JSON of the resolved
    config (sorted keys, LF) so two same-seed runs -- and the ubuntu/windows CI
    matrix -- produce the SAME resolved-config SHA (platform invariance).
  * no global ``np.random``; the stage sub-stream comes from ``seeding.substream``.
  * pathlib only; no absolute paths outside config.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from src import reprolog, seeding

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# The per-phase stages (plan task 9). These are the pipeline stages that have a
# Makefile target and a per-stage entrypoint; they are the subset of
# seeding.STAGE_SPAWN_MAP that corresponds to a phase (the resampling-engine
# stages bootstrap-ci / ledoit-wolf / ruin-mc / vector-kelly are sub-stream names
# drawn from WITHIN these phases, not standalone --stage values here).
PHASE_STAGES: tuple[str, ...] = ("ingest", "validate", "price", "stake", "infer", "report")


def load_config(config_path: Path) -> dict[str, Any]:
    """Load a YAML config into a plain dict (config-as-data; ARCH §3.3)."""
    path = Path(config_path)
    if not path.is_absolute():
        path = (PROJECT_ROOT / path).resolve()
    if not path.exists():
        raise FileNotFoundError(f"config not found: {path}")
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def canonical_config_json(resolved: dict[str, Any]) -> str:
    """Canonical JSON of the resolved config for a platform-invariant SHA.

    Sorted keys + LF; the SHA of THIS string is config_resolved_sha256, so two
    same-seed runs and the ubuntu/windows CI matrix agree byte-for-byte (Phase 0
    acceptance: platform-invariant resolved-config SHA).
    """
    return json.dumps(resolved, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def resolve_config(config: dict[str, Any], stage: str) -> dict[str, Any]:
    """Return the fully-resolved config for a stage.

    Phase 0 scaffold: the resolved config is the loaded config plus the resolved
    stage. Later phases extend this with stage-specific defaults/overrides; the
    canonicalization (canonical_config_json) is what the SHA is taken over.
    """
    resolved = dict(config)
    resolved["_resolved_stage"] = stage
    return resolved


def root_seed_from_config(config: dict[str, Any]) -> int:
    """Read the root seed (seeding.root_seed, mirrored by inference.seed)."""
    seeding_block = config.get("seeding") or {}
    if "root_seed" in seeding_block:
        return int(seeding_block["root_seed"])
    inference_block = config.get("inference") or {}
    if "seed" in inference_block:
        return int(inference_block["seed"])
    raise KeyError("no root seed in config (expected seeding.root_seed or inference.seed)")


def make_run_id(stage: str, *, now: datetime | None = None) -> str:
    """Construct a unique-but-deterministic-shaped run id: <stage>-<UTCstamp>."""
    ts = (now or datetime.now(UTC)).strftime("%Y%m%dT%H%M%SZ")
    return f"{stage}-{ts}"


def dry_run(
    config_path: Path,
    stage: str,
    *,
    repo_root: Path | None = None,
    run_id: str | None = None,
    logs_dir: Path | None = None,
) -> Path:
    """Resolve config, derive the stage RNG sub-stream, emit a validated ReproLog.

    Returns the written ReproLog path. Runs NO compute (Phase 0 acceptance).
    ``logs_dir`` overrides the default logs/ destination (tests isolate it).
    """
    root = Path(repo_root) if repo_root is not None else PROJECT_ROOT
    config = load_config(config_path)
    root_seed = root_seed_from_config(config)

    # Derive the stage sub-stream (order-independent; never the root generator,
    # never global np.random). Constructing it here proves the (root_seed, stage)
    # mapping resolves for this stage; the Generator is not drawn from in dry-run.
    _ = seeding.substream(root_seed, stage)

    resolved = resolve_config(config, stage)
    config_sha = reprolog.sha256_text(canonical_config_json(resolved))

    rid = run_id or make_run_id(stage)
    record = reprolog.build(
        run_id=rid,
        rng_seed=root_seed,
        repo_root=root,
        logs_dir=logs_dir,
        config_resolved_sha256=config_sha,
        # model_hash / dataset_checksums / data_vendor / snapshot_date stay at
        # their schema-valid defaults (null / {}) in the dry-run: no fit, no data.
    )
    return record.emit(logs_dir=logs_dir)


# The World-Cup raw RESULTS sources (built by ``python -m src.build_wc_panel``) that
# determine the WC block of the canonical panel. Glob-matched per snapshot so the
# ingest stage that pins ``matches.parquet`` also pins, by checksum, every input the
# WC settlement block is derived from (the major finding: the WC inputs must be
# transitively bound into the stage emitting the canonical-panel hash, not only into
# a separate out-of-band wc-ingest ReproLog). These prefixes mirror
# ``src.build_wc_panel.RAW_FILENAMES`` exactly.
WC_RAW_SOURCE_PREFIXES: tuple[str, ...] = (
    "wc_jfjelstul_matches_",
    "wc_jfjelstul_goals_",
    "wc_jfjelstul_penalties_",
    "intl_results_",
    "intl_shootouts_",
)


class WCPanelMissingError(RuntimeError):
    """The canonical-panel assembly requires the WC hold-out panel but it is absent.

    Raised (fail-closed) when ``data/processed/wc_holdout_panel.parquet`` is not on
    disk: the ingest stage MUST NOT silently materialise a league-only canonical
    panel whose hash then masquerades as the league+WC headline canonical-panel hash
    (the major Phase-1 finding). The WC panel is produced by the documented
    ``reproduce-wc`` Makefile target (``python -m src.build_wc_panel``).
    """


def wc_source_checksums(
    *,
    processed_dir: Path,
    raw_dir: Path,
    wc_panel: object,
) -> dict[str, str]:
    """Collect the LF-normalized SHA-256 of every World-Cup input that feeds the
    canonical panel's WC block, for folding into the ingest ReproLog.

    Pins, by checksum: each on-disk WC raw RESULTS source (``wc_jfjelstul_*``,
    ``intl_results_*``, ``intl_shootouts_*``); the WC hold-out panel CSV mirror and
    parquet (``wc_holdout_panel.csv``); the team-alias crosswalk
    (``data/external/team_aliases.csv``); and the content fingerprint of the
    in-memory WC panel itself (``wc_holdout_panel.content``). These are the genuine
    on-disk inputs the WC settlement block is derived from -- nothing is fabricated.

    The raw-source checksums are recomputed here (not re-read from the wc-ingest
    sidecars) so the ingest ReproLog binds the actual bytes present at assembly time;
    they match ``src.build_wc_panel``'s recorded values when the snapshot is intact.
    """
    from src import assemble, reprolog

    checks: dict[str, str] = {}

    # 1) WC raw RESULTS sources (every snapshot of each prefix, so a re-snapshot is
    #    also bound). LF-normalized SHA matches the .sha256 sidecars.
    for prefix in WC_RAW_SOURCE_PREFIXES:
        for src_path in sorted(raw_dir.glob(f"{prefix}*.csv")):
            checks[src_path.name] = reprolog.sha256_path(src_path)

    # 2) WC hold-out panel CSV mirror (human-auditable, LF) + content fingerprint of
    #    the parsed panel (parquet bytes are not byte-stable; the content SHA is).
    wc_csv = processed_dir / "wc_holdout_panel.csv"
    if wc_csv.exists():
        checks["wc_holdout_panel.csv"] = reprolog.sha256_path(wc_csv)
    checks["wc_holdout_panel.content"] = assemble.content_sha256(wc_panel)

    # 3) Team-alias crosswalk (the WC<->martj42 join key; build_wc_panel output).
    crosswalk = processed_dir.parent / "external" / "team_aliases.csv"
    if crosswalk.exists():
        checks["team_aliases.csv"] = reprolog.sha256_path(crosswalk)

    return checks


def assemble_canonical_panel(
    config: dict[str, Any],
    ingest_result: object,
    *,
    processed_dir: Path | None = None,
    raw_dir: Path | None = None,
    require_wc: bool = True,
) -> tuple[Path | None, str | None, dict[str, int], dict[str, str]]:
    """Assemble data/processed/matches.parquet from the league + WC blocks (task 1 schema).

    Reconciles the just-ingested league panel with the already-built World-Cup
    hold-out panel into the single canonical DATA §7.1 table. Returns
    (matches_path, content_sha256, {n_league, n_wc}, wc_dataset_checksums).

    Fails closed (``WCPanelMissingError``) when ``require_wc`` is set and the WC
    hold-out panel is absent: the WC settlement block is part of the canonical panel
    whose content hash the ingest stage pins, so the stage MUST NOT silently emit a
    league-only panel under that hash (the major Phase-1 finding). The WC panel is
    rebuilt by the documented ``reproduce-wc`` target (``python -m src.build_wc_panel``).
    The returned ``wc_dataset_checksums`` binds every WC input by checksum into the
    ingest ReproLog. With ``require_wc=False`` (offline league-only unit tests) the
    panel still materialises from the league block alone and the WC checksum map is
    empty.
    """
    import pandas as pd

    from src import assemble

    pdir = (
        Path(processed_dir) if processed_dir is not None else (PROJECT_ROOT / "data" / "processed")
    )
    rdir = Path(raw_dir) if raw_dir is not None else (PROJECT_ROOT / "data" / "raw")

    league_panel = getattr(ingest_result, "panel")  # noqa: B009
    snapshot_date = (
        getattr(ingest_result, "snapshot_date", None) or datetime.now(UTC).date().isoformat()
    )
    league_vendor = config["ingest"]["data_vendor"]

    wc_path = pdir / "wc_holdout_panel.parquet"
    if not wc_path.exists():
        if require_wc:
            raise WCPanelMissingError(
                f"World-Cup hold-out panel not found: {wc_path}. The canonical "
                "matches.parquet binds the WC settlement block, so ingest fails "
                "closed rather than emit a league-only panel under the canonical "
                "hash. Build it first via `make reproduce-wc` "
                "(`uv run python -m src.build_wc_panel`)."
            )
        wc_panel = pd.DataFrame(columns=["match_id"])
    else:
        wc_panel = pd.read_parquet(wc_path)

    wc_cfg = config.get("wc_holdout") or {}
    wc_vendor = (
        f"{wc_cfg.get('results_settlement_source', 'jfjelstul/worldcup')} + "
        f"{wc_cfg.get('results_crosscheck_source', 'martj42/international_results')} "
        "(RESULTS only; WC odds gap recorded)"
    )

    # martj42 results for the WC host stratum (neutral flag).
    mj_candidates = sorted(rdir.glob("intl_results_*.csv"))
    mj_results = pd.read_csv(mj_candidates[-1]) if mj_candidates else None

    wc_checks: dict[str, str] = {}
    if wc_panel.empty:
        from src.assemble import league_to_canonical

        panel = league_to_canonical(
            league_panel, data_vendor=league_vendor, snapshot_date=snapshot_date
        )
        for c in assemble.CANONICAL_COLUMNS:
            if c not in panel.columns:
                panel[c] = pd.NA
        panel = panel[list(assemble.CANONICAL_COLUMNS)]
    else:
        panel = assemble.assemble_matches(
            league_panel,
            wc_panel,
            league_vendor=league_vendor,
            wc_vendor=wc_vendor,
            snapshot_date=snapshot_date,
            mj_results=mj_results,
        )
        # Bind every WC input by checksum into the stage that pins matches.parquet.
        wc_checks = wc_source_checksums(processed_dir=pdir, raw_dir=rdir, wc_panel=wc_panel)

    if panel.empty:
        return None, None, {"n_league": 0, "n_wc": 0}, wc_checks
    matches_path, sha = assemble.write_matches(panel, processed_dir=pdir)
    counts = {
        "n_league": int((panel["block"] == "league").sum()),
        "n_wc": int((panel["block"] == "wc").sum()),
    }
    return matches_path, sha, counts, wc_checks


def run_ingest_stage(
    config_path: Path,
    *,
    repo_root: Path | None = None,
    run_id: str | None = None,
    logs_dir: Path | None = None,
    fetch: bool = True,
) -> tuple[Path, object]:
    """Run the REAL Phase-1 ingest compute and emit its per-stage ReproLog.

    Downloads the league estimation universe, schema-validates, derives the
    season-conditional refC_*, runs the Pinnacle-degradation provenance gate, writes
    the processed league panel, and ASSEMBLES the single canonical
    data/processed/matches.parquet (league + WC blocks; task 1 schema). The ReproLog
    carries the real dataset_checksums (every downloaded CSV + the canonicalized
    league panel + the canonical matches panel), the vendor, the snapshot date, and
    references the provenance-register SHA via the resolved config SHA. Returns
    (reprolog_path, IngestResult).
    """
    from src import ingest  # local import: heavy deps (pandas/pandera) off the dry-run path

    root = Path(repo_root) if repo_root is not None else PROJECT_ROOT
    config = load_config(config_path)
    root_seed = root_seed_from_config(config)
    _ = seeding.substream(root_seed, "ingest")  # derive (unused draws in ingest)

    rid = run_id or make_run_id("ingest")
    result = ingest.run_ingest(config, run_id=rid, fetch=fetch)

    # Assemble the canonical league+WC panel (task 1 schema) and pin its checksum.
    # Fails closed if the WC hold-out panel is absent (the canonical hash binds the
    # WC settlement block; major Phase-1 finding). The returned WC source checksums
    # are folded into the ingest dataset_checksums so the WC inputs are transitively
    # bound by checksum into the stage that emits the headline canonical-panel hash.
    matches_path, matches_sha, counts, wc_checks = assemble_canonical_panel(config, result)
    result.dataset_checksums.update(wc_checks)
    if matches_path is not None and matches_sha is not None:
        result.dataset_checksums["matches.parquet"] = matches_sha

    # The resolved config for the ingest stage, extended with the provenance-register
    # SHA so the ReproLog config_resolved_sha256 binds the gate artifact by reference.
    resolved = resolve_config(config, "ingest")
    resolved["_pinnacle_register_sha256"] = result.provenance_register_sha256
    config_sha = reprolog.sha256_text(canonical_config_json(resolved))

    record = reprolog.build(
        run_id=rid,
        rng_seed=root_seed,
        repo_root=root,
        logs_dir=logs_dir,
        dataset_checksums=result.dataset_checksums,
        data_vendor=config["ingest"]["data_vendor"],
        snapshot_date=result.snapshot_date,
        config_resolved_sha256=config_sha,
    )
    out = record.emit(logs_dir=logs_dir)
    # Stash the assembly facts on the result for the CLI summary.
    result.matches_path = matches_path  # type: ignore[attr-defined]
    result.matches_sha256 = matches_sha  # type: ignore[attr-defined]
    result.matches_counts = counts  # type: ignore[attr-defined]
    return out, result


def run_validate_stage(
    config_path: Path,
    *,
    repo_root: Path | None = None,
    run_id: str | None = None,
    logs_dir: Path | None = None,
) -> tuple[Path, object]:
    """Run the REAL Phase-1 validate compute and emit its per-stage ReproLog.

    Runs the DATA §8 data-quality gates on data/processed/matches.parquet with
    empirical-quantile cut-points fitted per division-season x reference regime,
    recomputes the regulation-time draw-rate base rates (task 7), and writes
    logs/data_quality_<run_id>.json. The ReproLog pins the canonical panel's content
    checksum in dataset_checksums. Returns (reprolog_path, ValidateResult).
    """
    from src import validate  # local import: heavy deps off the dry-run path

    root = Path(repo_root) if repo_root is not None else PROJECT_ROOT
    config = load_config(config_path)
    root_seed = root_seed_from_config(config)
    _ = seeding.substream(root_seed, "validate")  # derive (no draws in validate)

    # Bind the edge-prior verification register (Phase-1 task 11 gate) into the
    # validate-stage ReproLog by SHA reference: the plan acceptance criterion
    # requires the register SHA in the ReproLog before any World-Cup number. The
    # register file is the source of record; its SHA is computed on LF-normalized
    # bytes (plan task 10c) and recorded as a sidecar, in the data-quality report,
    # and via the resolved config SHA below.
    register_path = root / "docs" / "protocol" / "register_edge-prior-verification_2026-06-16.md"
    register_sha = validate.edge_prior_register_sha256(root)
    if register_sha is not None:
        register_path.with_name(register_path.name + ".sha256").write_text(
            f"{register_sha}  {register_path.name}\n", encoding="utf-8", newline="\n"
        )

    rid = run_id or make_run_id("validate")
    result = validate.run_validate(
        config,
        run_id=rid,
        logs_dir=logs_dir or validate.LOGS_DIR,
        register_sha256=register_sha,
    )

    resolved = resolve_config(config, "validate")
    resolved["_data_quality_run_id"] = rid
    resolved["_edge_prior_register_sha256"] = register_sha
    config_sha = reprolog.sha256_text(canonical_config_json(resolved))

    # The validate stage consumes the WC hold-out panel (settlement reconciliation)
    # and the martj42 results (draw-rate base rates), so its ReproLog binds those WC
    # inputs by checksum too -- the canonical matches.parquet hash alone does not
    # name the upstream WC sources (major Phase-1 finding).
    import pandas as pd

    wc_path = root / "data" / "processed" / "wc_holdout_panel.parquet"
    validate_checksums: dict[str, str] = {"matches.parquet": result.matches_sha256}
    if wc_path.exists():
        validate_checksums.update(
            wc_source_checksums(
                processed_dir=root / "data" / "processed",
                raw_dir=root / "data" / "raw",
                wc_panel=pd.read_parquet(wc_path),
            )
        )

    record = reprolog.build(
        run_id=rid,
        rng_seed=root_seed,
        repo_root=root,
        logs_dir=logs_dir,
        dataset_checksums=validate_checksums,
        data_vendor=config["ingest"]["data_vendor"],
        snapshot_date=datetime.now(UTC).date().isoformat(),
        config_resolved_sha256=config_sha,
    )
    out = record.emit(logs_dir=logs_dir)
    return out, result


def run_stake_stage(
    config_path: Path,
    *,
    repo_root: Path | None = None,
    run_id: str | None = None,
    logs_dir: Path | None = None,
) -> tuple[Path, object]:
    """Run the Phase-3 staking/ledger pass over the league panel + emit its ReproLog.

    Reads data/processed/matches.parquet, de-vigs + settles the LEAGUE block
    (src.ledger.prepare_settled_bets, a-priori-frozen Shin primary), builds the
    execution-cost model from the config ``costs`` block + the Phase-1 open->close
    calibration (src.costs.from_config), and walks the staking/ledger pass for the
    canonical Kelly scheme (the honest-prior reference: f*=0 where the de-vigged edge
    is negative -> stake 0 -> "do not bet"). Every ledger entry carries BOTH gross and
    net PnL; the conservation invariant is asserted before the ReproLog is emitted. The
    ReproLog pins the canonical panel's content checksum and the data-quality report
    (open->close calibration basis) in dataset_checksums, and records the root seed +
    the named `stake` sub-stream derivation (plan task 9.1).

    Returns (reprolog_path, StakeResult-like SimpleNamespace) for the CLI summary.
    """
    import types

    import pandas as pd

    from src import costs as costs_mod
    from src import ledger as ledger_mod

    root = Path(repo_root) if repo_root is not None else PROJECT_ROOT
    config = load_config(config_path)
    root_seed = root_seed_from_config(config)
    # Derive the deterministic `stake` sub-stream (order-independent; never the root
    # generator, never global np.random). No draws are needed for the deterministic
    # ledger walk, but the derivation pins (root_seed, "stake") for the ReproLog.
    _ = seeding.substream(root_seed, "stake")

    matches_path = root / "data" / "processed" / "matches.parquet"
    if not matches_path.exists():
        raise FileNotFoundError(
            f"canonical panel not found: {matches_path}; run --stage ingest first."
        )
    panel = pd.read_parquet(matches_path)

    devig_method = (config.get("odds") or {}).get("devig_method", "shin")
    bets = ledger_mod.prepare_settled_bets(panel, devig_method=devig_method, block="league")

    # Build the cost model from the config costs block + the Phase-1 open->close
    # calibration (data-selected slippage quantile; ADR-0004). The data-quality report
    # is the calibration basis; net-of-cost is the reported figure.
    costs_cfg = config.get("costs") or {}
    dq_report = costs_mod.latest_data_quality_report(root / "logs")
    cost_model = costs_mod.from_config(costs_cfg, data_quality_report=dq_report)

    # The honest-prior reference pass: full push-Kelly. Negative de-vigged edge ->
    # f*=0 -> stake 0 ("do not bet"), reported as a legitimate output (slice brief).
    result = ledger_mod.build_ledger(bets, scheme="kelly", cost_model=cost_model)
    summary = ledger_mod.ledger_summary(result)

    # --- Phase 3 tasks 4-6: ruin Monte-Carlo + BRB/RCK grid + frontier (slice brief).
    risk_outputs = run_risk_engines(config, bets, cost_model, root_seed=root_seed, root=root)

    rid = run_id or make_run_id("stake")

    # dataset_checksums: pin the canonical panel content + the data-quality calibration
    # report so the slippage basis is reconstructible from the ReproLog.
    from src import assemble

    dataset_checksums: dict[str, str] = {
        "matches.parquet": assemble.content_sha256(panel),
    }
    if dq_report is not None:
        dataset_checksums[dq_report.name] = reprolog.sha256_path(dq_report)

    resolved = resolve_config(config, "stake")
    resolved["_stake_scheme"] = result.scheme
    resolved["_slippage_quantile_level"] = cost_model.slippage.quantile_level
    # Pin the ruin Monte-Carlo's RNG sub-stream + B into the resolved-config SHA so its
    # draws are reconstructible from the log (root seed + spawn map). The deployed
    # vector-Kelly path is a DETERMINISTIC convex program with NO Monte-Carlo (it draws
    # from no sub-stream); its spawn-map slot is RESERVED for a future scenario-resampled
    # evaluation. We record it explicitly as reserved/unused so the reproducibility
    # envelope does not overstate what is randomized (ADR-0005; src.vector_kelly docstring).
    resolved["_ruin_mc_substream"] = "ruin-mc"
    resolved["_vector_kelly_substream"] = (
        "vector-kelly (reserved, unused: deterministic convex solve, no rng draw)"
    )
    resolved["_ruin_mc_b"] = risk_outputs["ruin_b"]
    config_sha = reprolog.sha256_text(canonical_config_json(resolved))

    record = reprolog.build(
        run_id=rid,
        rng_seed=root_seed,
        repo_root=root,
        logs_dir=logs_dir,
        dataset_checksums=dataset_checksums,
        data_vendor=config["ingest"]["data_vendor"],
        snapshot_date=datetime.now(UTC).date().isoformat(),
        config_resolved_sha256=config_sha,
    )
    out = record.emit(logs_dir=logs_dir)

    # Persist the risk-engine tables (the F-07/F-08/F-09/T-04/T-05/T-06 DATA) next to
    # the ReproLog so Phase 5 renders them without re-running the Monte-Carlo.
    risk_path = write_risk_outputs(risk_outputs, run_id=rid, logs_dir=logs_dir or (root / "logs"))

    facts = types.SimpleNamespace(
        summary=summary,
        slippage=cost_model.slippage,
        commission_rate=cost_model.commission_rate,
        result=result,
        risk=risk_outputs,
        risk_path=risk_path,
    )
    return out, facts


def _grid_or_default(value: object, default: list[float]) -> list[float]:
    """Return a config grid as a list[float], falling back to ``default`` when null.

    The staking parameter grids (phi/lambda) are ``null`` placeholders in the baseline
    config until the walk-forward CV resolves them (no-magic-number). For the ruin/
    frontier ENGINE to trace a curve before that selection lands, a documented default
    SWEEP RANGE is used: a uniform grid over the admissible fraction range. These are
    sweep POSITIONS for the frontier trace, not asserted operating values (the operating
    point is read off the resulting frontier, never hand-set).
    """
    if value:
        return [float(v) for v in value]  # type: ignore[union-attr]
    return list(default)


# Default frontier SWEEP grids (positions traced before the walk-forward CV resolves the
# config grids). phi over (0, 0.1] brackets the sub-Kelly fixed fractions a real book
# runs; lambda over (0, 1] is the full fractional-Kelly range with half-Kelly (0.5) as
# the documented prior. These are sweep positions for the curve, not operating values.
_DEFAULT_PHI_SWEEP = [0.005, 0.01, 0.02, 0.03, 0.05, 0.075, 0.10]
_DEFAULT_LAMBDA_SWEEP = [0.1, 0.25, 0.5, 0.75, 1.0]


def run_risk_engines(
    config: dict[str, Any],
    bets: object,
    cost_model: object,
    *,
    root_seed: int,
    root: Path,
) -> dict[str, Any]:
    """Run the Phase-3 ruin MC + BRB/RCK grid + growth-drawdown frontier (tasks 4-6).

    Builds the matchday-grouped NET per-bet return blocks from the settled league bets
    (concurrency preserved), runs the matchday-block bootstrap ruin engine and the
    growth-drawdown frontier on the ``ruin-mc`` sub-stream, sweeps the BRB
    ``lambda(alpha_dd, beta_dd)`` / RCK grid over methodology.md §1.2, and -- when the
    all-negative-edge honest prior makes ``lambda*=0`` dominate -- attaches the
    counterfactual bankroll/lambda that WOULD be required were the edge real. Returns a
    JSON-serialisable dict of the tables (the F-07/F-08/F-09/T-04/T-05/T-06 DATA).
    """
    import numpy as np
    import pandas as pd

    from src import frontier as frontier_mod
    from src import ruin as ruin_mod
    from src import staking as staking_mod

    risk_cfg = config.get("risk") or {}
    df = bets  # settled bet table from prepare_settled_bets

    o = pd.to_numeric(df["o_dnb_underdog"], errors="coerce").to_numpy(dtype="float64")
    p_w = pd.to_numeric(df["p_win"], errors="coerce").to_numpy(dtype="float64")
    p_d = pd.to_numeric(df["p_draw"], errors="coerce").to_numpy(dtype="float64")
    gross_ret = pd.to_numeric(df["settle_gross_return"], errors="coerce").to_numpy(dtype="float64")
    md_key = df["date"].astype("string").to_numpy()
    # Underdog 1X2 closing price (the slippage-bucket-cut variable) for per-bucket slippage
    # application in the ruin/frontier net-return blocks (ADR-0004 / Phase-3 task 9).
    if "underdog_price" in df:
        under_price = pd.to_numeric(df["underdog_price"], errors="coerce").to_numpy(dtype="float64")
    else:
        under_price = np.full(o.shape, np.nan, dtype="float64")

    # NET per-bet PROFIT multiple r = net_return - 1 (the multiplicative-update input).
    net_profit = np.full(o.shape, np.nan, dtype="float64")
    for i in range(o.size):
        if np.isfinite(o[i]) and np.isfinite(gross_ret[i]):
            bucket = (
                cost_model.slippage.resolve_odds_bucket(float(under_price[i]))  # type: ignore[attr-defined]
                if np.isfinite(under_price[i])
                else None
            )
            nr = cost_model.net_return(  # type: ignore[attr-defined]
                float(o[i]), float(gross_ret[i]), odds_bucket=bucket
            )
            net_profit[i] = nr - 1.0

    md = ruin_mod.group_by_matchday(net_profit, md_key, o_dnb=o, p_win=p_w, p_draw=p_d)

    # Honest-prior count: positive-edge bets (push-Kelly f* > 0).
    fstar = np.atleast_1d(
        np.asarray(staking_mod.push_kelly_fraction(p_w, p_d, o, clip_negative=True), float)
    )
    n_pos = int((fstar > 0.0).sum())

    # Sweep EVERY ruin floor in the declared grid (methodology.md §1.1-§1.2: "Two values
    # are reported, not one" -- rho in {0.0, 0.5}). Under the multiplicative schemes rho=0
    # is unreachable (W_t>0 a.s.) but the additive cash schemes CAN cross 0, and the 0.5
    # behavioural stop-out is the operationally binding floor; both must be reported. The
    # `ruin-mc` sub-stream is re-derived per rho inside the loop below (order-independent).
    rho_grid = [float(r) for r in (risk_cfg.get("rho_grid") or [0.0])]
    eps_target = float(risk_cfg.get("mc_eps_target", 0.05))
    se_ratio = float(risk_cfg.get("mc_se_ratio", 0.10))
    deployed_b = int(risk_cfg.get("deployed_b", ruin_mod.DEPLOYED_B))
    mean_block = float(risk_cfg.get("mean_block_matchdays", ruin_mod.DEFAULT_MEAN_BLOCK_MATCHDAYS))
    dd_level = str(risk_cfg.get("dd_quantile_level", frontier_mod.DEFAULT_DD_QUANTILE_LEVEL))
    b_floor = ruin_mod.min_bootstrap_paths(eps_target, se_ratio=se_ratio)
    n_paths = max(deployed_b, b_floor)

    alpha_grid = tuple(float(a) for a in risk_cfg.get("alpha_dd_grid", [0.5, 0.6, 0.7, 0.8]))
    beta_grid = tuple(float(b) for b in risk_cfg.get("beta_dd_grid", [0.05, 0.10, 0.20]))
    op_a = float(risk_cfg.get("operating_alpha_dd", 0.5))
    op_b = float(risk_cfg.get("operating_beta_dd", 0.10))

    # Counterfactual reference price/draw: data-derived panel medians when config-null.
    hyp_edge = risk_cfg.get("hypothetical_edge_if_real")
    o_ref = risk_cfg.get("counterfactual_o_dnb_ref")
    if o_ref is None:
        o_ref = float(np.nanmedian(o)) if np.isfinite(o).any() else None
    pd_ref = risk_cfg.get("counterfactual_p_draw_ref")
    if pd_ref is None:
        pd_ref = float(np.nanmean(p_d)) if np.isfinite(p_d).any() else None

    staking_cfg = config.get("staking") or {}
    phi_grid = _grid_or_default(staking_cfg.get("phi_grid"), _DEFAULT_PHI_SWEEP)
    lambda_grid = _grid_or_default(staking_cfg.get("lambda_grid"), _DEFAULT_LAMBDA_SWEEP)
    # The additive cash schemes (flat/level_to_odds) sweep the same fraction-of-initial-
    # bankroll positions as fixed_fraction (W_0=1 normalisation); config c_grid overrides.
    unit_grid = _grid_or_default(staking_cfg.get("unit_grid"), phi_grid)
    c_grid = _grid_or_default(staking_cfg.get("c_grid"), phi_grid)

    # Build a frontier report PER ruin floor rho in the declared grid (methodology.md
    # §1.1-§1.2). The RNG sub-stream is re-derived per rho so each rho's bootstrap is
    # reproducible and independent of sweep order. The first rho is the "primary" report
    # for the back-compat top-level summary fields; all rho are emitted in reports_by_rho.
    reports_by_rho: list[tuple[float, Any]] = []
    for rho in rho_grid:
        rho_rng = seeding.substream(root_seed, "ruin-mc")
        rep = frontier_mod.build_frontier_report(
            md,
            rho=rho,
            rng=rho_rng,
            phi_grid=phi_grid,
            lambda_grid=lambda_grid,
            unit_grid=unit_grid,
            c_grid=c_grid,
            alpha_dd_grid=alpha_grid,
            beta_dd_grid=beta_grid,
            operating_alpha_dd=op_a,
            operating_beta_dd=op_b,
            n_positive_edge_bets=n_pos,
            n_paths=n_paths,
            mean_block=mean_block,
            hypothetical_edge=float(hyp_edge) if hyp_edge is not None else None,
            o_dnb_ref=o_ref,
            p_draw_ref=pd_ref,
            dd_quantile_level=dd_level,
        )
        reports_by_rho.append((rho, rep))
    # Primary (first-rho) report drives the back-compat top-level fields; rho-independent
    # verdicts (lambda*=0 dominance, the RCK grid, the counterfactual) are identical across
    # rho, so the primary carries them for the summary.
    rho = rho_grid[0]
    report = reports_by_rho[0][1]

    # --- Task 8: concurrent-match independence test on the real league matchdays
    # (STAKE Open Question 2). The renormalised single-bet approximation is only
    # defensible if concurrent outcomes are (near-)independent; this gates that.
    # vector_kelly hard-imports cvxpy (ADR-0001 pinned native dep). A bare
    # `python -m src.run` against a global interpreter lacks it; emit an actionable
    # message pointing at the `uv run` entrypoint rather than a bare ModuleNotFoundError.
    try:
        from src import vector_kelly as vk_mod
    except ModuleNotFoundError as exc:
        raise ModuleNotFoundError(
            f"the stake stage requires the pinned native deps (cvxpy + Clarabel; ADR-0001) "
            f"but '{exc.name}' is not importable -- you are likely running a bare "
            f"`python -m src.run` against a global interpreter. Run under the project venv: "
            f"`uv sync --frozen` then `uv run python -m src.run --stage stake` "
            f"(or `make reproduce-staking`). See README 'Running the pipeline'."
        ) from exc

    outcome_idx = np.where(
        gross_ret > 1.0 + 1e-9, 0, np.where(np.abs(gross_ret - 1.0) <= 1e-9, 1, 2)
    )  # 0=win,1=push/draw,2=loss
    matchday_outcomes = [outcome_idx[md_key == k] for k in pd.unique(md_key)]
    indep = vk_mod.independence_lr_test(matchday_outcomes, alpha=0.05)

    # --- Task 3: vector-Kelly exact-vs-approximation growth gap, demonstrated on the
    # LARGEST genuinely-concurrent league matchday (the operational concurrency unit;
    # the WC group-stage slate is the deployment analogue but its odds are PENDING).
    # The exact convex program (cvxpy/Clarabel) vs the renormalised-capped deployable
    # rule, with the growth gap reported (STAKE §5.2-§5.3). On the all-negative-edge
    # honest prior both collapse to all-cash with a zero gap -- reported, not hidden.
    vk_gap = None
    if md.n_matchdays:
        sizes = [blk.size for blk in md.odds_blocks]
        big = int(np.argmax(sizes))
        if md.odds_blocks[big].size >= 2:
            # Cap the slate at a tractable scenario count (3^n scenarios): the exact
            # program enumerates joint outcomes, so a very large slate is infeasible to
            # enumerate; use the first n_cap bets of the largest slate as the demonstrator.
            n_cap = min(md.odds_blocks[big].size, 8)
            o_s = md.odds_blocks[big][:n_cap]
            pw_s = md.pwin_blocks[big][:n_cap]
            pd_s = md.pdraw_blocks[big][:n_cap]
            finite = np.isfinite(o_s) & np.isfinite(pw_s) & np.isfinite(pd_s)
            if finite.sum() >= 2:
                gg = vk_mod.growth_gap(o_s[finite], pw_s[finite], pd_s[finite], lam=1.0)
                vk_gap = {
                    "n_concurrent_bets": int(finite.sum()),
                    "exact_growth": gg.exact.expected_log_growth,
                    "approx_growth": gg.approx.expected_log_growth,
                    "growth_gap": gg.growth_gap,
                    "relative_gap": gg.relative_gap,
                    "exact_budget_used": gg.exact.budget_used,
                    "approx_renormalised": gg.approx.renormalised,
                    "solver_status": gg.exact.solver_status,
                }

    return {
        "n_bets": int(o.size),
        "n_matchdays": md.n_matchdays,
        "n_positive_edge_bets": n_pos,
        "lambda_star_zero_dominates": report.lambda_star_zero_dominates,
        "ruin_b": n_paths,
        "ruin_b_precision_floor": b_floor,
        "ruin_eps_target": eps_target,
        "ruin_se_ratio": se_ratio,
        "rho": rho,
        "rho_grid": rho_grid,
        "report": report,
        "reports_by_rho": reports_by_rho,
        "independence_test": indep,
        "vector_kelly_gap": vk_gap,
    }


def write_risk_outputs(risk_outputs: dict[str, Any], *, run_id: str, logs_dir: Path) -> Path:
    """Serialise the ruin/frontier/RCK tables to logs/risk_frontier_<run_id>.json (task 6).

    Produces the F-07/F-08/F-09/T-04/T-05/T-06 DATA (Phase 5 renders the figures). The
    file carries: the per-scheme frontier points + efficient envelope (T-04/T-05/F-07);
    the BRB lambda(alpha_dd, beta_dd) / RCK grid (T-06); and -- when lambda*=0 dominates
    -- the counterfactual required-if-edge-real feasibility statement.
    """
    import json as _json
    from dataclasses import asdict

    def _serialise_scheme_frontiers(rep: Any) -> dict[str, Any]:
        """Serialise one frontier report's per-scheme curves (T-04/T-05/F-07 data)."""
        return {
            scheme: {
                "all_below_zero_growth": sf.all_below_zero_growth,
                "points": [
                    {
                        "param_name": p.param_name,
                        "param_value": p.param_value,
                        "expected_log_growth": p.expected_log_growth,
                        "drawdown_budget": p.drawdown_budget,
                        "prob_ruin": p.prob_ruin,
                        "prob_ruin_ci": list(p.prob_ruin_ci),
                        "drawdown_quantiles": p.drawdown_quantiles,
                    }
                    for p in sf.points
                ],
                "efficient_points": [
                    {
                        "param_name": p.param_name,
                        "param_value": p.param_value,
                        "expected_log_growth": p.expected_log_growth,
                        "drawdown_budget": p.drawdown_budget,
                    }
                    for p in sf.efficient_points
                ],
            }
            for scheme, sf in rep.scheme_frontiers.items()
        }

    report = risk_outputs["report"]
    rho_grid = risk_outputs.get("rho_grid", [risk_outputs["rho"]])
    reports_by_rho = risk_outputs.get("reports_by_rho", [(risk_outputs["rho"], report)])
    payload: dict[str, Any] = {
        "run_id": run_id,
        "n_bets": risk_outputs["n_bets"],
        "n_matchdays": risk_outputs["n_matchdays"],
        "n_positive_edge_bets": risk_outputs["n_positive_edge_bets"],
        "lambda_star_zero_dominates": risk_outputs["lambda_star_zero_dominates"],
        "ruin_monte_carlo": {
            "B": risk_outputs["ruin_b"],
            "B_precision_floor": risk_outputs["ruin_b_precision_floor"],
            "eps_target": risk_outputs["ruin_eps_target"],
            "se_ratio": risk_outputs["ruin_se_ratio"],
            "rho": risk_outputs["rho"],
            "rho_grid": rho_grid,
            "substream": "ruin-mc",
            "justification": (
                "B set by the precision target SE<=se_ratio*eps => "
                "B>=(1-eps)/(se_ratio^2 * eps); deployed B clears the floor (STAKE §6.3)"
            ),
        },
        # The primary (first-rho) per-scheme frontiers (back-compat top-level view).
        "scheme_frontiers": _serialise_scheme_frontiers(report),
        # EVERY ruin floor rho in the declared grid (methodology.md §1.1-§1.2: "Two values
        # are reported, not one"). The rho=0.5 behavioural stop-out -- the operationally
        # binding floor under the multiplicative schemes -- is reported here alongside the
        # rho=0.0 literal-bankruptcy benchmark, per scheme.
        "ruin_by_rho": [
            {"rho": float(r), "scheme_frontiers": _serialise_scheme_frontiers(rep)}
            for r, rep in reports_by_rho
        ],
        "brb_rck_grid": [
            {
                "alpha_dd": r.alpha_dd,
                "beta_dd": r.beta_dd,
                "theta": r.theta,
                "lambda_rck": r.lam_rck,
                "constraint_at_lambda": r.constraint_at_lam,
                "binds": r.binds,
            }
            for r in report.rck_grid
        ],
        "dd_quantile_level": report.dd_quantile_level,
    }
    indep = risk_outputs.get("independence_test")
    if indep is not None:
        payload["concurrent_independence_test"] = {
            "lr_statistic": indep.lr_statistic,
            "dof": indep.dof,
            "p_value": indep.p_value,
            "n_matchdays": indep.n_matchdays,
            "reject_independence": indep.reject_independence,
            "alpha": indep.alpha,
            "note": indep.note,
        }
    vk_gap = risk_outputs.get("vector_kelly_gap")
    if vk_gap is not None:
        payload["vector_kelly_growth_gap"] = vk_gap
    if report.required_if_edge_real is not None:
        payload["required_if_edge_real"] = asdict(report.required_if_edge_real)

    out = Path(logs_dir) / f"risk_frontier_{run_id}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(_json.dumps(payload, indent=2, default=float), encoding="utf-8", newline="\n")
    return out


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m src.run",
        description="Per-phase entrypoint (plan task 9); --dry-run validates the ReproLog.",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("config/baseline.yaml"),
        help="Path to the experiment config YAML (default: config/baseline.yaml).",
    )
    parser.add_argument(
        "--stage",
        choices=PHASE_STAGES,
        default="ingest",
        help=f"Pipeline stage to run (one of {', '.join(PHASE_STAGES)}).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Resolve config + emit a schema-valid ReproLog, then exit without compute.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.dry_run:
        out = dry_run(args.config, args.stage)
        print(f"dry-run OK: stage={args.stage} reprolog={out.relative_to(PROJECT_ROOT).as_posix()}")
        return 0
    if args.stage == "ingest":
        # Phase 1: real league-universe ingestion + canonical-panel assembly
        # (plan tasks 1 schema, 2, 2.1, 3, 3.1, 8, 9, 9.1).
        out, result = run_ingest_stage(args.config)
        gate = result.provenance_register.get("gate_passed", False)
        counts = getattr(result, "matches_counts", {"n_league": 0, "n_wc": 0})
        print(
            f"ingest OK: {result.panel.shape[0]} league rows from "
            f"{sum(1 for f in result.fetches if f.ok)}/{len(result.fetches)} files; "
            f"matches.parquet = {counts['n_league']} league + {counts['n_wc']} WC; "
            f"reprolog={out.relative_to(PROJECT_ROOT).as_posix()}; "
            f"pinnacle_gate_passed={gate}"
        )
        # The Pinnacle-degradation provenance gate is a HARD Phase-1 gate (task 3.1):
        # failing it blocks the 2026 headline verdict. Surface a nonzero exit so the
        # pipeline does not proceed on an unverified reference-cutover.
        return 0 if gate else 3
    if args.stage == "validate":
        # Phase 1: real data-quality gates + draw-rate base rates (tasks 6, 7; DATA §8).
        out, result = run_validate_stage(args.config)
        print(
            f"validate OK: {result.n_rows} rows ({result.n_league} league + {result.n_wc} WC); "
            f"gates_passed={result.gates_passed}; "
            f"data_quality={result.data_quality_path.relative_to(PROJECT_ROOT).as_posix()}; "
            f"reprolog={out.relative_to(PROJECT_ROOT).as_posix()}"
        )
        return 0 if result.gates_passed else 4
    if args.stage == "stake":
        # Phase 3: staking-scheme + costs + ledger pass over the league panel
        # (plan tasks 1, 2, 9). Net-of-cost is the reported figure (ADR-0004).
        out, facts = run_stake_stage(args.config)
        s = facts.summary
        rk = facts.risk
        print(
            f"stake OK: scheme={s['scheme']} n_bets={s['n_bets']} n_staked={s['n_staked']}; "
            f"slippage={facts.slippage.quantile_level}={facts.slippage.value:.6f} "
            f"(n_obs={facts.slippage.n_observable}); commission={facts.commission_rate:.4f}; "
            f"net_growth={s['net_growth_multiple']:.6f} (gross={s['gross_growth_multiple']:.6f}); "
            f"conservation_ok={s['conservation_ok']}; "
            f"reprolog={out.relative_to(PROJECT_ROOT).as_posix()}"
        )
        print(
            f"  risk: n_pos_edge={rk['n_positive_edge_bets']}/{rk['n_bets']} "
            f"lambda*=0_dominates={rk['lambda_star_zero_dominates']}; "
            f"ruin_MC B={rk['ruin_b']} (floor={rk['ruin_b_precision_floor']}); "
            f"frontier={facts.risk_path.relative_to(PROJECT_ROOT).as_posix()}"
        )
        return 0
    # The remaining per-stage compute (price/infer/report) lands in later phases;
    # Phase 1 implements `ingest`/`validate`; Phase 3 implements `stake`.
    sys.stderr.write(
        f"stage {args.stage!r} compute is not implemented yet; "
        "use --dry-run for the Phase-0 acceptance check.\n"
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
