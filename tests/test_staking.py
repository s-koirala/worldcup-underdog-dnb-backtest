"""Unit + property tests for the DNB EV / variance / push-Kelly closed forms.

Phase 2 (plan task 4, task 5 unit tests, task 6 property tests; CALC §5-§7).

Covers, mirroring CALC §5-§7 and the §8 worked numbers exactly:
  * EV ``mu = p_W*(o-1) - p_fav`` against the §8.2 (-5.3%) and §8.4 (+28%) cases;
  * three-point ``Var_DNB = p_W*b^2 + p_fav - mu^2`` against §8.2 / §8.4;
  * the fair-win benchmark ``Var = o - 1`` (CALC §6.2 stated identity);
  * the always-signed fair-price identity ``Var_winbet(fair) - Var_DNB(fair)
    = p_D*p_fav/p_W`` against direct evaluation AND a Monte-Carlo over the simplex
    (resolved CALC Open Question 5), plus the §6.2 regression guard that the
    inequality is NOT general (it fails at mispriced odds);
  * push-Kelly ``f*`` against §8.2 (negative -> clipped to 0, the no-short branch)
    and §8.4 (+0.1577);
  * THE SELF-CHECK the slice brief requires: ``f*`` degenerates to the textbook
    two-outcome Kelly ``(p*o-1)/(o-1)`` as the draw probability d -> 0;
  * synthetic-DNB price feeds EV consistently with the §8.1 worked 3.250 odds;
  * the src.metrics re-export is the same callable as src.staking.

No magic numbers beyond the literature-anchored CALC §8 worked probabilities/odds
(asserted with explicit tolerances) and the RNG seed, which is drawn from the
project's deterministic substream (src.seeding), not hand-set.
"""

from __future__ import annotations

import math

import pytest
from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st
from src import metrics, seeding, staking
from src.pricing import synthetic_dnb

# Tolerance for matching the CALC §8 worked numbers, which the doc rounds to 4 sig
# figs; 5e-4 absolute admits that rounding without being slack.
WORKED_ATOL = 5e-4


# ---------------------------------------------------------------------------
# §5 Expected value -- worked cases.
# ---------------------------------------------------------------------------


def test_ev_matches_calc_8_2_negative_case():
    """CALC §8.2: basic-de-vig probs at synthetic o_DNB=3.250 -> mu = -5.3%."""
    mu = staking.expected_value(p_win=0.2105, p_draw=0.2632, o_dnb=3.250)
    assert mu == pytest.approx(-0.0526, abs=WORKED_ATOL)


def test_ev_matches_calc_8_4_positive_case():
    """CALC §8.4: p_W=0.30, p_D=0.26 at o_DNB=3.40 -> mu = +0.280."""
    mu = staking.expected_value(p_win=0.30, p_draw=0.26, o_dnb=3.40)
    assert mu == pytest.approx(0.280, abs=WORKED_ATOL)


def test_ev_two_equivalent_forms_agree():
    """mu = p_W*(o-1) - p_fav must equal p_W*o - (1 - p_D) (CALC §5)."""
    p_w, p_d, o = 0.31, 0.24, 2.95
    p_fav = 1.0 - p_w - p_d
    form_a = p_w * (o - 1.0) - p_fav
    form_b = p_w * o - (1.0 - p_d)
    mu = staking.expected_value(p_win=p_w, p_draw=p_d, o_dnb=o)
    assert mu == pytest.approx(form_a)
    assert mu == pytest.approx(form_b)


def test_ev_zero_at_fair_dnb_price():
    """At the fair DNB price o = (1-p_D)/p_W the EV is exactly 0 (CALC §5)."""
    p_w, p_d = 0.28, 0.27
    o_fair = staking.fair_dnb_odds(p_win=p_w, p_draw=p_d)
    assert staking.expected_value(p_win=p_w, p_draw=p_d, o_dnb=o_fair) == pytest.approx(
        0.0, abs=1e-12
    )


# ---------------------------------------------------------------------------
# §6 Variance -- worked cases, benchmark, fair-price identity.
# ---------------------------------------------------------------------------


def test_variance_matches_calc_8_2():
    """CALC §8.2: Var_DNB = 0.2105*2.25^2 + 0.5263 - mu^2 = 1.589."""
    var = staking.per_bet_variance(p_win=0.2105, p_draw=0.2632, o_dnb=3.250)
    assert var == pytest.approx(1.589, abs=WORKED_ATOL)


def test_variance_matches_calc_8_4():
    """CALC §8.4: Var_DNB = 0.30*2.40^2 + 0.44 - 0.28^2 = 2.090."""
    var = staking.per_bet_variance(p_win=0.30, p_draw=0.26, o_dnb=3.40)
    assert var == pytest.approx(2.090, abs=WORKED_ATOL)


def test_fair_win_bet_variance_identity():
    """The benchmark Var_winbet(fair) = o - 1 (CALC §6.2 stated identity)."""
    for o in (1.45, 2.0, 3.25, 6.6):
        assert staking.fair_win_bet_variance(o) == pytest.approx(o - 1.0)


def test_fair_price_variance_reduction_identity_direct():
    """Var_winbet(fair) - Var_DNB(fair) = p_D*p_fav/p_W, evaluated at the fair price.

    Computes both sides independently: the LHS from fair_win_bet_variance and
    per_bet_variance at o = fair DNB odds; the RHS from the closed-form helper.
    They must agree to machine precision (CALC §6.2, resolved Open Question 5).
    """
    p_w, p_d = 0.2105, 0.2632
    p_fav = 1.0 - p_w - p_d
    o_fair = staking.fair_dnb_odds(p_win=p_w, p_draw=p_d)
    lhs = staking.fair_win_bet_variance(o_fair) - staking.per_bet_variance(
        p_win=p_w, p_draw=p_d, o_dnb=o_fair
    )
    rhs = staking.fair_price_variance_reduction(p_win=p_w, p_draw=p_d)
    assert lhs == pytest.approx(rhs, abs=1e-12)
    assert rhs == pytest.approx(p_d * p_fav / p_w, abs=1e-12)
    assert rhs >= 0.0  # non-negative for any valid simplex point with p_W > 0


@settings(max_examples=400, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    p_w=st.floats(min_value=0.02, max_value=0.96),
    p_d=st.floats(min_value=0.02, max_value=0.96),
)
def test_fair_price_variance_reduction_monte_carlo(p_w, p_d):
    """The fair-price identity holds over the simplex (CALC §6.2 500k-draw MC analogue).

    Property form of the resolved Open Question 5 simulation: at the FAIR price the
    win-bet-minus-DNB variance gap equals p_D*p_fav/p_W with zero sign violations.
    """
    assume(p_w + p_d < 0.99)  # leave p_fav > 0.01 (strictly interior simplex)
    o_fair = staking.fair_dnb_odds(p_win=p_w, p_draw=p_d)
    lhs = staking.fair_win_bet_variance(o_fair) - staking.per_bet_variance(
        p_win=p_w, p_draw=p_d, o_dnb=o_fair
    )
    rhs = staking.fair_price_variance_reduction(p_win=p_w, p_draw=p_d)
    assert lhs == pytest.approx(rhs, abs=1e-9)
    assert lhs >= -1e-9  # non-negative (no sign violation at the fair price)


def test_variance_reduction_is_not_general_at_mispriced_odds():
    """Regression guard (CALC §6.2): Var_DNB can EXCEED o-1 at mispriced odds.

    The §6.2 counterexample p_W=0.70, p_D=0.22 at o_DNB=6.60 gives Var_DNB=7.29 >
    o-1=5.60, proving the fair-price identity is NOT a general bound. The variance
    closed form must reproduce that inequality.
    """
    var = staking.per_bet_variance(p_win=0.70, p_draw=0.22, o_dnb=6.60)
    assert var == pytest.approx(7.29, abs=1e-2)
    assert var > 6.60 - 1.0  # the inequality reverses -- fair-price-only statement


# ---------------------------------------------------------------------------
# §7 Push-Kelly -- worked cases, no-short branch, d->0 degeneration self-check.
# ---------------------------------------------------------------------------


def test_kelly_matches_calc_8_4_positive():
    """CALC §8.4: f* = (0.30*2.40 - 0.44)/(2.40*(0.30+0.44)) = 0.1577."""
    f = staking.push_kelly_fraction(p_win=0.30, p_draw=0.26, o_dnb=3.40)
    assert f == pytest.approx(0.1577, abs=WORKED_ATOL)


def test_kelly_negative_edge_clipped_to_zero_calc_8_2():
    """CALC §8.2: f* = -0.0317 < 0 -> clipped to 0 (no short side in DNB)."""
    f = staking.push_kelly_fraction(p_win=0.2105, p_draw=0.2632, o_dnb=3.250)
    assert f == 0.0
    # The un-clipped FOC root is the negative value the doc reports.
    raw = staking.push_kelly_fraction(p_win=0.2105, p_draw=0.2632, o_dnb=3.250, clip_negative=False)
    assert raw == pytest.approx(-0.0317, abs=WORKED_ATOL)


def test_kelly_positive_iff_positive_ev():
    """Kelly turns positive exactly at the §5 positive-EV boundary p_W*o = 1-p_D."""
    p_w, p_d = 0.30, 0.26
    o_boundary = (1.0 - p_d) / p_w  # the fair price; EV = 0 here
    assert staking.expected_value(p_win=p_w, p_draw=p_d, o_dnb=o_boundary) == pytest.approx(
        0.0, abs=1e-12
    )
    raw_at_boundary = staking.push_kelly_fraction(
        p_win=p_w, p_draw=p_d, o_dnb=o_boundary, clip_negative=False
    )
    assert raw_at_boundary == pytest.approx(0.0, abs=1e-12)
    # Just above the fair price -> positive edge -> positive (un-clipped) stake.
    assert (
        staking.push_kelly_fraction(
            p_win=p_w, p_draw=p_d, o_dnb=o_boundary + 0.1, clip_negative=False
        )
        > 0.0
    )


def test_kelly_unrenormalised_form_agrees():
    """f* via no-push-renormalised probs == the raw CALC §7.1 form (1/(1-p_D) cancels)."""
    p_w, p_d, o = 0.33, 0.25, 3.10
    p_fav = 1.0 - p_w - p_d
    b = o - 1.0
    direct = (p_w * b - p_fav) / (b * (p_w + p_fav))  # CALC §7.1 un-renormalised
    f = staking.push_kelly_fraction(p_win=p_w, p_draw=p_d, o_dnb=o, clip_negative=False)
    assert f == pytest.approx(direct, abs=1e-12)


@pytest.mark.parametrize("d", [1e-2, 1e-4, 1e-6, 1e-9])
def test_kelly_degenerates_to_two_outcome_as_draw_to_zero(d):
    """SELF-CHECK (slice brief): f* -> textbook two-outcome Kelly as draw prob d -> 0.

    Hold the conditional no-draw win view fixed by parameterising p_W = q_W*(1-d)
    so that as d -> 0 the underdog win prob -> q_W and the favourite mass -> 1-q_W,
    i.e. the bet collapses to a pure two-outcome win bet at o. The push-Kelly f*
    (un-clipped) must converge to (q_W*o - 1)/(o - 1) = edge/odds.
    """
    q_w, o = 0.45, 2.60  # conditional win prob and DNB odds (positive-edge: 0.45*2.6>1)
    p_w = q_w * (1.0 - d)  # underdog-win prob with a vanishing push mass d
    f_push = staking.push_kelly_fraction(p_win=p_w, p_draw=d, o_dnb=o, clip_negative=False)
    f_two = staking.two_outcome_kelly(p_win=q_w, o=o)
    # The gap must shrink with d (linear convergence): tolerance scales with d.
    assert f_push == pytest.approx(f_two, abs=max(1e-12, 5.0 * d))


def test_kelly_exact_two_outcome_at_zero_draw():
    """At d == 0 exactly, push-Kelly equals the two-outcome closed form (no push)."""
    p_w, o = 0.45, 2.60
    f_push = staking.push_kelly_fraction(p_win=p_w, p_draw=0.0, o_dnb=o, clip_negative=False)
    f_two = staking.two_outcome_kelly(p_win=p_w, o=o)
    assert f_push == pytest.approx(f_two, abs=1e-12)
    assert f_two == pytest.approx((p_w * o - 1.0) / (o - 1.0), abs=1e-12)


# ---------------------------------------------------------------------------
# Synthetic-DNB price -> EV consistency, and the metrics re-export.
# ---------------------------------------------------------------------------


def test_synthetic_dnb_price_feeds_ev_consistently():
    """CALC §8.1/§8.2: synthetic o_DNB = A*(D-1)/D = 4.50*2.60/3.60 = 3.250 feeds EV."""
    o = synthetic_dnb(4.50, 3.60)
    assert o == pytest.approx(3.250, abs=1e-9)
    mu = staking.expected_value(p_win=0.2105, p_draw=0.2632, o_dnb=o)
    assert mu == pytest.approx(-0.0526, abs=WORKED_ATOL)


def test_metrics_reexports_are_same_callables():
    """src.metrics exposes the staking EV/variance helpers (single-sourced)."""
    assert metrics.expected_value is staking.expected_value
    assert metrics.per_bet_variance is staking.per_bet_variance
    assert metrics.fair_win_bet_variance is staking.fair_win_bet_variance
    assert metrics.fair_price_variance_reduction is staking.fair_price_variance_reduction
    assert metrics.fair_dnb_odds is staking.fair_dnb_odds


# ---------------------------------------------------------------------------
# Vectorisation parity (scalar path == array path).
# ---------------------------------------------------------------------------


def test_vectorised_matches_scalar():
    """Array inputs give the same values as element-wise scalar calls (CALC §5-§7)."""
    rng = seeding.substream(20260616, "price")
    p_w = rng.uniform(0.05, 0.45, size=64)
    p_d = rng.uniform(0.05, 0.40, size=64)
    o = rng.uniform(1.5, 6.0, size=64)
    # Keep the simplex valid (p_fav > 0).
    keep = (p_w + p_d) < 0.95
    p_w, p_d, o = p_w[keep], p_d[keep], o[keep]

    mu_vec = staking.expected_value(p_win=p_w, p_draw=p_d, o_dnb=o)
    var_vec = staking.per_bet_variance(p_win=p_w, p_draw=p_d, o_dnb=o)
    f_vec = staking.push_kelly_fraction(p_win=p_w, p_draw=p_d, o_dnb=o)
    for i in range(len(o)):
        assert mu_vec[i] == pytest.approx(
            staking.expected_value(p_win=p_w[i], p_draw=p_d[i], o_dnb=o[i])
        )
        assert var_vec[i] == pytest.approx(
            staking.per_bet_variance(p_win=p_w[i], p_draw=p_d[i], o_dnb=o[i])
        )
        assert f_vec[i] == pytest.approx(
            staking.push_kelly_fraction(p_win=p_w[i], p_draw=p_d[i], o_dnb=o[i])
        )


# ---------------------------------------------------------------------------
# Property tests (Hypothesis; plan task 6).
# ---------------------------------------------------------------------------


@settings(max_examples=400, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    p_w=st.floats(min_value=0.02, max_value=0.95),
    p_d=st.floats(min_value=0.0, max_value=0.95),
    o=st.floats(min_value=1.01, max_value=20.0),
)
def test_property_variance_nonnegative_and_clipped_kelly_in_unit_interval(p_w, p_d, o):
    """Var_DNB >= 0 always; clipped f* in [0, 1) (a valid bankroll fraction)."""
    assume(p_w + p_d <= 0.98)
    var = staking.per_bet_variance(p_win=p_w, p_draw=p_d, o_dnb=o)
    assert var >= -1e-12
    f = staking.push_kelly_fraction(p_win=p_w, p_draw=p_d, o_dnb=o)
    assert 0.0 <= f < 1.0


@settings(max_examples=400, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    p_w=st.floats(min_value=0.02, max_value=0.95),
    p_d=st.floats(min_value=0.0, max_value=0.95),
    o=st.floats(min_value=1.01, max_value=20.0),
)
def test_property_clipped_kelly_positive_iff_positive_ev(p_w, p_d, o):
    """f* > 0 (clipped) iff EV > 0 (CALC §7.1: Kelly positive exactly when EV positive)."""
    assume(p_w + p_d <= 0.98)
    mu = staking.expected_value(p_win=p_w, p_draw=p_d, o_dnb=o)
    f = staking.push_kelly_fraction(p_win=p_w, p_draw=p_d, o_dnb=o)
    if mu > 1e-9:
        assert f > 0.0
    elif mu < -1e-9:
        assert f == 0.0


@settings(max_examples=300, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    p_w=st.floats(min_value=0.05, max_value=0.90),
    o=st.floats(min_value=1.05, max_value=15.0),
    d=st.floats(min_value=1e-9, max_value=1e-3),
)
def test_property_kelly_converges_to_two_outcome(p_w, o, d):
    """As d -> 0 the un-clipped f* approaches the two-outcome Kelly (degeneration)."""
    assume(p_w * (1.0 - d) + d <= 0.999)
    f_push = staking.push_kelly_fraction(
        p_win=p_w * (1.0 - d), p_draw=d, o_dnb=o, clip_negative=False
    )
    f_two = staking.two_outcome_kelly(p_win=p_w, o=o)
    assert math.isclose(f_push, f_two, abs_tol=max(1e-9, 50.0 * d))
