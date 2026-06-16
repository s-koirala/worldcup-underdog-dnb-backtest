"""ReproLog tests (plan task 3; acceptance: 13-named-key schema-valid record).

Covers: the exactly-13 named keys, the five CLAUDE.md-mandated keys present by
name, the zero-commit state (git_head null/"UNCOMMITTED", git_dirty true),
schema-by-name validation (missing key / extra key rejected), LF-normalized
checksum stability, and emit() writing logs/reprolog_<run_id>.json.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from src import reprolog

EXPECTED_KEYS = {
    "git_head",
    "git_dirty",
    "pip_freeze_sha256",
    "pip_freeze_path",
    "dataset_checksums",
    "data_vendor",
    "snapshot_date",
    "rng_seed",
    "config_resolved_sha256",
    "model_hash",
    "run_id",
    "timestamp",
    "runtime",
}
MANDATED = {"git_head", "pip_freeze_sha256", "dataset_checksums", "rng_seed", "model_hash"}


def test_schema_required_lists_exactly_13_keys():
    schema = reprolog.load_schema()
    required = schema["required"]
    assert len(required) == 13
    assert set(required) == EXPECTED_KEYS


def test_schema_lists_the_five_mandated_keys():
    schema = reprolog.load_schema()
    assert MANDATED.issubset(set(schema["required"]))
    assert set(reprolog.MANDATED_KEYS) == MANDATED


def test_module_mandated_keys_match_class_reexport():
    assert reprolog.ReproLog.MANDATED_KEYS == reprolog.MANDATED_KEYS


def _build(tmp_path: Path, **kw) -> reprolog.ReproLog:
    return reprolog.build(
        run_id=kw.pop("run_id", "test-run"),
        rng_seed=kw.pop("rng_seed", 20260616),
        logs_dir=tmp_path / "logs",
        **kw,
    )


def test_build_emits_record_with_exactly_13_keys(tmp_path):
    record = _build(tmp_path).to_record()
    assert set(record) == EXPECTED_KEYS


def test_validate_record_accepts_a_built_record(tmp_path):
    record = _build(tmp_path).to_record()
    reprolog.validate_record(record)  # must not raise


def test_validate_record_rejects_missing_mandated_key(tmp_path):
    record = _build(tmp_path).to_record()
    del record["rng_seed"]
    with pytest.raises(ValueError, match="missing required keys"):
        reprolog.validate_record(record)


def test_validate_record_rejects_extra_key(tmp_path):
    record = _build(tmp_path).to_record()
    record["surprise"] = 1
    with pytest.raises(ValueError, match="unexpected keys"):
        reprolog.validate_record(record)


def test_zero_commit_git_head_is_null_by_default():
    # The repo has zero commits; git_head must resolve to None (global rule 2).
    head = reprolog.git_head()
    assert head is None or head == reprolog.UNCOMMITTED


def test_zero_commit_sentinel_branch():
    head = reprolog.git_head(on_zero_commit=reprolog.UNCOMMITTED)
    # Either a real SHA (if commits ever exist) or the sentinel; never empty.
    assert head
    if head != reprolog.UNCOMMITTED:
        assert len(head) >= 7


def test_git_dirty_true_in_zero_commit_state():
    assert reprolog.git_dirty() is True


def test_build_handles_zero_commit(tmp_path):
    record = _build(tmp_path).to_record()
    assert record["git_head"] is None
    assert record["git_dirty"] is True
    reprolog.validate_record(record)


def test_build_with_uncommitted_sentinel(tmp_path):
    record = _build(tmp_path, zero_commit_head="UNCOMMITTED").to_record()
    assert record["git_head"] in (reprolog.UNCOMMITTED, None) or len(record["git_head"]) >= 7
    reprolog.validate_record(record)


def test_sha256_text_is_lf_normalized():
    assert reprolog.sha256_text("a\r\nb\r\n") == reprolog.sha256_text("a\nb\n")
    assert reprolog.sha256_text("a\rb") == reprolog.sha256_text("a\nb")


def test_emit_writes_reprolog_file(tmp_path):
    logs = tmp_path / "logs"
    record = reprolog.build(run_id="emit-test", rng_seed=1, logs_dir=logs)
    out = record.emit(logs_dir=logs)
    assert out == logs / "reprolog_emit-test.json"
    assert out.exists()
    text = out.read_text(encoding="utf-8")
    assert "\r\n" not in text  # LF only
    reloaded = json.loads(text)
    assert set(reloaded) == EXPECTED_KEYS
    reprolog.validate_record(reloaded)


class _FakeCompleted:
    """Minimal stand-in for subprocess.CompletedProcess."""

    def __init__(self, returncode: int, stdout: str = "", stderr: str = ""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _stub_subprocess_run(monkeypatch, *, uv_behavior, pip_stdout):
    """Patch reprolog.subprocess.run so the uv branch behaves as specified and the
    pip-fallback branch returns a controlled stdout. Records the commands seen so
    the test can assert the fallback was actually taken. Does NOT depend on uv or
    pip being installed in the test env (this uv-managed venv ships without pip)."""
    seen: list[list[str]] = []

    def fake_run(cmd, *args, **kwargs):
        seen.append(list(cmd))
        if cmd and cmd[0] == "uv":
            if uv_behavior == "missing":
                raise FileNotFoundError("uv not on PATH")
            if uv_behavior == "nonzero":
                return _FakeCompleted(returncode=1, stderr="uv pip freeze failed")
            raise AssertionError(f"unexpected uv_behavior {uv_behavior!r}")
        # The pip fallback branch (sys.executable -m pip freeze).
        return _FakeCompleted(returncode=0, stdout=pip_stdout)

    monkeypatch.setattr(reprolog.subprocess, "run", fake_run)
    return seen


def test_pip_freeze_falls_back_to_pip_when_uv_missing(monkeypatch):
    """If `uv` is not on PATH, subprocess.run raises FileNotFoundError before any
    return code exists; pip_freeze must catch that (OSError) and fall back to the
    interpreter's pip, not crash. Regression for the docstring promise that the
    fallback fires when uv is *unavailable*, not only when it returns nonzero.
    """
    seen = _stub_subprocess_run(monkeypatch, uv_behavior="missing", pip_stdout="pkg==1.0\n")
    freeze = reprolog.pip_freeze()
    assert freeze == "pkg==1.0\n"
    # The pip fallback was actually invoked (uv raised, did not return).
    assert any(cmd[1:] == ["-m", "pip", "freeze"] for cmd in seen), (
        "pip fallback must run when uv raises FileNotFoundError"
    )


def test_pip_freeze_falls_back_to_pip_when_uv_nonzero(monkeypatch):
    """The original guard: uv on PATH but returns nonzero -> pip fallback."""
    seen = _stub_subprocess_run(monkeypatch, uv_behavior="nonzero", pip_stdout="pkg==2.0\n")
    freeze = reprolog.pip_freeze()
    assert freeze == "pkg==2.0\n"
    assert any(cmd[1:] == ["-m", "pip", "freeze"] for cmd in seen)


def test_dataset_checksums_default_empty_and_seed_nonnegative(tmp_path):
    record = _build(tmp_path).to_record()
    assert record["dataset_checksums"] == {}
    assert record["rng_seed"] >= 0
    assert record["runtime"]["python_version"]
    assert record["runtime"]["platform"]
