"""Dry-run entrypoint tests (plan task 3 + task 9 + task 10 acceptance).

Covers: --dry-run resolves the config, emits a ReproLog that validates against
the committed 13-named-key schema, and exits without compute; two same-seed runs
produce a byte-identical resolved-config SHA (determinism / platform invariance);
the config_resolved_sha256 is recorded; every phase stage resolves.

Every dry_run() here writes to an isolated tmp logs dir so the suite never
pollutes the project logs/ directory.
"""

from __future__ import annotations

import json

import pytest
from src import reprolog, run

CONFIG = run.PROJECT_ROOT / "config" / "baseline.yaml"


def _load_emitted(path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_dry_run_emits_schema_valid_reprolog(tmp_path):
    out = run.dry_run(CONFIG, "ingest", run_id="dryrun-ingest-1", logs_dir=tmp_path)
    record = _load_emitted(out)
    reprolog.validate_record(record)
    assert record["rng_seed"] == 20260616
    assert record["config_resolved_sha256"] is not None
    assert len(record["config_resolved_sha256"]) == 64
    assert record["git_dirty"] is True
    assert record["git_head"] is None or record["git_head"] == reprolog.UNCOMMITTED


def test_two_same_seed_runs_give_identical_config_sha(tmp_path):
    a = run.dry_run(CONFIG, "ingest", run_id="dryrun-a", logs_dir=tmp_path / "a")
    b = run.dry_run(CONFIG, "ingest", run_id="dryrun-b", logs_dir=tmp_path / "b")
    ra, rb = _load_emitted(a), _load_emitted(b)
    # Same seed + same config + same stage => identical resolved-config SHA
    # (platform-invariant; Phase 0 acceptance).
    assert ra["config_resolved_sha256"] == rb["config_resolved_sha256"]


def test_config_sha_is_stage_sensitive(tmp_path):
    a = run.dry_run(CONFIG, "ingest", run_id="dryrun-stage-a", logs_dir=tmp_path / "a")
    b = run.dry_run(CONFIG, "infer", run_id="dryrun-stage-b", logs_dir=tmp_path / "b")
    ra, rb = _load_emitted(a), _load_emitted(b)
    assert ra["config_resolved_sha256"] != rb["config_resolved_sha256"]


def test_canonical_config_json_is_sorted_lf():
    s = run.canonical_config_json({"b": 1, "a": 2})
    assert s == '{"a":2,"b":1}'  # sorted keys, no spaces


@pytest.mark.parametrize("stage", run.PHASE_STAGES)
def test_every_phase_stage_resolves_in_dry_run(stage, tmp_path):
    out = run.dry_run(CONFIG, stage, run_id=f"dryrun-{stage}", logs_dir=tmp_path)
    assert out.exists()
    reprolog.validate_record(_load_emitted(out))


def test_main_dry_run_exit_zero():
    # The real CLI writes to the project logs/ dir; clean up ONLY the artifacts THIS
    # call created -- never a blanket glob-delete of logs/reprolog_validate-*.json,
    # which would also destroy the ReproLog a real `--stage validate` run emitted
    # (the Phase-1 acceptance criterion requires that record to persist). Snapshot
    # the pre-existing files and remove only the set difference afterwards.
    rl_glob = "logs/reprolog_validate-*.json"
    pf_glob = "logs/pip_freeze_validate-*.txt"
    before_rl = set(run.PROJECT_ROOT.glob(rl_glob))
    before_pf = set(run.PROJECT_ROOT.glob(pf_glob))
    rc = run.main(["--config", "config/baseline.yaml", "--stage", "validate", "--dry-run"])
    assert rc == 0
    for p in set(run.PROJECT_ROOT.glob(rl_glob)) - before_rl:
        p.unlink(missing_ok=True)
    for p in set(run.PROJECT_ROOT.glob(pf_glob)) - before_pf:
        p.unlink(missing_ok=True)


def test_main_without_dry_run_is_not_implemented_for_later_stages():
    # Phase 1 implements `ingest`; the later-phase stages are still not implemented
    # and return exit 2 (use --dry-run for their Phase-0 acceptance check).
    rc = run.main(["--config", "config/baseline.yaml", "--stage", "price"])
    assert rc == 2  # compute not implemented yet for this stage


def test_root_seed_from_config_reads_seeding_block():
    cfg = run.load_config(CONFIG)
    assert run.root_seed_from_config(cfg) == 20260616


def test_config_seed_matches_seeding_root_seed():
    """seeding.root_seed and inference.seed must mirror (config consistency)."""
    cfg = run.load_config(CONFIG)
    assert cfg["seeding"]["root_seed"] == cfg["inference"]["seed"]
