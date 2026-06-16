"""ReproLog: the 13-named-key reproducibility envelope.

Phase 0 task 3 (plan §C; plan §D.4; ARCH §3.2; CLAUDE.md reproducibility mandate).

Emitted before ANY artifact write. The record has EXACTLY 13 named atomic keys
(plan Phase 0 Methods, keys 1-13). The five CLAUDE.md-mandated keys are present
by name: git_head (1), pip_freeze_sha256 (3), dataset_checksums (5),
rng_seed (8), model_hash (10).

Single source of truth for the 13 keys is config/reprolog_schema.json; this
pydantic model mirrors it, and emit() validates the serialized record against
that committed JSON Schema BY KEY NAME (not by asserting a bare integer 13).

Pre-first-commit state: the repo currently has zero commits and a deliberately
unset git author identity, so a commit fails by design. emit() handles that
gracefully -- git_head is null (or "UNCOMMITTED") and git_dirty is true -- so the
Phase 0 --dry-run works with zero commits (global rule 2).
"""

from __future__ import annotations

import hashlib
import json
import platform as _platform
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field

# Repo-relative anchors (no absolute paths in code; plan task 10a).
_THIS_FILE = Path(__file__).resolve()
PROJECT_ROOT = _THIS_FILE.parent.parent
SCHEMA_PATH = PROJECT_ROOT / "config" / "reprolog_schema.json"
LOGS_DIR = PROJECT_ROOT / "logs"

SCHEMA_VERSION = "1.0.0"

# Sentinel HEAD value for the pre-first-commit state when a non-null marker is
# preferred over null (both are schema-valid for git_head).
UNCOMMITTED = "UNCOMMITTED"

_SHA256_HEX = r"^[0-9a-f]{64}$"
Sha256Hex = Annotated[str, Field(pattern=_SHA256_HEX)]

# The five CLAUDE.md-mandated keys, by name (keys 1, 3, 5, 8, 10), for the
# dry-run by-name assertion. Module-level so pydantic does not treat it as a
# record field.
MANDATED_KEYS: tuple[str, ...] = (
    "git_head",
    "pip_freeze_sha256",
    "dataset_checksums",
    "rng_seed",
    "model_hash",
)


class Runtime(BaseModel):
    """Key 13 sub-object: interpreter + OS/arch fingerprint."""

    model_config = ConfigDict(extra="forbid")

    python_version: str
    platform: str

    @classmethod
    def capture(cls) -> Runtime:
        return cls(
            python_version=_platform.python_version(),
            platform=_platform.platform(),
        )


class ReproLog(BaseModel):
    """The 13-named-key reproducibility record (plan Methods keys 1-13)."""

    model_config = ConfigDict(extra="forbid")

    # Key 1 -- CLAUDE.md-mandated (git HEAD). Nullable for the zero-commit state.
    git_head: str | None
    # Key 2.
    git_dirty: bool
    # Key 3 -- CLAUDE.md-mandated (project-venv pip freeze).
    pip_freeze_sha256: Sha256Hex
    # Key 4.
    pip_freeze_path: str
    # Key 5 -- CLAUDE.md-mandated (dataset checksum).
    dataset_checksums: dict[str, Sha256Hex] = Field(default_factory=dict)
    # Key 6.
    data_vendor: str | None = None
    # Key 7.
    snapshot_date: str | None = None
    # Key 8 -- CLAUDE.md-mandated (RNG seed). The no-magic-number exemption.
    rng_seed: int = Field(ge=0)
    # Key 9.
    config_resolved_sha256: Annotated[str, Field(pattern=_SHA256_HEX)] | None = None
    # Key 10 -- CLAUDE.md-mandated (model commit hash).
    model_hash: str | None = None
    # Key 11.
    run_id: str = Field(min_length=1)
    # Key 12.
    timestamp: str
    # Key 13.
    runtime: Runtime

    # Re-export of the module-level constant for callers using ReproLog.MANDATED_KEYS.
    MANDATED_KEYS: ClassVar[tuple[str, ...]] = MANDATED_KEYS

    def to_record(self) -> dict:
        """Serialize to the plain dict written to disk and validated by schema."""
        return self.model_dump(mode="json")

    def emit(self, logs_dir: Path | None = None) -> Path:
        """Write logs/reprolog_<run_id>.json and validate against the schema.

        Returns the written path. Raises if the serialized record does not
        validate against config/reprolog_schema.json by key name.
        """
        record = self.to_record()
        validate_record(record)
        out_dir = Path(logs_dir) if logs_dir is not None else LOGS_DIR
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"reprolog_{self.run_id}.json"
        # LF newlines; deterministic key order for byte-stable comparison.
        text = json.dumps(record, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
        out_path.write_text(text, encoding="utf-8", newline="\n")
        return out_path


# --------------------------------------------------------------------------
# Field collectors (pre-first-commit safe).
# --------------------------------------------------------------------------


def git_head(repo_root: Path | None = None, *, on_zero_commit: str | None = None) -> str | None:
    """Return HEAD commit SHA, or ``on_zero_commit`` (default None) when there
    are no commits / not a usable repo (zero-commit state; global rule 2)."""
    root = Path(repo_root) if repo_root is not None else PROJECT_ROOT
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
        )
    except (OSError, FileNotFoundError):
        return on_zero_commit
    if out.returncode != 0:
        # "fatal: ... does not have any commits yet" -> graceful null/sentinel.
        return on_zero_commit
    return out.stdout.strip() or on_zero_commit


def git_dirty(repo_root: Path | None = None) -> bool:
    """Return True if the working tree has uncommitted changes. In the
    zero-commit state every tracked-candidate file is untracked, so this is
    True by design."""
    root = Path(repo_root) if repo_root is not None else PROJECT_ROOT
    try:
        out = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
        )
    except (OSError, FileNotFoundError):
        return True
    if out.returncode != 0:
        return True
    return bool(out.stdout.strip())


def pip_freeze(repo_root: Path | None = None) -> str:
    """Return the project-venv `uv pip freeze` text (env fingerprint, ARCH §3.2).

    Falls back to the running interpreter's `pip` if uv is unavailable. "Unavailable"
    has two failure modes that must BOTH route to the fallback: (a) uv is on PATH but
    returns nonzero, and (b) uv is NOT on PATH at all, in which case subprocess.run
    raises FileNotFoundError (a subclass of OSError) before any return code exists.
    The original guard only caught (a); (b) crashed with an unhandled OSError. Both
    are now wrapped, mirroring the (OSError, FileNotFoundError) handling in git_head /
    git_dirty (https://docs.python.org/3/library/subprocess.html#subprocess.run).
    """
    root = Path(repo_root) if repo_root is not None else PROJECT_ROOT
    try:
        out = subprocess.run(
            ["uv", "pip", "freeze"],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
        )
        uv_ok = out.returncode == 0
    except OSError:
        # uv not on PATH (FileNotFoundError) or otherwise unspawnable -> fall back.
        uv_ok = False
    if not uv_ok:
        # Fall back to the running interpreter's pip if uv is unavailable.
        out = subprocess.run(
            [sys.executable, "-m", "pip", "freeze"],
            cwd=root,
            capture_output=True,
            text=True,
            check=True,
        )
    return out.stdout


def sha256_text(text: str) -> str:
    """SHA-256 of text on NORMALIZED (LF) bytes (plan task 10c; CRLF-stable)."""
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def sha256_path(path: Path) -> str:
    """SHA-256 of a file's bytes, normalized to LF (plan task 10c)."""
    return sha256_text(Path(path).read_text(encoding="utf-8"))


def capture_pip_freeze(
    run_id: str, repo_root: Path | None = None, logs_dir: Path | None = None
) -> tuple[str, str]:
    """Write the freeze text under logs/ and return (sha256_hex, repo_rel_path)."""
    root = Path(repo_root) if repo_root is not None else PROJECT_ROOT
    out_dir = Path(logs_dir) if logs_dir is not None else (root / "logs")
    out_dir.mkdir(parents=True, exist_ok=True)
    freeze = pip_freeze(root)
    digest = sha256_text(freeze)
    freeze_path = out_dir / f"pip_freeze_{run_id}.txt"
    freeze_path.write_text(freeze.replace("\r\n", "\n"), encoding="utf-8", newline="\n")
    # Repo-relative POSIX path in the normal case (logs_dir under repo_root). When
    # logs_dir is decoupled from repo_root (e.g. a temp dir in tests), the freeze
    # path is not a subpath of root, so fall back to its POSIX string rather than
    # raising on relative_to.
    try:
        rel = freeze_path.relative_to(root).as_posix()
    except ValueError:
        rel = freeze_path.as_posix()
    return digest, rel


# --------------------------------------------------------------------------
# Builder + schema validation.
# --------------------------------------------------------------------------


def build(
    *,
    run_id: str,
    rng_seed: int,
    repo_root: Path | None = None,
    logs_dir: Path | None = None,
    dataset_checksums: dict[str, str] | None = None,
    data_vendor: str | None = None,
    snapshot_date: str | None = None,
    config_resolved_sha256: str | None = None,
    model_hash: str | None = None,
    zero_commit_head: Literal[None, "UNCOMMITTED"] = None,
) -> ReproLog:
    """Assemble a fully-populated ReproLog, collecting git/env fields safely in
    the pre-first-commit state.

    ``zero_commit_head`` controls the git_head value when there are no commits:
    ``None`` (default, schema-valid null) or the ``"UNCOMMITTED"`` sentinel.
    """
    root = Path(repo_root) if repo_root is not None else PROJECT_ROOT
    freeze_sha, freeze_path = capture_pip_freeze(run_id, root, logs_dir)
    return ReproLog(
        git_head=git_head(root, on_zero_commit=zero_commit_head),
        git_dirty=git_dirty(root),
        pip_freeze_sha256=freeze_sha,
        pip_freeze_path=freeze_path,
        dataset_checksums=dataset_checksums or {},
        data_vendor=data_vendor,
        snapshot_date=snapshot_date,
        rng_seed=rng_seed,
        config_resolved_sha256=config_resolved_sha256,
        model_hash=model_hash,
        run_id=run_id,
        timestamp=datetime.now(UTC).isoformat(),
        runtime=Runtime.capture(),
    )


def load_schema(schema_path: Path | None = None) -> dict:
    """Load the committed JSON Schema (the single source of truth for the 13 keys)."""
    path = Path(schema_path) if schema_path is not None else SCHEMA_PATH
    return json.loads(path.read_text(encoding="utf-8"))


def validate_record(record: dict, schema_path: Path | None = None) -> None:
    """Validate a serialized record against the committed schema BY KEY NAME.

    Asserts (a) all 13 named keys present, (b) no extra keys, (c) the five
    CLAUDE.md-mandated keys present by name, (d) the record satisfies the
    JSON Schema. Raises ValueError on any failure. Uses pydantic (no jsonschema
    dependency) for structural validation, plus an explicit by-name key check so
    the acceptance criterion is enforced against the schema's `required` list,
    not a hand-counted integer.
    """
    schema = load_schema(schema_path)
    required = list(schema["required"])
    if len(required) != 13:
        raise ValueError(f"schema 'required' must list exactly 13 keys, found {len(required)}")
    keys = set(record)
    missing = set(required) - keys
    if missing:
        raise ValueError(f"ReproLog missing required keys by name: {sorted(missing)}")
    if not schema.get("additionalProperties", True):
        extra = keys - set(schema["properties"])
        if extra:
            raise ValueError(f"ReproLog has unexpected keys: {sorted(extra)}")
    for k in MANDATED_KEYS:
        if k not in keys:
            raise ValueError(f"CLAUDE.md-mandated key missing by name: {k!r}")
    # Round-trip through the pydantic model to validate types/patterns.
    ReproLog.model_validate(record)
