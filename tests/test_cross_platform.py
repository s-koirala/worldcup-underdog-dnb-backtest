"""Cross-platform reproducibility controls (plan task 10; §D.7).

Covers: the no-absolute-path lint (task 10a) over src/ -- no `C:\\` or `/Users/`
literals outside config/; pathlib-only (no `os.path` import in src/); the
.gitattributes LF rules are present (task 10b); the config spawn map mirrors
src.seeding.STAGE_SPAWN_MAP byte-for-byte; and the committed fixture parses.
"""

from __future__ import annotations

import csv
from pathlib import Path

import yaml
from src import seeding

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC = PROJECT_ROOT / "src"

# Needles built so this test file itself does not contain the literal a naive
# grep would flag (it would otherwise match its own source under tests/).
DRIVE_NEEDLE = "C:" + "\\"
USERS_NEEDLE = "/Users" + "/"


def _src_py_files():
    return sorted(SRC.rglob("*.py"))


def test_no_absolute_path_literals_in_src():
    offenders = []
    for path in _src_py_files():
        text = path.read_text(encoding="utf-8")
        if DRIVE_NEEDLE in text or USERS_NEEDLE in text:
            offenders.append(path.relative_to(PROJECT_ROOT).as_posix())
    assert not offenders, f"absolute-path literals outside config/: {offenders}"


def test_no_os_path_concatenation_in_src():
    # pathlib only (task 10a); flag `import os.path` / `from os import path` /
    # `os.path.join`. Bare `import os` is allowed (identity_gate uses os.environ).
    offenders = []
    for path in _src_py_files():
        text = path.read_text(encoding="utf-8")
        if "os.path" in text or "from os import path" in text:
            offenders.append(path.relative_to(PROJECT_ROOT).as_posix())
    assert not offenders, f"os.path usage (use pathlib): {offenders}"


def test_gitattributes_present_with_lf_rules():
    ga = PROJECT_ROOT / ".gitattributes"
    assert ga.exists()
    text = ga.read_text(encoding="utf-8")
    assert "* text=auto" in text
    assert "*.csv text eol=lf" in text
    assert "*.sha256 text eol=lf" in text


def test_config_spawn_map_mirrors_seeding_module():
    cfg = yaml.safe_load((PROJECT_ROOT / "config" / "baseline.yaml").read_text(encoding="utf-8"))
    config_map = cfg["seeding"]["stage_spawn_map"]
    assert config_map == dict(seeding.STAGE_SPAWN_MAP), (
        "config/baseline.yaml seeding.stage_spawn_map must equal "
        "src.seeding.STAGE_SPAWN_MAP byte-for-byte"
    )


def test_committed_fixture_parses():
    fixture = PROJECT_ROOT / "tests" / "fixtures" / "mini_league.csv"
    assert fixture.exists()
    with fixture.open(encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    assert len(rows) >= 5
    required_cols = {"Div", "Date", "HomeTeam", "AwayTeam", "FTR", "PSCH", "PSCD", "PSCA"}
    assert required_cols.issubset(set(rows[0]))
    assert {r["FTR"] for r in rows} <= {"H", "D", "A"}
