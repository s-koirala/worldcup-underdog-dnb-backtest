"""Tests for the growth-drawdown frontier engine (Phase 3 task 6; STAKE §7.3).

Covers:
  * tracing a per-scheme frontier (fixed-fraction sweep) and the efficient (upper-left)
    envelope being a non-dominated subset;
  * the all-negative-edge honest-prior verdict: lambda*=0 dominates, the Kelly-family
    frontier is the cash point only, and the counterfactual required-if-edge-real
    feasibility statement is attached (the bankroll/lambda that WOULD be required were the
    edge real -- a power statement, not a profit claim);
  * the required-if-edge-real inversion: a hypothetical positive edge inverts to an
    implied f* > 0 and a drawdown-constrained lambda in (0, 1].
"""

from __future__ import annotations

import numpy as np
import pytest
from src import frontier, ruin, seeding


def _toy_matchdays(profit_values, n_per_day=5, o=2.857, pw=0.42, pd_=0.20):
    r = np.array(profit_values * n_per_day, dtype=float)
    key = np.repeat(np.arange(len(profit_values)), n_per_day)
    n = r.size
    return ruin.group_by_matchday(
        r, key, o_dnb=np.full(n, o), p_win=np.full(n, pw), p_draw=np.full(n, pd_)
    )


def test_efficient_envelope_is_non_dominated():
    """The efficient envelope keeps only points no other point dominates (max growth/DD)."""
    md = _toy_matchdays([-1.0, 1.857, -1.0, 0.0, 1.857, -1.0])
    sf = frontier.trace_scheme_frontier(
        md,
        scheme="fixed_fraction",
        param_grid=[0.01, 0.05, 0.1],
        rho=0.5,
        rng=seeding.substream(20260616, "ruin-mc"),
        n_paths=400,
    )
    assert len(sf.points) == 3
    # The efficient set is a subset of the traced points, sorted by drawdown budget.
    eff_dd = [p.drawdown_budget for p in sf.efficient_points]
    assert eff_dd == sorted(eff_dd)
    assert len(sf.efficient_points) <= len(sf.points)
    # No efficient point is strictly dominated by another point.
    for p in sf.efficient_points:
        for q in sf.points:
            dominated = (
                q.expected_log_growth > p.expected_log_growth
                and q.drawdown_budget <= p.drawdown_budget
            )
            assert not dominated


def test_lambda_star_zero_dominates_on_negative_edge_book():
    """All-negative-edge: lambda*=0 dominates; the counterfactual feasibility is attached."""
    # A book with no positive-edge bet (push-Kelly f*=0 everywhere).
    md = _toy_matchdays([1.0, 0.0, -1.0], o=1.8, pw=0.30, pd_=0.28)
    report = frontier.build_frontier_report(
        md,
        rho=0.5,
        rng=seeding.substream(20260616, "ruin-mc"),
        phi_grid=[0.01, 0.05],
        lambda_grid=[0.25, 0.5, 1.0],
        alpha_dd_grid=(0.5, 0.6, 0.7, 0.8),
        beta_dd_grid=(0.05, 0.10, 0.20),
        operating_alpha_dd=0.5,
        operating_beta_dd=0.10,
        n_positive_edge_bets=0,
        n_paths=400,
        hypothetical_edge=0.0093,  # RBF 2024 reverse-FLB gradient (EDGE §3.2)
        o_dnb_ref=2.857,
        p_draw_ref=0.28,
    )
    assert report.lambda_star_zero_dominates
    # The Kelly-family frontier collapses to the cash point (no positive-growth lambda).
    assert report.scheme_frontiers["kelly"].all_below_zero_growth
    # The counterfactual is attached: what WOULD be required were the edge real.
    assert report.required_if_edge_real is not None
    req = report.required_if_edge_real
    assert req.implied_full_kelly_f > 0.0  # a real edge WOULD imply a positive Kelly bet
    assert 0.0 < req.rck_lambda <= 1.0
    assert req.deployed_fraction == pytest.approx(req.rck_lambda * req.implied_full_kelly_f)


def test_required_if_edge_real_inverts_edge_to_positive_kelly():
    """A hypothetical positive edge inverts to an implied win prob and a positive f*."""
    b = 1.857
    stream = np.concatenate([np.full(420, b), np.zeros(200), np.full(380, -1.0)])
    req = frontier.required_lambda_if_edge_real(
        hypothetical_edge=0.05,
        o_dnb_ref=2.857,
        p_draw_ref=0.28,
        profit_multiples_if_edge=stream,
        operating_alpha_dd=0.5,
        operating_beta_dd=0.10,
    )
    assert req.implied_full_kelly_f > 0.0
    assert 0.0 < req.rck_lambda <= 1.0
    assert req.hypothetical_edge == 0.05


def test_frontier_report_carries_full_rck_grid():
    """The frontier report carries the full methodology.md §1.2 RCK grid (12 cells)."""
    md = _toy_matchdays([1.0, 0.0, -1.0], o=1.8, pw=0.30, pd_=0.28)
    report = frontier.build_frontier_report(
        md,
        rho=0.5,
        rng=seeding.substream(20260616, "ruin-mc"),
        phi_grid=[0.05],
        lambda_grid=[0.5],
        alpha_dd_grid=(0.5, 0.6, 0.7, 0.8),
        beta_dd_grid=(0.05, 0.10, 0.20),
        operating_alpha_dd=0.5,
        operating_beta_dd=0.10,
        n_positive_edge_bets=0,
        n_paths=200,
    )
    assert len(report.rck_grid) == 12
    # All FIVE staking schemes render on the frontier (plan acceptance line 318): the
    # additive flat / level_to_odds curves alongside the multiplicative trio.
    assert {
        "flat",
        "fixed_fraction",
        "level_to_odds",
        "kelly",
        "fractional_kelly",
    } == set(report.scheme_frontiers)


def test_trace_additive_scheme_frontiers_render():
    """The additive cash schemes (flat / level_to_odds) trace a frontier curve (STAKE §7.3)."""
    md = _toy_matchdays([-1.0, 1.857, -1.0, 0.0, 1.857, -1.0])
    for scheme in ("flat", "level_to_odds"):
        sf = frontier.trace_scheme_frontier(
            md,
            scheme=scheme,
            param_grid=[0.01, 0.05, 0.1],
            rho=0.5,
            rng=seeding.substream(20260616, "ruin-mc"),
            n_paths=400,
        )
        assert sf.scheme == scheme
        assert len(sf.points) == 3
        # The cash schemes record their own free parameter on each point.
        assert {p.param_name for p in sf.points} == {"unit" if scheme == "flat" else "c"}
        # The efficient envelope is a non-dominated, drawdown-sorted subset.
        eff_dd = [p.drawdown_budget for p in sf.efficient_points]
        assert eff_dd == sorted(eff_dd)


def test_build_frontier_report_renders_all_five_schemes_plus_rck():
    """Plan acceptance line 318: F-07/T-04/T-05 render for all five schemes + RCK."""
    md = _toy_matchdays([-1.0, 1.857, -1.0, 0.0, 1.857, -1.0], o=2.857, pw=0.42, pd_=0.20)
    report = frontier.build_frontier_report(
        md,
        rho=0.5,
        rng=seeding.substream(20260616, "ruin-mc"),
        phi_grid=[0.01, 0.05],
        lambda_grid=[0.5, 1.0],
        unit_grid=[0.01, 0.05],
        c_grid=[0.01, 0.05],
        alpha_dd_grid=(0.5, 0.6, 0.7, 0.8),
        beta_dd_grid=(0.05, 0.10, 0.20),
        operating_alpha_dd=0.5,
        operating_beta_dd=0.10,
        n_positive_edge_bets=10,
        n_paths=300,
    )
    assert set(report.scheme_frontiers) == {
        "flat",
        "fixed_fraction",
        "level_to_odds",
        "kelly",
        "fractional_kelly",
    }
    assert len(report.rck_grid) == 12  # the RCK lambda(alpha_dd, beta_dd) grid (T-06)
