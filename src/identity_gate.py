"""Fail-closed git-author identity-hygiene gate (Phase 0 task 2.1).

Load-bearing: the venue is publication under the SKIE pseudonym
(rules/publishing.md identity hygiene). The repo has zero commits, so the FIRST
commit is the leak point -- the authoring environment exposes a real OS username
(`skoir`) and a personal Gmail. This gate runs as a pre-commit hook and BLOCKS
(exit 1) on any of:

  1. ``git config user.email`` unset, or NOT the configured SKIE pseudonym, or
     equal to the known real address (skoirala2625@gmail.com).
  2. ``git config user.name`` not the configured SKIE pseudonym name.
  3. ``user.useConfigOnly`` not true (Git would otherwise synthesize an
     OS-derived identity).
  4. The OS username (`skoir`) or the real email appearing in the author
     name/email, any STAGED file's content, or notebook metadata
     (kernelspec / metadata.authors).

The SKIE pseudonym email is NOT known in this environment, so it is read from a
placeholder -- config/baseline.yaml ``identity_hygiene.skie_git_email`` or the
``SKIE_GIT_EMAIL`` env var. If that placeholder is unset OR equals the known
real address, the gate FAILS CLOSED (the safe default before the pseudonym is
provisioned). This module performs NO commit.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BASELINE_CONFIG = PROJECT_ROOT / "config" / "baseline.yaml"

# Known REAL identity tokens that must never enter committed history.
REAL_EMAIL = "skoirala2625@gmail.com"
OS_USERNAME = "skoir"


class GateResult:
    """Outcome of the gate: ``ok`` plus the list of violation messages."""

    def __init__(self, violations: list[str]):
        self.violations = violations

    @property
    def ok(self) -> bool:
        return not self.violations

    def __bool__(self) -> bool:
        return self.ok


def _git(args: list[str], repo_root: Path) -> tuple[int, str]:
    out = subprocess.run(["git", *args], cwd=repo_root, capture_output=True, text=True, check=False)
    return out.returncode, out.stdout.strip()


def load_identity_config(config_path: Path | None = None) -> dict[str, Any]:
    """Load the identity_hygiene block; env var SKIE_GIT_EMAIL overrides config."""
    path = Path(config_path) if config_path is not None else BASELINE_CONFIG
    cfg: dict[str, Any] = {}
    if path.exists():
        loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        cfg = loaded.get("identity_hygiene", {}) or {}
    env_email = os.environ.get("SKIE_GIT_EMAIL")
    if env_email:
        cfg = {**cfg, "skie_git_email": env_email}
    return cfg


def _resolve_expected(cfg: dict[str, Any]) -> tuple[str | None, str, str, str]:
    expected_email = cfg.get("skie_git_email")
    expected_name = cfg.get("skie_git_name") or "SKIE"
    forbidden_email = cfg.get("forbidden_email") or REAL_EMAIL
    forbidden_user = cfg.get("forbidden_os_username") or OS_USERNAME
    return expected_email, expected_name, forbidden_email, forbidden_user


def check_git_identity(repo_root: Path, cfg: dict[str, Any]) -> list[str]:
    """Author identity + useConfigOnly checks (gate items 1-3)."""
    v: list[str] = []
    expected_email, expected_name, forbidden_email, _ = _resolve_expected(cfg)

    if not expected_email:
        v.append(
            "FAIL-CLOSED: SKIE pseudonym email is not provisioned "
            "(config identity_hygiene.skie_git_email / env SKIE_GIT_EMAIL is unset). "
            "Set it to the pseudonym address before any commit."
        )
    elif expected_email == forbidden_email:
        v.append(
            "FAIL-CLOSED: configured SKIE email equals the known real address "
            f"({forbidden_email}); it must be the pseudonym, not the real identity."
        )

    rc_e, cfg_email = _git(["config", "user.email"], repo_root)
    if rc_e != 0 or not cfg_email:
        v.append("git config user.email is unset (useConfigOnly will refuse the commit).")
    else:
        if cfg_email == forbidden_email:
            v.append(f"git user.email is the real address {forbidden_email}.")
        if expected_email and cfg_email != expected_email:
            v.append(
                f"git user.email {cfg_email!r} != configured SKIE pseudonym {expected_email!r}."
            )

    rc_n, cfg_name = _git(["config", "user.name"], repo_root)
    if rc_n != 0 or not cfg_name:
        v.append("git config user.name is unset.")
    elif cfg_name != expected_name:
        v.append(f"git user.name {cfg_name!r} != configured SKIE pseudonym {expected_name!r}.")

    rc_u, use_config_only = _git(["config", "user.useConfigOnly"], repo_root)
    if rc_u != 0 or use_config_only.lower() != "true":
        v.append("git user.useConfigOnly is not 'true' (Git may synthesize an OS identity).")

    return v


def _staged_files(repo_root: Path) -> list[str]:
    rc, out = _git(["diff", "--cached", "--name-only", "--diff-filter=ACMR"], repo_root)
    if rc != 0 or not out:
        return []
    return [line for line in out.splitlines() if line.strip()]


def _staged_blob(repo_root: Path, path: str) -> str | None:
    out = subprocess.run(
        ["git", "show", f":{path}"], cwd=repo_root, capture_output=True, check=False
    )
    if out.returncode != 0:
        return None
    return out.stdout.decode("utf-8", errors="replace")


def _notebook_metadata_tokens(text: str) -> str:
    """Return notebook kernelspec + metadata.authors text for token scanning."""
    try:
        nb = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return ""
    meta = nb.get("metadata", {}) if isinstance(nb, dict) else {}
    parts = [json.dumps(meta.get("kernelspec", {})), json.dumps(meta.get("authors", []))]
    return " ".join(parts)


def scan_staged_content(repo_root: Path, cfg: dict[str, Any]) -> list[str]:
    """Scan staged files (and notebook metadata) for forbidden tokens (item 4)."""
    v: list[str] = []
    _, _, forbidden_email, forbidden_user = _resolve_expected(cfg)
    needles = {"real email": forbidden_email, "OS username": forbidden_user}

    for path in _staged_files(repo_root):
        blob = _staged_blob(repo_root, path)
        if blob is None:
            continue
        for label, needle in needles.items():
            if needle and needle in blob:
                v.append(f"staged file {path!r} contains the {label} token {needle!r}.")
        if path.endswith(".ipynb"):
            meta_text = _notebook_metadata_tokens(blob)
            for label, needle in needles.items():
                if needle and needle in meta_text:
                    v.append(f"notebook {path!r} metadata contains the {label} token {needle!r}.")
    return v


def run_gate(repo_root: Path | None = None, config_path: Path | None = None) -> GateResult:
    """Run all checks and return the aggregated result (no side effects)."""
    root = Path(repo_root) if repo_root is not None else PROJECT_ROOT
    cfg = load_identity_config(config_path)
    violations = check_git_identity(root, cfg) + scan_staged_content(root, cfg)
    return GateResult(violations)


def main(argv: list[str] | None = None) -> int:
    """Pre-commit entry point. Exit 0 only if the gate is clean; else exit 1."""
    result = run_gate()
    if result.ok:
        print("identity-hygiene gate: OK")
        return 0
    sys.stderr.write("identity-hygiene gate: BLOCKED (commit refused)\n")
    for msg in result.violations:
        sys.stderr.write(f"  - {msg}\n")
    sys.stderr.write(
        "\nFix: set git user.name/user.email to the SKIE pseudonym, set "
        "identity_hygiene.skie_git_email (or SKIE_GIT_EMAIL), and remove the "
        "real-identity tokens from staged content.\n"
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
