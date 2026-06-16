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
    # The remaining per-stage compute (price/stake/infer/report) lands in later
    # phases; Phase 1 implements `ingest` (incl. assembly) and `validate`.
    sys.stderr.write(
        f"stage {args.stage!r} compute is not implemented yet; "
        "use --dry-run for the Phase-0 acceptance check.\n"
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
