"""Identity-hygiene gate tests (plan task 2.1; acceptance: fail-closed before commit).

Covers: the gate fails closed when the SKIE pseudonym email is unset (the current
zero-commit state); fails when the configured email equals the known real address;
flags a real-email / OS-username token in author identity; and the env override.
The repo has zero commits and user.email is unset, so run_gate() MUST be blocked.
"""

from __future__ import annotations

import textwrap

from src import identity_gate as ig


def test_gate_blocks_in_current_unprovisioned_state():
    # user.email unset + skie_git_email null => fail-closed (commit refused).
    result = ig.run_gate()
    assert not result.ok
    assert result.violations


def test_fail_closed_when_pseudonym_email_unset():
    v = ig.check_git_identity(ig.PROJECT_ROOT, {"skie_git_name": "SKIE"})
    assert any("FAIL-CLOSED" in m and "not provisioned" in m for m in v)


def test_fail_closed_when_configured_email_is_real_identity():
    cfg = {"skie_git_email": ig.REAL_EMAIL, "skie_git_name": "SKIE"}
    v = ig.check_git_identity(ig.PROJECT_ROOT, cfg)
    assert any("equals the known real address" in m for m in v)


def test_env_override_supplies_pseudonym_email(monkeypatch):
    monkeypatch.setenv("SKIE_GIT_EMAIL", "skie@pseudonym.example")
    cfg = ig.load_identity_config()
    assert cfg["skie_git_email"] == "skie@pseudonym.example"


def test_env_override_does_not_whitelist_the_real_email(monkeypatch):
    monkeypatch.setenv("SKIE_GIT_EMAIL", ig.REAL_EMAIL)
    cfg = ig.load_identity_config()
    v = ig.check_git_identity(ig.PROJECT_ROOT, cfg)
    assert any("equals the known real address" in m for m in v)


def test_real_email_token_constant():
    assert ig.REAL_EMAIL == "skoirala2625@gmail.com"
    assert ig.OS_USERNAME == "skoir"


def test_notebook_metadata_token_scan_detects_author():
    nb = textwrap.dedent(
        """
        {"metadata": {"authors": [{"name": "skoir"}], "kernelspec": {"name": "py"}},
         "cells": []}
        """
    ).strip()
    meta_text = ig._notebook_metadata_tokens(nb)
    assert "skoir" in meta_text


def test_main_returns_one_when_blocked():
    # In the current unprovisioned/zero-commit state the gate blocks (exit 1).
    assert ig.main() == 1
