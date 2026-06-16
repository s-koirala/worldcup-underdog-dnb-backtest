"""Run-once World-Cup ODDS scrape script -- RETAINED FOR PROVENANCE ONLY.

Phase 1 task 4 / Phase-1 risk (plan): there is NO clean public World-Cup 1X2
closing-odds CSV (DATA §2.2). Every path is a ToS-governed, JS-rendered,
rate-limited HTML scrape that CANNOT be re-derived byte-for-byte from a source
URL. This script documents the intended one-time scrape so that IF a scrape is
performed (out-of-band, by a human operator who has accepted the site ToS), its
output is frozen as a checksummed snapshot:

    data/raw/wc_odds_<snapshot_date>.csv   + .sha256   (+ provenance JSON)

and THAT committed-by-checksum artifact -- not the source URL -- is pinned in
``config`` and the ReproLog ``dataset_checksums``. The held-out WC analysis is
then reproducible-FROM-SNAPSHOT, not reproducible-from-source (plan §D.4, task 4).

STATUS (2026-06-16): NOT RUN in this environment.
  * OddsPortal (oddsportal.com) returns a JS-rendered shell with NO odds in the
    static HTML (verified headlessly: the World-Cup-2022 results page returned
    only navigation chrome, no scores/odds), and its ToS prohibits scraping.
  * Covers (covers.com) is similarly JS/ToS-bound.
  * No licensed machine-readable free WC odds product exists (The Odds API
    historical is metered + key-gated; not obtainable headlessly here).
This script is therefore a PROVENANCE ARTIFACT and a contract for a future
operator, not an executable pipeline step. Running it requires:
  (i)  a browser-automation backend (Playwright/Selenium) the operator installs;
  (ii) explicit acceptance of the target site's ToS by that operator;
  (iii) a per-selection capture of BOTH the opening and the closing price where
        the source carries line movement (so CLV is defined; gaps register
        "open->close (CLV) line capture on the WC scrape").

Because the scrape is inherently non-deterministic (page markup changes, JS
render timing, rate-limited partial pulls), it is NOT wired into ``make
reproduce-data``; the deterministic, reproducible step is consuming the FROZEN
snapshot hash.
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = PROJECT_ROOT / "data" / "raw"

# Target editions and the canonical 1X2 + AH columns a scrape must capture so the
# output is directly consumable by the Phase-2 pricing module. Closing is the
# point-in-time decision line (DATA §5); opening enables CLV (task 10).
TARGET_EDITIONS: tuple[int, ...] = (2002, 2006, 2010, 2014, 2018, 2022, 2026)

REQUIRED_COLUMNS: tuple[str, ...] = (
    "competition",  # e.g. WC2018
    "season",
    "date",
    "kickoff_utc",
    "home_team",
    "away_team",
    # 1X2 closing (synthetic-DNB source) + opening (CLV entry):
    "open_H",
    "open_D",
    "open_A",
    "close_H",
    "close_D",
    "close_A",
    # native AH-0.0 where the source carries it (>= 2019/20 only): the genuine
    # quoted-DNB price preferred over synthetic (CALC §3.5).
    "ah0_close_home",
    "ah0_close_away",
    "source_url",
    "fetch_timestamp_utc",
)


def main() -> int:
    sys.stderr.write(
        "src/scrape_wc_odds.py is a PROVENANCE-ONLY contract, not an executable\n"
        "pipeline step. No headless WC-odds source is obtainable in this\n"
        "environment (OddsPortal/Covers are JS+ToS-bound; all public CSV/Kaggle/\n"
        "GitHub/Zenodo odds sets are football-data.co.uk DOMESTIC-only). To freeze\n"
        "a snapshot, a human operator must run a browser-automation backend under\n"
        "the site ToS and write data/raw/wc_odds_<snapshot_date>.csv with the\n"
        f"columns {REQUIRED_COLUMNS} for editions {TARGET_EDITIONS}, then checksum\n"
        "it via src.provenance.fetch_to_raw's sidecar convention. See the docstring.\n"
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
