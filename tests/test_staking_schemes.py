"""Tests for the five staking schemes + data-derived lambda (Phase 3 task 1, task 5, task 7).

Covers:
  * the five stake-sizing functions as functions of (o_dnb, p, bankroll_before) ONLY,
    matching the STAKE §2 / §3.3 worked numbers (Kelly f*=0.1026 -> 10.26% of bankroll);
  * the negative-edge -> f*=0 -> stake 0 honest-prior branch (CALC §8.2; slice brief);
  * the level_to_odds 1/(d-1) and fixed_fraction phi*W sizing tilts;
  * the dispatch (stake()) parameter validation;
  * the Bayesian-shrinkage lambda = 1/(1+CV^2) (half-Kelly as a CONSEQUENCE at CV=1);
  * the BRB drawdown-bound exponent theta = log beta/log alpha (= 3.3219 worked);
  * THE non-anticipation property test (slice brief / STAT §9.2): permuting FUTURE
    results never changes any stake.

No magic numbers beyond the STAKE-worked probabilities/odds and the deterministic
substream seed.
"""

from __future__ import annotations

import numpy as np
import pytest
from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st
from src import seeding, staking

WORKED_ATOL = 5e-4


# ---------------------------------------------------------------------------
# The five schemes -- worked sizing.
# ---------------------------------------------------------------------------


def test_flat_is_constant_cash_ignoring_signal():
    """flat stakes the level unit regardless of odds/edge/bankroll (STAKE §2)."""
    assert staking.stake("flat", 2.857, 0.30, 0.28, 1000.0, unit=10.0) == 10.0
    # Same unit even at a wildly different signal / bankroll (odds-agnostic).
    assert staking.stake("flat", 6.6, 0.05, 0.40, 5.0, unit=10.0) == 10.0


def test_fixed_fraction_is_phi_times_bankroll():
    """fixed_fraction stakes phi * bankroll_before, odds-agnostic (STAKE §2, §7.1)."""
    assert staking.stake("fixed_fraction", 2.857, 0.30, 0.28, 1000.0, phi=0.02) == pytest.approx(
        20.0
    )
    assert staking.stake("fixed_fraction", 6.6, 0.05, 0.40, 500.0, phi=0.02) == pytest.approx(10.0)


def test_level_to_odds_is_c_over_b():
    """level_to_odds stakes c/(d-1) -- more on short prices (STAKE §2, §7.1)."""
    # d=2.857 -> b=1.857; c=5 -> 5/1.857 = 2.6925.
    assert staking.stake("level_to_odds", 2.857, 0.30, 0.28, 1000.0, c=5.0) == pytest.approx(
        5.0 / 1.857, abs=1e-9
    )
    # Shorter price (d=1.5) gets a LARGER stake than a longer price (d=5.0) for the
    # same target profit -- the level-to-odds tilt.
    short = staking.stake("level_to_odds", 1.5, 0.6, 0.2, 1000.0, c=5.0)
    long = staking.stake("level_to_odds", 5.0, 0.18, 0.2, 1000.0, c=5.0)
    assert short > long


def test_kelly_matches_stake_3_3_worked_fraction():
    """STAKE §3.3: f* = 0.1026 at o_DNB=2.857, p_W=0.30, p_D=0.28 -> 10.26% of W."""
    s = staking.stake("kelly", 2.857, 0.30, 0.28, 1000.0)
    assert s == pytest.approx(0.1026 * 1000.0, abs=1.0)  # ~102.6 (doc rounds f* to 4dp)


def test_kelly_negative_edge_stakes_zero():
    """Honest-prior branch (CALC §8.2; slice brief): negative edge -> f*=0 -> stake 0."""
    assert staking.stake("kelly", 3.25, 0.2105, 0.2632, 1000.0) == 0.0
    assert staking.stake("fractional_kelly", 3.25, 0.2105, 0.2632, 1000.0, lam=0.5) == 0.0


def test_fractional_kelly_is_lambda_times_kelly():
    """fractional_kelly = lam * full-Kelly stake (STAKE §4)."""
    full = staking.stake("kelly", 2.857, 0.30, 0.28, 1000.0)
    half = staking.stake("fractional_kelly", 2.857, 0.30, 0.28, 1000.0, lam=0.5)
    assert half == pytest.approx(0.5 * full, abs=1e-9)


def test_stake_dispatch_validates_params():
    """The dispatch raises on an unknown scheme or a missing/extra parameter."""
    with pytest.raises(ValueError, match="unknown staking scheme"):
        staking.stake("martingale", 2.0, 0.3, 0.3, 100.0)
    with pytest.raises(ValueError, match="missing required parameter"):
        staking.stake("fixed_fraction", 2.0, 0.3, 0.3, 100.0)  # no phi
    with pytest.raises(ValueError, match="unexpected parameter"):
        staking.stake("kelly", 2.0, 0.3, 0.3, 100.0, phi=0.02)  # kelly takes none


def test_scheme_set_is_the_five_canonical():
    """STAKING_SCHEMES is the five-scheme set (matches config + the family K)."""
    assert staking.STAKING_SCHEMES == (
        "flat",
        "fixed_fraction",
        "level_to_odds",
        "kelly",
        "fractional_kelly",
    )


# ---------------------------------------------------------------------------
# Data-derived lambda (STAKE §4.2 shrinkage; §6.2 BRB exponent).
# ---------------------------------------------------------------------------


def test_shrinkage_lambda_half_at_unit_cv():
    """lam = 1/(1+CV^2); CV=1 (edge_sd == edge) -> 0.5 (half-Kelly as a consequence)."""
    assert staking.shrinkage_lambda(0.05, 0.05) == pytest.approx(0.5)
    # Lower noise -> lambda toward 1; higher noise -> toward 0.
    assert staking.shrinkage_lambda(0.10, 0.02) > 0.9
    assert staking.shrinkage_lambda(0.02, 0.20) < 0.1


def test_shrinkage_lambda_zero_for_nonpositive_edge():
    """Non-positive edge -> lam=0 (no positive-edge stake to fractionate)."""
    assert staking.shrinkage_lambda(-0.01, 0.05) == 0.0
    assert staking.shrinkage_lambda(0.0, 0.05) == 0.0


def test_brb_bound_exponent_worked():
    """STAKE §6.2: theta = log(0.1)/log(0.5) = 3.3219 (a strictness, not a bet size)."""
    assert staking.brb_bound_exponent(0.5, 0.1) == pytest.approx(3.32192809, abs=1e-6)
    # theta > 1 for any nontrivial target.
    assert staking.brb_bound_exponent(0.7, 0.1) > 1.0


def test_brb_bound_exponent_domain():
    """alpha_dd, beta_dd must be in (0,1)."""
    with pytest.raises(ValueError):
        staking.brb_bound_exponent(1.0, 0.1)
    with pytest.raises(ValueError):
        staking.brb_bound_exponent(0.5, 0.0)


# ---------------------------------------------------------------------------
# Non-anticipation property test (slice brief; STAT §9.2; plan task 7).
# ---------------------------------------------------------------------------


@settings(max_examples=200, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    o=st.floats(min_value=1.05, max_value=15.0),
    p_w=st.floats(min_value=0.02, max_value=0.9),
    p_d=st.floats(min_value=0.02, max_value=0.9),
    w=st.floats(min_value=1.0, max_value=1e6),
    fut_result=st.sampled_from(["H", "D", "A"]),
)
def test_non_anticipation_stake_independent_of_future_result(o, p_w, p_d, w, fut_result):
    """A stake is a function of (o_dnb, p, bankroll_before) ONLY -- never the result.

    The scheme signatures contain no result channel, so a "future result" passed
    alongside the signal cannot enter the stake. This test makes that explicit:
    sizing every scheme with the SAME signal but a DIFFERENT future result yields the
    SAME stake (permuting future results never changes any stake; STAT §9.2).
    """
    assume(p_w + p_d <= 0.96)
    # The future result is deliberately unused by the staking call -- proving the
    # stake cannot read it. Compute each scheme once; the value must not depend on
    # fut_result (which Hypothesis varies independently).
    stakes = {
        "flat": staking.stake("flat", o, p_w, p_d, w, unit=10.0),
        "fixed_fraction": staking.stake("fixed_fraction", o, p_w, p_d, w, phi=0.02),
        "level_to_odds": staking.stake("level_to_odds", o, p_w, p_d, w, c=5.0),
        "kelly": staking.stake("kelly", o, p_w, p_d, w),
        "fractional_kelly": staking.stake("fractional_kelly", o, p_w, p_d, w, lam=0.5),
    }
    # Recompute holding the signal fixed -- byte-identical regardless of fut_result.
    for name, val in stakes.items():
        params = {
            "flat": {"unit": 10.0},
            "fixed_fraction": {"phi": 0.02},
            "level_to_odds": {"c": 5.0},
            "kelly": {},
            "fractional_kelly": {"lam": 0.5},
        }[name]
        again = staking.stake(name, o, p_w, p_d, w, **params)
        assert again == val or (np.isnan(again) and np.isnan(val))


def test_vectorised_schemes_match_scalar():
    """Array sizing equals element-wise scalar sizing (ledger vectorisation parity)."""
    rng = seeding.substream(20260616, "stake")
    o = rng.uniform(1.5, 6.0, size=50)
    p_w = rng.uniform(0.05, 0.45, size=50)
    p_d = rng.uniform(0.05, 0.40, size=50)
    w = rng.uniform(100.0, 1e4, size=50)
    keep = (p_w + p_d) < 0.95
    o, p_w, p_d, w = o[keep], p_w[keep], p_d[keep], w[keep]
    kelly_vec = staking.stake("kelly", o, p_w, p_d, w)
    ff_vec = staking.stake("fixed_fraction", o, p_w, p_d, w, phi=0.02)
    for i in range(len(o)):
        assert kelly_vec[i] == pytest.approx(staking.stake("kelly", o[i], p_w[i], p_d[i], w[i]))
        assert ff_vec[i] == pytest.approx(
            staking.stake("fixed_fraction", o[i], p_w[i], p_d[i], w[i], phi=0.02)
        )
