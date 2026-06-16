"""Provenance-tracked raw-source fetch + checksum sidecar helpers.

Phase 1 (plan tasks 1, 4): every datum in ``data/raw/`` must carry provenance
(source URL + fetch context + SHA-256). This module centralizes the fetch ->
write -> checksum -> provenance-record flow so an ingest is reproducible-from-
snapshot (the committed-by-checksum file, NOT the source URL, is the canonical
input pinned in the ReproLog ``dataset_checksums`` -- plan task 4, §D.4).

Determinism / cross-platform (plan task 10c):
  * checksums are computed on NORMALIZED (LF) bytes via src.reprolog.sha256_text,
    so a CRLF/LF round-trip on Windows never breaks checksum equality;
  * pathlib only; no absolute paths in code.

NOTE on the WC-odds gap (plan task 4 / Phase-1 risk): there is no clean public
World-Cup ODDS source obtainable headlessly in this environment (OddsPortal is
JS-rendered + ToS-bound; every Kaggle/GitHub/Zenodo odds set traces back to
football-data.co.uk's DOMESTIC-only scope -- verified 2026-06-16). This module
therefore fetches the genuinely-accessible RESULTS sources for the WC settlement
panel; the odds gap is recorded honestly in the data-quality report and the
docs/protocol note, and the run-once scrape script (src/scrape_wc_odds.py) is
retained for provenance only.
"""

from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src import reprolog

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = PROJECT_ROOT / "data" / "raw"
PROVENANCE_DIR = RAW_DIR / "provenance"


def _curl(url: str) -> bytes:
    """Fetch ``url`` with curl (the env's reachable HTTPS client). Returns bytes.

    curl is used (not urllib) because the env fact sheet pins curl as the vetted
    HTTPS path; ``-sS`` is quiet-but-show-errors, ``-L`` follows redirects,
    ``--fail`` makes an HTTP>=400 a non-zero exit (no silent empty file).
    """
    out = subprocess.run(
        ["curl", "-sS", "-L", "--fail", url],
        capture_output=True,
        check=True,
    )
    return out.stdout


def fetch_to_raw(
    url: str,
    dest_name: str,
    *,
    source_label: str,
    snapshot_date: str,
    raw_dir: Path | None = None,
    note: str | None = None,
) -> dict[str, Any]:
    """Fetch ``url`` -> ``data/raw/<dest_name>`` + ``.sha256`` + a provenance JSON.

    Returns the provenance record dict (also written to
    ``data/raw/provenance/<dest_name>.provenance.json``). The SHA-256 is computed
    on LF-normalized bytes so it is the value pinned in the ReproLog
    ``dataset_checksums`` (plan §D.4, task 10c).
    """
    rdir = Path(raw_dir) if raw_dir is not None else RAW_DIR
    pdir = rdir / "provenance"
    rdir.mkdir(parents=True, exist_ok=True)
    pdir.mkdir(parents=True, exist_ok=True)

    raw_bytes = _curl(url)
    text = raw_bytes.decode("utf-8")
    digest = reprolog.sha256_text(text)

    dest = rdir / dest_name
    # Write LF-normalized so the on-disk bytes match the checksummed bytes.
    dest.write_text(text.replace("\r\n", "\n").replace("\r", "\n"), encoding="utf-8", newline="\n")

    sidecar = rdir / f"{dest_name}.sha256"
    # `<sha>  <name>` is the sha256sum-compatible sidecar format (LF).
    sidecar.write_text(f"{digest}  {dest_name}\n", encoding="utf-8", newline="\n")

    record = {
        "dest_name": dest_name,
        "source_url": url,
        "source_label": source_label,
        "snapshot_date": snapshot_date,
        "fetch_timestamp_utc": datetime.now(UTC).isoformat(),
        "sha256_lf": digest,
        "n_bytes_raw": len(raw_bytes),
        "note": note,
    }
    prov = pdir / f"{dest_name}.provenance.json"
    prov.write_text(
        json.dumps(record, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return record


def verify_sidecar(dest_name: str, raw_dir: Path | None = None) -> bool:
    """Recompute the LF-normalized SHA-256 and check it against the sidecar."""
    rdir = Path(raw_dir) if raw_dir is not None else RAW_DIR
    dest = rdir / dest_name
    sidecar = rdir / f"{dest_name}.sha256"
    if not (dest.exists() and sidecar.exists()):
        return False
    recorded = sidecar.read_text(encoding="utf-8").split()[0]
    return reprolog.sha256_path(dest) == recorded
