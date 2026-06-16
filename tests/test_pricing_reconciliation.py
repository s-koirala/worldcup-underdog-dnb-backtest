"""Reconciliation gate: the synthetic-DNB identity matches the assembled panel.

This test belongs to the SELECTION + SETTLEMENT slice (it pins the load-bearing guarantee
those modules depend on): ``src.pricing.synthetic_dnb`` MUST equal
``src.ingest.attach_reference_price``'s ``o_dnb_underdog`` BIT-FOR-BIT on the same inputs,
so the assembled ``data/processed/matches.parquet`` is unchanged when selection/settlement
consume the identity. (The de-vig layer in ``src/pricing.py`` is owned + tested by the
pricing slice; this file asserts ONLY the assemble-identity reconciliation.)
"""

from __future__ import annotations

import numpy as np
from src import ingest, pricing, run

FIXTURE = run.PROJECT_ROOT / "tests" / "fixtures" / "mini_league.csv"


def _ingest_fixture_panel(tmp_path):
    """Run the real ingest refC/underdog/o_dnb derivation on the committed fixture."""
    raw = tmp_path / "2223_E0.csv"
    ingest.write_with_sha256(raw, FIXTURE.read_bytes())
    cfg = run.load_config(run.PROJECT_ROOT / "config" / "baseline.yaml")["ingest"]
    ah = cfg["quoted_ah_pinnacle_close"]
    vf = ingest.validate_file(
        raw, season=2223, division="E0", ah_home=ah["home"], ah_away=ah["away"], ah_line=ah["line"]
    )
    vf = ingest.attach_reference_price(
        vf,
        cutover_season=cfg["reference_cutover_season"],
        reference_columns=cfg["reference_columns"],
        ah_home=ah["home"],
        ah_away=ah["away"],
        ah_line=ah["line"],
    )
    return vf.df


def test_synthetic_dnb_worked_example_3_25():
    """CALC §8.1: H=1.80, D=3.60, A=4.50 (away underdog) -> o_DNB = 3.250."""
    assert abs(pricing.synthetic_dnb(4.50, 3.60) - 3.250) < 1e-12


def test_synthetic_dnb_matches_ingest_o_dnb_underdog_bitwise(tmp_path):
    """RECONCILIATION GATE: pricing.synthetic_dnb == ingest o_dnb_underdog bit-for-bit.

    The underdog price is chosen with the SAME tie-break as ingest (refC_A >= refC_H ->
    away), so feeding pricing.synthetic_dnb the underdog price reproduces the stored
    column exactly -- guaranteeing matches.parquet content is unchanged.
    """
    df = _ingest_fixture_panel(tmp_path)
    h = df["refC_H"].to_numpy(dtype="float64")
    a = df["refC_A"].to_numpy(dtype="float64")
    d = df["refC_D"].to_numpy(dtype="float64")
    under_price = np.where(a >= h, a, h)  # same selection as src.ingest
    recomputed = pricing.synthetic_dnb(under_price, d)
    stored = df["o_dnb_underdog"].to_numpy(dtype="float64")
    assert np.array_equal(recomputed, stored, equal_nan=True)  # exact, not just isclose


def test_synthetic_dnb_nan_on_bad_draw_price():
    """Non-positive / NaN draw price -> NaN (no fabricated price; matches ingest guard)."""
    assert np.isnan(pricing.synthetic_dnb(4.50, 0.0))
    assert np.isnan(pricing.synthetic_dnb(4.50, np.nan))
