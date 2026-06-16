"""Tests for the wired `--stage stake` entrypoint (Phase 3 task 9; slice brief).

Confirms:
  * run_stake_stage runs the staking/ledger pass over the league panel, emits a
    schema-valid per-stage ReproLog, and the ledger conserves;
  * the ReproLog records the root seed and pins the canonical-panel + data-quality
    (open->close slippage basis) checksums;
  * the honest-prior verdict surfaces (full Kelly stakes 0 everywhere -> do not bet);
  * `--dry-run --stage stake` resolves the `stake` sub-stream and emits a ReproLog
    without running compute (the Phase-0 acceptance mirror).

The compute test writes to an isolated tmp logs dir and is skipped when the canonical
panel is not materialised.
"""

from __future__ import annotations

import json

import pytest
from src import ledger, reprolog, run

CONFIG = run.PROJECT_ROOT / "config" / "baseline.yaml"


def test_stake_is_a_phase_stage():
    """`stake` is selectable as a --stage value (the wired entrypoint)."""
    assert "stake" in run.PHASE_STAGES


def test_dry_run_stake_emits_schema_valid_reprolog(tmp_path):
    """--dry-run --stage stake resolves the `stake` sub-stream + emits a valid ReproLog."""
    out = run.dry_run(CONFIG, "stake", run_id="dryrun-stake-1", logs_dir=tmp_path)
    record = json.loads(out.read_text(encoding="utf-8"))
    reprolog.validate_record(record)
    assert record["rng_seed"] == 20260616


def test_run_stake_stage_over_league_panel(tmp_path):
    """The real staking/ledger pass runs, conserves, and emits a valid ReproLog."""
    matches = run.PROJECT_ROOT / "data" / "processed" / "matches.parquet"
    if not matches.exists():
        pytest.skip("canonical matches.parquet not materialised")
    out, facts = run.run_stake_stage(CONFIG, run_id="test-stake-1", logs_dir=tmp_path)

    record = json.loads(out.read_text(encoding="utf-8"))
    reprolog.validate_record(record)
    assert record["rng_seed"] == 20260616
    # The canonical panel content + the open->close calibration report are pinned.
    assert "matches.parquet" in record["dataset_checksums"]

    s = facts.summary
    # Honest prior: full Kelly stakes 0 on every league bet (no positive-EV cell).
    assert s["scheme"] == "kelly"
    assert s["n_bets"] > 1000  # the estimation universe is at the 10^3-10^4 scale
    assert s["n_staked"] == 0  # do not bet (slice brief; STAKE §7.3)
    assert s["conservation_ok"] is True
    # The slippage was DATA-calibrated from the open->close distribution.
    assert facts.slippage.value > 0.0
    assert facts.slippage.n_observable > 0
    # Commission is within the DATA §2.3 [2%,5%] band.
    assert 0.02 <= facts.commission_rate <= 0.05

    # --- Phase 3 tasks 4-6: the risk engines ran and the honest-prior verdict surfaced.
    rk = facts.risk
    assert rk["n_positive_edge_bets"] == 0  # all-negative-edge prior dominates
    assert rk["lambda_star_zero_dominates"] is True  # lambda*=0 (do not bet) verdict
    # B is DERIVED from the precision target (SE<=eps/10 => B>=100(1-eps)/eps) and clears it.
    assert rk["ruin_b"] >= rk["ruin_b_precision_floor"]
    assert rk["ruin_b_precision_floor"] == 1900  # STAKE §6.3 worked value at eps=0.05
    # The frontier DATA artifact was written (F-07/F-08/F-09/T-04/T-05/T-06 source).
    import json as _json

    payload = _json.loads(facts.risk_path.read_text(encoding="utf-8"))
    assert payload["lambda_star_zero_dominates"] is True
    # The Kelly-family frontier collapses to the cash point (no positive-growth lambda).
    assert payload["scheme_frontiers"]["kelly"]["all_below_zero_growth"] is True
    # All FIVE staking schemes render on the frontier (plan acceptance line 318):
    # flat / fixed_fraction / level_to_odds / kelly / fractional_kelly.
    assert set(payload["scheme_frontiers"]) == {
        "flat",
        "fixed_fraction",
        "level_to_odds",
        "kelly",
        "fractional_kelly",
    }
    # The ruin floor rho is swept over the WHOLE declared grid (methodology.md §1.1-§1.2:
    # "Two values are reported, not one"); both rho=0.0 (benchmark) and rho=0.5
    # (behavioural stop-out) are emitted per scheme.
    rhos = {round(float(e["rho"]), 6) for e in payload["ruin_by_rho"]}
    assert rhos == {0.0, 0.5}
    for entry in payload["ruin_by_rho"]:
        assert set(entry["scheme_frontiers"]) == {
            "flat",
            "fixed_fraction",
            "level_to_odds",
            "kelly",
            "fractional_kelly",
        }
    # The BRB lambda(alpha_dd, beta_dd) / RCK grid spans methodology.md §1.2 (4x3 cells).
    assert len(payload["brb_rck_grid"]) == 12
    # The counterfactual required-if-edge-real feasibility statement is attached.
    assert "required_if_edge_real" in payload
    assert payload["required_if_edge_real"]["implied_full_kelly_f"] > 0.0
    # The concurrent-independence test ran (gates the renormalised approximation).
    assert "concurrent_independence_test" in payload


def test_run_stake_stage_conservation_helper_agrees(tmp_path):
    """ledger_summary's conservation flag matches an independent check_conservation call."""
    matches = run.PROJECT_ROOT / "data" / "processed" / "matches.parquet"
    if not matches.exists():
        pytest.skip("canonical matches.parquet not materialised")
    _, facts = run.run_stake_stage(CONFIG, run_id="test-stake-2", logs_dir=tmp_path)
    assert ledger.check_conservation(facts.result) is True
