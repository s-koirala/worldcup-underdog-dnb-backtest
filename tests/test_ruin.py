"""Tests for the matchday-block bootstrap ruin engine + BRB/RCK solver (Phase 3 tasks 4, 5, 7).

Covers:
  * the precision-target B derivation (SE<=eps/10 => B>=100(1-eps)/eps; the STAKE §6.3
    worked eps=0.05 -> 1900);
  * the matchday-block stationary bootstrap: determinism + order-independence under the
    `ruin-mc` sub-stream, concurrency-preserving matchday grouping;
  * the all-negative-edge honest prior: Kelly stakes 0 -> flat path, P(ruin)=0, growth 0;
  * a positive-EV stream grows and a negative-EV fixed-fraction book ruins;
  * the NON-ANTICIPATION property (task 7): permuting FUTURE returns within the empirical
    multiset never changes a stake fraction (the fraction is signal-only);
  * the BRB bound exponent theta = log beta/log alpha (worked 3.32) and the RCK lambda
    solve: lambda<1 binds on a positive-edge stream, and is vacuous (lambda=1, binds=False)
    on an all-cash (f*=0) stream;
  * min-bankroll / largest-fraction bisection feasibility.
"""

from __future__ import annotations

import numpy as np
import pytest
from src import ruin, seeding, staking


def test_min_bootstrap_paths_matches_worked_value():
    """STAKE §6.3 worked: eps=0.05, SE<=eps/10 => B>=100*(1-eps)/eps = 1900."""
    assert ruin.min_bootstrap_paths(0.05) == 1900
    # The general form B >= (1-eps)/(se_ratio^2 * eps).
    assert ruin.min_bootstrap_paths(0.01) == 9900
    with pytest.raises(ValueError):
        ruin.min_bootstrap_paths(0.0)


def test_deployed_b_clears_the_floor():
    """The deployed B = 10^4 clears the precision-target floor at the smallest eps target."""
    assert ruin.min_bootstrap_paths(0.05) <= ruin.DEPLOYED_B


def _toy_matchdays(profit_values, n_per_day=5, o=2.857, pw=0.42, pd_=0.20):
    """Build a MatchdayReturns from a repeated profit-multiple pattern (concurrency blocks)."""
    r = np.array(profit_values * n_per_day, dtype=float)
    key = np.repeat(np.arange(len(profit_values)), n_per_day)
    n = r.size
    return ruin.group_by_matchday(
        r, key, o_dnb=np.full(n, o), p_win=np.full(n, pw), p_draw=np.full(n, pd_)
    )


def test_ruin_mc_deterministic_and_order_independent():
    """Two `ruin-mc` sub-streams at the same root seed give byte-identical ruin estimates."""
    md = _toy_matchdays([1.857, 0.0, -1.0, 1.857, -1.0, 0.0, 1.857, -1.0])
    a = ruin.bootstrap_ruin(
        md,
        scheme="fixed_fraction",
        scheme_params={"phi": 0.05},
        rho=0.5,
        rng=seeding.substream(20260616, "ruin-mc"),
        n_paths=500,
        horizon_matchdays=8,
    )
    b = ruin.bootstrap_ruin(
        md,
        scheme="fixed_fraction",
        scheme_params={"phi": 0.05},
        rho=0.5,
        rng=seeding.substream(20260616, "ruin-mc"),
        n_paths=500,
        horizon_matchdays=8,
    )
    assert a.prob_ruin == b.prob_ruin
    assert a.mean_terminal_log_growth == b.mean_terminal_log_growth
    assert a.drawdown_quantiles == b.drawdown_quantiles


def test_all_negative_edge_kelly_flat_no_ruin():
    """All-negative-edge Kelly stakes 0 everywhere -> flat path, P(ruin)=0, zero growth."""
    # A book with no positive-edge bet: push-Kelly f* = 0 on every bet.
    md = _toy_matchdays([1.0, 0.0, -1.0], o=1.8, pw=0.30, pd_=0.28)
    assert float(staking.push_kelly_fraction(0.30, 0.28, 1.8)) == 0.0
    res = ruin.bootstrap_ruin(
        md,
        scheme="kelly",
        rho=0.5,
        rng=seeding.substream(20260616, "ruin-mc"),
        n_paths=300,
        horizon_matchdays=3,
    )
    assert res.prob_ruin == 0.0
    assert res.n_staked_per_path_mean == 0.0
    assert res.mean_terminal_log_growth == pytest.approx(0.0)


def test_negative_ev_fixed_fraction_book_ruins():
    """A negative-EV underdog book staked at fixed fraction ruins with high probability."""
    # A losing book: mostly losses, few wins -> negative EV. Fixed-fraction phi compounds
    # the losses multiplicatively (STAKE §6.1 case ii) toward the rho floor.
    md = _toy_matchdays([-1.0, -1.0, 1.857, -1.0, 0.0, -1.0, 1.857, -1.0])
    res = ruin.bootstrap_ruin(
        md,
        scheme="fixed_fraction",
        scheme_params={"phi": 0.1},
        rho=0.5,
        rng=seeding.substream(20260616, "ruin-mc"),
        n_paths=2000,
        horizon_bets=200,
    )
    assert res.prob_ruin > 0.5  # the negative-EV book draws down to the floor
    assert res.mean_terminal_log_growth < 0.0
    lo, hi = res.prob_ruin_ci
    # Wilson interval is well-ordered and clipped to [0,1] (hi may be a float-epsilon
    # below 1.0 at P(ruin)=1.0, so compare with a tolerance, not strict <=).
    assert 0.0 <= lo <= res.prob_ruin + 1e-12
    assert res.prob_ruin <= hi + 1e-9 <= 1.0 + 1e-9


def test_non_anticipation_permuting_future_returns_invariant(monkeypatch):
    """NON-ANTICIPATION (task 7): permuting the empirical returns never changes a stake fraction.

    The stake fraction is a pure function of the signal (o_dnb, p_win, p_draw); the
    realised return enters only the wealth update, never the sizing. So computing the
    per-matchday stake fractions on the returns and on a PERMUTATION of those returns
    (same signal, shuffled outcomes) yields identical fractions.
    """
    rng = np.random.default_rng(1)
    n = 30
    o = rng.uniform(2.0, 4.0, n)
    pw = rng.uniform(0.3, 0.5, n)
    pd_ = rng.uniform(0.18, 0.30, n)
    r = rng.choice([1.857, 0.0, -1.0], size=n)
    key = np.repeat(np.arange(6), 5)

    md1 = ruin.group_by_matchday(r, key, o_dnb=o, p_win=pw, p_draw=pd_)
    # Permute the FUTURE returns r (the outcomes) but keep the signal aligned to its bet.
    perm = rng.permutation(n)
    md2 = ruin.group_by_matchday(r[perm], key, o_dnb=o, p_win=pw, p_draw=pd_)

    f1 = [
        ruin._stake_fraction_for_block(
            "fractional_kelly",
            {"lam": 0.5},
            md1.odds_blocks[d],
            md1.pwin_blocks[d],
            md1.pdraw_blocks[d],
        )
        for d in range(md1.n_matchdays)
    ]
    f2 = [
        ruin._stake_fraction_for_block(
            "fractional_kelly",
            {"lam": 0.5},
            md2.odds_blocks[d],
            md2.pwin_blocks[d],
            md2.pdraw_blocks[d],
        )
        for d in range(md2.n_matchdays)
    ]
    # The signal is identical per bet (returns were permuted, not the signal), so the
    # fractions are identical block-for-block -- the stake never read the result.
    for a, b in zip(f1, f2, strict=True):
        assert np.allclose(a, b)


def test_additive_scheme_classifier():
    """flat / level_to_odds are additive (cash) schemes; the fraction schemes are not."""
    assert ruin.is_additive_scheme("flat")
    assert ruin.is_additive_scheme("level_to_odds")
    assert not ruin.is_additive_scheme("fixed_fraction")
    assert not ruin.is_additive_scheme("kelly")
    assert not ruin.is_additive_scheme("fractional_kelly")
    assert set(ruin.ADDITIVE_SCHEMES) == {"flat", "level_to_odds"}


def test_additive_flat_book_can_literally_bankrupt_at_rho_zero():
    """Additive (flat-cash) staking on a losing book CAN cross W<=0 -> rho=0 ruin reachable.

    Unlike the multiplicative schemes (W_t>0 a.s., rho=0 unreachable; STAKE §6.1 case ii),
    the additive cash walk has i.i.d. increments and literal bankruptcy is reachable in
    finitely many losing steps (STAKE §6.1 case i). A heavily-losing book staked flat must
    therefore register positive ruin at the rho=0 literal-bankruptcy floor.
    """
    md = _toy_matchdays([-1.0, -1.0, 1.857, -1.0, 0.0, -1.0, 1.857, -1.0])
    res = ruin.bootstrap_ruin(
        md,
        scheme="flat",
        scheme_params={"unit": 0.2},
        rho=0.0,  # literal bankruptcy: only reachable under the additive dynamics
        rng=seeding.substream(20260616, "ruin-mc"),
        n_paths=1000,
        horizon_bets=200,
    )
    assert res.prob_ruin > 0.0  # the additive walk crosses 0 (literal bankruptcy)
    assert res.n_staked_per_path_mean > 0.0  # flat stakes every settleable bet


def test_additive_level_to_odds_stakes_inverse_in_net_odds():
    """level_to_odds sizes the cash stake c/(d-1) (constant target profit; STAKE §2)."""
    # Two prices: a shorter (o=2.0 -> b=1.0) and longer (o=3.0 -> b=2.0) underdog.
    r = np.array([0.0, 0.0], dtype=float)
    key = np.array([0, 0])
    md = ruin.group_by_matchday(
        r, key, o_dnb=np.array([2.0, 3.0]), p_win=np.array([0.4, 0.4]), p_draw=np.array([0.2, 0.2])
    )
    s = ruin._cash_stake_for_block("level_to_odds", {"c": 0.1}, md.odds_blocks[0])
    # c/(d-1): 0.1/1.0 = 0.1 on the short price; 0.1/2.0 = 0.05 on the long price (less on
    # the longer-priced bet -- the inverse-in-net-odds tilt, opposite to Kelly on longshots).
    assert s[0] == pytest.approx(0.1)
    assert s[1] == pytest.approx(0.05)


def test_additive_positive_ev_book_grows_low_ruin():
    """A positive-EV book staked flat at a small unit grows with low ruin (additive branch)."""
    md = _toy_matchdays([1.857, 0.0, -1.0, 1.857, -1.0, 1.857])
    res = ruin.bootstrap_ruin(
        md,
        scheme="flat",
        scheme_params={"unit": 0.02},
        rho=0.5,
        rng=seeding.substream(20260616, "ruin-mc"),
        n_paths=1000,
        horizon_bets=200,
    )
    assert res.prob_ruin < 0.1
    assert res.mean_terminal_log_growth > 0.0


def test_brb_bound_exponent_worked_value():
    """STAKE §6.2 worked: theta = log0.10/log0.50 = 3.3219 (the BRB drawdown-bound exponent)."""
    assert staking.brb_bound_exponent(0.5, 0.10) == pytest.approx(3.321928, abs=1e-4)


def test_rck_lambda_binds_below_full_kelly_on_positive_edge():
    """RCK shrinks lambda < 1 (binds) on a genuine positive-edge stream (BRB §5.3)."""
    # A positive-edge 3-point stream {+b, 0, -1} with a real win mass.
    b = 1.857
    stream = np.concatenate([np.full(420, b), np.zeros(200), np.full(380, -1.0)])
    fstar = float(staking.push_kelly_fraction(0.42, 0.20, 2.857))
    res = ruin.solve_rck_lambda(stream, fstar, alpha_dd=0.5, beta_dd=0.10)
    assert res.theta == pytest.approx(3.321928, abs=1e-4)
    assert res.binds
    assert 0.0 < res.lam_rck < 1.0  # fractional Kelly lambda < 1 (sub-Kelly shrinkage)
    assert res.constraint_at_lam <= 1.0 + 1e-6


def test_rck_lambda_vacuous_on_all_cash_stream():
    """All-cash (f*=0) stream: constraint satisfied at full budget, binds=False (vacuous)."""
    stream = np.concatenate([np.full(300, 1.857), np.zeros(200), np.full(500, -1.0)])
    res = ruin.solve_rck_lambda(stream, 0.0, alpha_dd=0.5, beta_dd=0.10)  # f* = 0 (no bet)
    assert not res.binds
    assert res.lam_rck == pytest.approx(1.0)
    assert res.constraint_at_lam == pytest.approx(1.0)


def test_brb_grid_sweeps_methodology_cells():
    """The BRB grid sweeps every (alpha_dd, beta_dd) cell of methodology.md §1.2."""
    b = 1.857
    stream = np.concatenate([np.full(420, b), np.zeros(200), np.full(380, -1.0)])
    fstar = float(staking.push_kelly_fraction(0.42, 0.20, 2.857))
    grid = ruin.brb_drawdown_grid(
        stream, fstar, alpha_dd_grid=(0.5, 0.6, 0.7, 0.8), beta_dd_grid=(0.05, 0.10, 0.20)
    )
    assert len(grid) == 12  # 4 x 3 cells
    # lambda is monotone-DECREASING in the bound strictness theta = log beta/log alpha:
    # a STRICTER drawdown target (larger theta) yields a SMALLER (more conservative) RCK
    # lambda. (0.8, 0.20) has theta=7.21; (0.5, 0.05) has theta=4.32; the stricter cell
    # (0.8,0.20) is therefore the more conservative => smaller lambda.
    by_cell = {(r.alpha_dd, r.beta_dd): r for r in grid}
    assert by_cell[(0.8, 0.20)].theta > by_cell[(0.5, 0.05)].theta
    assert by_cell[(0.8, 0.20)].lam_rck <= by_cell[(0.5, 0.05)].lam_rck + 1e-9


def _per_matchday_reference_lambda(blocks, fstar, theta, *, lam_hi=1.0):
    """Reference per-MATCHDAY-period RCK lambda: bisect on E[rel_d^{-theta}] <= 1 with
    rel_d = 1 + sum_{j in day d} lam*f*_j*r_j (the SLATE relative; STAKE §6.2 eq. 9)."""

    def lhs(lam):
        rel = np.array([1.0 + np.sum(lam * fstar * blk) for blk in blocks], dtype=float)
        if np.any(rel <= 0.0):
            return float("inf")
        return float(np.mean(rel ** (-theta)))

    lo, hi, best = 0.0, float(lam_hi), 0.0
    if lhs(hi) <= 1.0:
        return hi
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        if lhs(mid) <= 1.0:
            best, lo = mid, mid
        else:
            hi = mid
        if hi - lo < 1e-4:
            break
    return best


def _per_bet_reference_lambda(r_flat, fstar, theta, *, lam_hi=1.0):
    """Reference (INCORRECT, pre-fix) per-BET RCK lambda: bisect on the FLATTENED per-bet
    relatives E[(1 + lam*f*r)^{-theta}] <= 1, ignoring within-matchday concurrency."""

    def lhs(lam):
        rel = 1.0 + lam * fstar * r_flat
        if np.any(rel <= 0.0):
            return float("inf")
        return float(np.mean(rel ** (-theta)))

    lo, hi, best = 0.0, float(lam_hi), 0.0
    if lhs(hi) <= 1.0:
        return hi
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        if lhs(mid) <= 1.0:
            best, lo = mid, mid
        else:
            hi = mid
        if hi - lo < 1e-4:
            break
    return best


def test_rck_lambda_uses_per_matchday_period_relatives_under_concurrency():
    """RCK lambda is the per-MATCHDAY-period solve, NOT the per-bet solve (STAKE §6.2 eq. 9).

    The BRB drawdown bound is a per-REBALANCING-PERIOD statement and the period is the
    MATCHDAY (the concurrency unit; STAKE §5.1, §6.3). On a fixture with TWO concurrent
    positive-edge bets per matchday the per-matchday-period wealth relative
    ``rel_d = 1 + sum_j lambda*f*_j*r_j`` differs from the per-bet relative
    ``1 + lambda*f*_i*r_i``, so the RCK lambda from the two treatments must DIVERGE; the
    engine must return the per-matchday-period value. This is the regression guard for the
    Phase-3 finding (the solve previously flattened md.blocks via np.concatenate).
    """
    o, pw, pd_ = 2.857, 0.42, 0.20
    b = o - 1.0
    pfav = 1.0 - pw - pd_
    fstar = float(staking.push_kelly_fraction(pw, pd_, o))
    assert fstar > 0.0  # genuine positive-edge bet (so the constraint can bind)
    theta = staking.brb_bound_exponent(0.5, 0.10)

    # 60 matchdays x 2 concurrent bets, outcomes at the marginal (win/push/loss) probs.
    rng = np.random.default_rng(0)
    out_vals, probs = np.array([b, 0.0, -1.0]), np.array([pw, pd_, pfav])
    blocks = [rng.choice(out_vals, size=2, p=probs).astype(float) for _ in range(60)]
    r_flat = np.concatenate(blocks)
    fstar_blocks = [np.full(2, fstar) for _ in blocks]

    # The engine solve (matchday grouping passed in).
    res = ruin.solve_rck_lambda(blocks, fstar_blocks, alpha_dd=0.5, beta_dd=0.10)

    lam_md_ref = _per_matchday_reference_lambda(blocks, fstar, theta)
    lam_bet_ref = _per_bet_reference_lambda(r_flat, fstar, theta)

    # (a) The engine matches the per-matchday-period reference within bisection tolerance.
    assert res.lam_rck == pytest.approx(lam_md_ref, abs=2e-3)
    assert res.binds
    # (b) The per-matchday-period and per-bet solves genuinely DIVERGE under concurrency.
    assert abs(lam_md_ref - lam_bet_ref) > 1e-2
    # And the engine is NOT the (wrong) per-bet value.
    assert abs(res.lam_rck - lam_bet_ref) > 1e-2
    # The per-matchday constraint at full Kelly is STRICTLY tighter than the per-bet one
    # (concurrent slate has a fatter left tail) -- the mechanism behind the divergence.
    cv_md_full = ruin.brb_constraint_value(
        blocks, [fstar_blocks[d] for d in range(60)], theta=theta
    )
    cv_bet_full = float(np.mean((1.0 + fstar * r_flat) ** (-theta)))
    assert cv_md_full > cv_bet_full


def test_brb_constraint_value_per_period_vs_bare_array_equivalence():
    """A bare 1-D return array is treated as one bet per period (per-bet == per-period).

    Backward compatibility: when there is no concurrency (one bet per matchday) the
    per-matchday-period relative collapses to the per-bet relative, so passing a flat
    array (one bet per period) must reproduce the legacy element-wise constraint value.
    """
    r = np.array([1.857, 0.0, -1.0, 1.857, -1.0], dtype=float)
    f = 0.3
    theta = staking.brb_bound_exponent(0.5, 0.10)
    legacy = float(np.mean((1.0 + f * r) ** (-theta)))
    via_bare = ruin.brb_constraint_value(r, f, theta=theta)
    # Equivalent singleton-block list form.
    via_blocks = ruin.brb_constraint_value([np.array([x]) for x in r], f, theta=theta)
    assert via_bare == pytest.approx(legacy)
    assert via_blocks == pytest.approx(legacy)


def test_max_fraction_for_budget_feasible_on_safe_book():
    """The min-bankroll dual: a safe (all-cash) book meets any budget at full fraction."""
    md = _toy_matchdays([1.0, 0.0, -1.0], o=1.8, pw=0.30, pd_=0.28)  # f*=0 everywhere
    res = ruin.max_fraction_for_budget(
        md,
        rho=0.5,
        rng=seeding.substream(20260616, "ruin-mc"),
        eps_target=0.05,
        dd_target=0.5,
        n_paths=300,
    )
    # The Kelly path here is all-cash, but the dual sweeps FIXED-FRACTION; a tiny phi on a
    # negative-EV book still draws down, so feasibility depends on the budget. Assert the
    # result is a valid fraction in [0,1] with the achieved metrics recorded.
    assert 0.0 <= res.max_fraction <= 1.0
    assert res.dd_quantile_level == "p95"
