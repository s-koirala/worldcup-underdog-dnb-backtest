"""Tests for the concurrent-matchday vector-Kelly program (Phase 3 task 3, 8; STAKE §5).

Covers:
  * the exact convex program (cvxpy/Clarabel) on a positive-edge slate -- budget binds,
    growth positive, status optimal;
  * the n=2 special case agreeing with the single-bet push-Kelly closed form;
  * the all-negative-edge honest-prior case -> all cash (do not bet), cleanly;
  * the renormalised-and-capped deployable approximation + its growth gap to the exact
    program (>= 0 by optimality), and that the budget cap binds when sum f* > f_max;
  * the concurrent-match independence G-test (task 8): independent slates do not reject,
    a constructed dependent (collusive draw) slate does.
"""

from __future__ import annotations

import numpy as np
import pytest
from src import staking
from src import vector_kelly as vk


def test_two_bet_exact_program_optimal_and_capped():
    """The exact program solves to optimal and caps total stake below the single-bet sum."""
    o = np.array([2.857, 3.0])
    pw = np.array([0.42, 0.40])
    pd_ = np.array([0.20, 0.22])
    res = vk.solve_vector_kelly(o, pw, pd_)
    assert res.solver_status == "optimal"
    # Positive expected log-growth on a genuine positive-edge slate.
    assert res.expected_log_growth > 0.0
    # Budget constraint: bet fractions + cash sum to 1; bets non-negative.
    assert res.f_bets.min() >= -1e-8
    assert abs(res.f_bets.sum() + res.f_cash - 1.0) < 1e-6
    # The joint program caps total matchday stake BELOW the sum of independent single-bet
    # Kelly fractions (STAKE §5.3): the cash residual is strictly positive.
    single = np.atleast_1d(np.asarray(staking.push_kelly_fraction(pw, pd_, o), float))
    assert res.f_bets.sum() <= single.sum() + 1e-6
    assert res.f_cash > 0.0


def test_single_bet_special_case_matches_push_kelly():
    """The n=1 (one bet + cash) program reproduces the single-bet push-Kelly fraction."""
    o = np.array([2.857])
    pw = np.array([0.42])
    pd_ = np.array([0.20])
    res = vk.solve_vector_kelly(o, pw, pd_)
    f_star = float(staking.push_kelly_fraction(pw[0], pd_[0], o[0]))
    # The vector program's single bet fraction equals the closed-form push-Kelly f*.
    assert res.f_bets[0] == pytest.approx(f_star, abs=2e-3)


def test_all_negative_edge_goes_to_cash():
    """All-negative-edge slate -> all weight on cash (do not bet), growth ~ 0 (slice brief)."""
    o = np.array([1.8, 1.9])
    pw = np.array([0.30, 0.28])
    pd_ = np.array([0.28, 0.30])
    res = vk.solve_vector_kelly(o, pw, pd_)
    assert res.f_bets.max() < 1e-4  # no positive-edge bet is taken
    assert res.f_cash == pytest.approx(1.0, abs=1e-3)
    assert res.expected_log_growth == pytest.approx(0.0, abs=1e-6)


def test_growth_gap_nonnegative_and_approx_matches_when_uncapped():
    """The approximation's growth <= the exact optimum (gap >= 0); reports renorm status."""
    # Four strong positive-edge bets so the sum of single-bet f* exceeds the budget 1.0
    # and the approximation's cap BINDS (sum f* ~ 1.07 here).
    o = np.array([2.857, 3.0, 2.5, 2.7])
    pw = np.array([0.42, 0.40, 0.45, 0.43])
    pd_ = np.array([0.20, 0.22, 0.21, 0.20])
    gg = vk.growth_gap(o, pw, pd_, lam=1.0)
    # Exact is log-optimal -> growth_gap >= 0 (up to solver tolerance).
    assert gg.growth_gap >= -1e-6
    single = np.atleast_1d(np.asarray(staking.push_kelly_fraction(pw, pd_, o), float))
    if single.sum() > 1.0:
        # The budget cap (f_max=1) BINDS -> the approximation renormalises down to it.
        assert gg.approx.renormalised
        assert gg.approx.budget_used <= 1.0 + 1e-9
    else:
        # Uncapped: the approximation runs the raw lambda-scaled single-bet fractions.
        assert not gg.approx.renormalised


def test_infeasible_program_raises_rather_than_returning_zeros():
    """A non-converged solve FAILS CLOSED (raises), never a silent all-zero allocation.

    An over-constrained program (a NEGATIVE bet-budget cap ``f_max < 0`` against
    ``f >= 0, 1^T f = 1``) is infeasible, so Clarabel returns status='infeasible' and
    ``f.value`` is None. The sizing engine must RAISE (a degraded solve cannot be
    reported as a legitimate do-not-bet); the pre-fix code returned a fully-formed
    VectorKellyResult with an all-zero f and only the bad status string recorded.
    """
    o = np.array([2.857, 3.0])
    pw = np.array([0.42, 0.40])
    pd_ = np.array([0.20, 0.22])
    with pytest.raises(RuntimeError, match="did not converge"):
        vk.solve_vector_kelly(o, pw, pd_, f_max=-0.5)


def test_payoff_matrix_structure():
    """The payoff matrix encodes win->o, draw->1 (push), loss->0, plus a cash column of 1s."""
    o = np.array([2.5, 3.0])
    payoff = vk.payoff_matrix(o)
    assert payoff.shape == (9, 3)  # 3^2 scenarios, 2 bets + cash
    # The all-win scenario (index 0,0) pays o on both bets + 1 cash.
    scen = vk.enumerate_scenarios(2)
    all_win = np.where((scen[:, 0] == 0) & (scen[:, 1] == 0))[0][0]
    assert np.allclose(payoff[all_win], [2.5, 3.0, 1.0])
    # The cash column is identically 1.
    assert np.allclose(payoff[:, 2], 1.0)


def test_independent_joint_sums_to_one():
    """The independence-default joint pi is a valid probability over all scenarios."""
    pw = np.array([0.42, 0.40])
    pd_ = np.array([0.20, 0.22])
    pi = vk.independent_joint(pw, pd_)
    assert pi.shape == (9,)
    assert pi.sum() == pytest.approx(1.0)
    assert (pi >= 0.0).all()


def test_independence_test_does_not_reject_independent_slates():
    """Independently-generated concurrent outcomes do not reject the independence null."""
    rng = np.random.default_rng(20260616)
    # 400 matchdays, each 3 concurrent bets, outcomes i.i.d. across matches.
    days = [rng.integers(0, 3, size=3) for _ in range(400)]
    res = vk.independence_lr_test(days, alpha=0.05)
    assert res.n_matchdays == 400
    assert not res.reject_independence  # honest independence is not spuriously rejected


def test_independence_test_rejects_collusive_dependence():
    """A constructed dead-rubber/biscotto dependence (paired draws) rejects independence."""
    rng = np.random.default_rng(7)
    days = []
    for _ in range(400):
        # With prob 0.6 BOTH matches draw (collusive 'biscotto' final round); else i.i.d.
        if rng.random() < 0.6:
            days.append(np.array([1, 1]))  # both draw (outcome index 1)
        else:
            days.append(rng.integers(0, 3, size=2))
    res = vk.independence_lr_test(days, alpha=0.05)
    assert res.reject_independence  # the dependence is detected -> run the exact program
    assert res.p_value < 0.05
