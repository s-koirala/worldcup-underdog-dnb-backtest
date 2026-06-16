"""Phase-3 staking/ruin engine tests -- the slice-brief items not already pinned.

The five staking schemes, the gross+net ledger conservation + non-anticipation, the
three-outcome Kelly FOC + d->0 degeneration, the BRB theta mapping, the RCK solve, the
vector-Kelly program, the concurrent-independence G-test, the matchday-block bootstrap
determinism, the precision-target B, the cost model, and the lambda*=0 frontier verdict
are already covered in test_staking.py / test_staking_schemes.py / test_ledger.py /
test_costs.py / test_ruin.py / test_vector_kelly.py / test_frontier.py / test_seeding.py.

This file closes the four engine-level items the slice brief names that those files do
NOT yet assert directly:

  1. LAMBDA-MONOTONICITY OF GROWTH (brief: "lambda-monotonicity of growth"). The
     one-step expected log-growth g(lambda*f*) is strictly INCREASING in lambda on
     (0, 1] for a genuine positive-edge bet (the Kelly optimum sits AT full Kelly), and
     over-betting (lambda > 1) loses growth -- the (2c - c^2) shape of STAKE §4.3. Scored
     with the same vk.expected_log_growth the vector program maximises, so it is the
     project's own growth object, not a re-derivation.

  2. UNCONSTRAINED FULL KELLY VIOLATES THE BRB theta=1 BOUND while the RCK solution
     satisfies its own theta bound (brief; STAKE §6.2: BRB's unconstrained Kelly has
     Prob(W_min<0.7) ~ 0.40 >> alpha^1 = 0.7). Asserted BOTH at the engine level (the
     matchday-block bootstrap drawdown probability exceeds the alpha^1 line for full
     Kelly) AND analytically (E[rel^{-theta}] at the drawdown target exceeds 1 for full
     Kelly but binds <= 1 at the RCK multiplier).

  3. RUIN-ENGINE ORDER-INDEPENDENCE (brief: "the matchday-block bootstrap drawing from
     the 'ruin-mc' sub-stream is byte-identical whether or not upstream stages ran first
     (order-independence)"). test_seeding.py proves the RNG PRIMITIVE is
     order-independent; this proves the ENGINE OUTPUT (bootstrap_ruin) is byte-identical
     when an upstream stage draws from its own sub-stream in between -- the integration-
     level acceptance the brief asks for.

  4. THE SLIPPAGE QUANTILE IS READ FROM CONFIG, NOT HARD-CODED (brief). Changing
     costs.slippage_quantile changes the applied per-leg slippage value (it is the
     selected level into the empirical open->close distribution); no magnitude is baked
     into the cost code.

No magic numbers beyond the STAKE-worked probabilities/odds, the methodology.md §1.2
risk grid, and the deterministic root seed (the single CLAUDE.md exemption).
"""

from __future__ import annotations

import numpy as np
import pytest
from src import costs, ruin, seeding, staking
from src import vector_kelly as vk

ROOT = 20260616

# STAKE §3.3 worked positive-edge cell: o_DNB = 2.857, p_W = 0.42, p_D = 0.20 (used so
# the push-Kelly f* is genuinely positive and the bet actually fires).
WORKED_O = 2.857
WORKED_PW = 0.42
WORKED_PD = 0.20


# ---------------------------------------------------------------------------
# 1. Lambda-monotonicity of expected log-growth (STAKE §4.3 (2c - c^2) shape).
# ---------------------------------------------------------------------------


def _g_at_lambda(lam: float, *, o: float, pw: float, pd_: float) -> float:
    """One-step expected log-growth of the lambda-fractional Kelly bet (vk's own object).

    Reuses the n=1 (one bet + cash) payoff matrix and the independence-default joint pi,
    scored with vector_kelly.expected_log_growth -- the SAME growth functional the vector
    program maximises -- so the monotonicity test is on the project's growth object.
    """
    o_arr = np.array([o])
    fstar = float(staking.push_kelly_fraction(pw, pd_, o))
    f = np.array([lam * fstar, 1.0 - lam * fstar])
    payoff = vk.payoff_matrix(o_arr)
    pi = vk.independent_joint(np.array([pw]), np.array([pd_]))
    return vk.expected_log_growth(payoff, f, pi)


def test_growth_strictly_increasing_in_lambda_up_to_full_kelly():
    """g(lambda*f*) strictly increases in lambda on [0,1]; the optimum is AT full Kelly."""
    fstar = float(staking.push_kelly_fraction(WORKED_PW, WORKED_PD, WORKED_O))
    assert fstar > 0.0  # the worked cell is genuinely positive-edge
    lams = [0.0, 0.25, 0.5, 0.75, 1.0]
    gs = [_g_at_lambda(L, o=WORKED_O, pw=WORKED_PW, pd_=WORKED_PD) for L in lams]
    # Strictly increasing across the fractional-Kelly ladder (more Kelly -> more growth,
    # since full Kelly is the log-growth maximiser and g is concave below it).
    for i in range(len(gs) - 1):
        assert gs[i] < gs[i + 1]
    # lambda = 0 (all cash) earns zero growth exactly.
    assert gs[0] == pytest.approx(0.0, abs=1e-12)


def test_overbetting_past_full_kelly_loses_growth():
    """Over-betting (lambda > 1) is on the FAR side of the optimum -> growth falls (STAKE §4.1)."""
    g_full = _g_at_lambda(1.0, o=WORKED_O, pw=WORKED_PW, pd_=WORKED_PD)
    g_over = _g_at_lambda(1.5, o=WORKED_O, pw=WORKED_PW, pd_=WORKED_PD)
    assert g_over < g_full  # over-betting destroys growth (the asymmetric Kelly penalty)


def test_half_kelly_retains_more_than_half_the_growth():
    """STAKE §4.3 (2c - c^2): half-Kelly keeps 75% of full-Kelly growth in the small-bet limit.

    The exact discrete g is not the Gaussian (2c - c^2) form, but the qualitative claim --
    half-Kelly keeps MORE than half the growth (the asymmetry that motivates fractional
    Kelly) -- must hold for a small positive-edge bet.
    """
    g_full = _g_at_lambda(1.0, o=WORKED_O, pw=WORKED_PW, pd_=WORKED_PD)
    g_half = _g_at_lambda(0.5, o=WORKED_O, pw=WORKED_PW, pd_=WORKED_PD)
    assert g_half > 0.5 * g_full  # > half the growth for half the Kelly fraction


# ---------------------------------------------------------------------------
# 2. Unconstrained full Kelly violates the BRB theta=1 bound; RCK satisfies its theta.
# ---------------------------------------------------------------------------


def _positive_edge_matchdays(n_per_day: int = 8) -> ruin.MatchdayReturns:
    """A genuinely positive-edge matchday multiset at the worked price (so full Kelly fires).

    The win/push/loss profit multiples are mixed so the bootstrap edge is positive and
    full Kelly stakes a real fraction (~0.27 of bankroll) -- the precondition for the BRB
    drawdown bound to be a meaningful constraint (a zero-stake book trivially satisfies it).
    """
    b = WORKED_O - 1.0
    profit = [b, b, b, b, 0.0, 0.0, -1.0, -1.0, -1.0, -1.0]
    r = np.array(profit * n_per_day, dtype=float)
    key = np.repeat(np.arange(len(profit)), n_per_day)
    n = r.size
    return ruin.group_by_matchday(
        r,
        key,
        o_dnb=np.full(n, WORKED_O),
        p_win=np.full(n, WORKED_PW),
        p_draw=np.full(n, WORKED_PD),
    )


def test_full_kelly_fires_a_real_fraction_on_the_positive_edge_cell():
    """Pre-condition: the worked positive-edge cell makes full Kelly stake a real fraction."""
    fstar = float(staking.push_kelly_fraction(WORKED_PW, WORKED_PD, WORKED_O))
    assert fstar > 0.2  # ~0.269 -- a substantial bet, so the drawdown bound is binding


def test_full_kelly_violates_the_theta1_drawdown_bound_engine_level():
    """Unconstrained full Kelly: Prob(W_min < alpha) >> alpha^1 (STAKE §6.2; engine level).

    BRB show the unconstrained Kelly bet's running-minimum drawdown probability blows
    through the theta=1 line (their Prob(W_min<0.7) ~ 0.40 > 0.7^1). Here, with rho = alpha
    the bootstrap's ruin indicator 1{W_min <= alpha*W_0} IS exactly Prob(W_min < alpha);
    full Kelly on a real positive-edge book must exceed the alpha^1 = alpha bound.
    """
    md = _positive_edge_matchdays()
    alpha = 0.7  # BRB experiment threshold; theta = 1 bound is alpha^1 = 0.7
    res = ruin.bootstrap_ruin(
        md,
        scheme="kelly",
        rho=alpha,
        rng=seeding.substream(ROOT, "ruin-mc"),
        n_paths=4000,
        horizon_matchdays=40,
    )
    # The theta=1 BRB bound would require Prob(W_min<alpha) <= alpha^1 = alpha; full Kelly
    # VIOLATES it (the quantitative face of MTZ "large drawdowns"; STAKE §6.2).
    assert res.prob_ruin > alpha


def test_rck_satisfies_its_theta_bound_while_full_kelly_violates_it():
    """The RCK multiplier binds E[rel^{-theta}] <= 1; full Kelly (lam=1) exceeds 1 (STAKE §6.2).

    Analytic companion to the engine-level test: at the drawdown target (alpha_dd, beta_dd)
    the exponent is theta = log beta/log alpha > 1. The risk-constrained-Kelly fraction
    makes E[(1 + lam f* r)^{-theta}] <= 1 (the constraint binds), whereas the unconstrained
    full-Kelly fraction blows the SAME constraint above 1 -- it does not meet the drawdown
    target, which is exactly why the bet must be shrunk to a fractional lambda < 1 (BRB §5.3).
    """
    b = WORKED_O - 1.0
    # A positive-edge 3-point empirical stream with a real win mass (matches test_ruin).
    stream = np.concatenate([np.full(420, b), np.zeros(200), np.full(380, -1.0)])
    fstar = float(staking.push_kelly_fraction(WORKED_PW, WORKED_PD, WORKED_O))
    theta = staking.brb_bound_exponent(0.5, 0.10)
    rck = ruin.solve_rck_lambda(stream, fstar, alpha_dd=0.5, beta_dd=0.10)
    assert rck.binds
    assert 0.0 < rck.lam_rck < 1.0  # sub-Kelly shrinkage
    # RCK fraction: constraint binds at <= 1 (the drawdown target is met).
    c_rck = ruin.brb_constraint_value(stream, rck.lam_rck * fstar, theta=theta)
    assert c_rck <= 1.0 + 1e-6
    # Unconstrained full Kelly (lambda = 1): the SAME constraint is VIOLATED (> 1).
    c_full = ruin.brb_constraint_value(stream, 1.0 * fstar, theta=theta)
    assert c_full > 1.0


# ---------------------------------------------------------------------------
# 3. Ruin-engine order-independence (ENGINE output, not just the RNG primitive).
# ---------------------------------------------------------------------------


def test_bootstrap_ruin_is_order_independent_against_an_upstream_draw():
    """bootstrap_ruin output is byte-identical whether or not an upstream stage drew first.

    test_seeding.py proves seeding.substream(ROOT, "ruin-mc") is order-independent at the
    Generator level. This proves the consequence the slice brief actually requires: the
    matchday-block bootstrap ENGINE -- the full RuinResult (prob_ruin, growth, drawdown
    quantiles, n_staked) -- is identical whether or not the bootstrap-ci / vector-kelly /
    ingest stages instantiated and DREW from their own sub-streams in the same process
    first. The ruin-mc stream is reconstructed from (root_seed, stage_name) alone, never
    mutated by another stage, so the deployment-risk numbers are reproducible per-stage.
    """
    md = _positive_edge_matchdays()
    kwargs = dict(
        scheme="fixed_fraction",
        scheme_params={"phi": 0.05},
        rho=0.5,
        n_paths=800,
        horizon_matchdays=20,
    )

    # (a) Standalone: ruin-mc is the first stream touched in the process path.
    standalone = ruin.bootstrap_ruin(md, rng=seeding.substream(ROOT, "ruin-mc"), **kwargs)

    # (b) After upstream stages each draw from THEIR OWN sub-streams (simulating the
    #     per-phase entrypoints running earlier in the same process).
    for upstream in ("ingest", "price", "stake", "bootstrap-ci", "vector-kelly"):
        seeding.substream(ROOT, upstream).random(257)
    after_upstream = ruin.bootstrap_ruin(md, rng=seeding.substream(ROOT, "ruin-mc"), **kwargs)

    # Every reported quantity is byte-identical (no dependence on execution order).
    assert standalone.prob_ruin == after_upstream.prob_ruin
    assert standalone.mean_terminal_log_growth == after_upstream.mean_terminal_log_growth
    assert standalone.median_terminal_log_growth == after_upstream.median_terminal_log_growth
    assert standalone.drawdown_quantiles == after_upstream.drawdown_quantiles
    assert standalone.max_drawdown_mean == after_upstream.max_drawdown_mean
    assert standalone.n_staked_per_path_mean == after_upstream.n_staked_per_path_mean


def test_ruin_mc_uses_the_named_substream_not_the_root_or_global():
    """The ruin engine is fed the ruin-mc sub-stream, distinct from the root/other streams.

    A defensive check that the engine numbers move when (and only when) the ruin-mc stream
    changes: the vector-kelly stream produces a DIFFERENT bootstrap path (so no stage is
    silently sharing the root generator or a global np.random).
    """
    md = _positive_edge_matchdays()
    kwargs = dict(
        scheme="fixed_fraction",
        scheme_params={"phi": 0.1},
        rho=0.5,
        n_paths=1500,
        horizon_matchdays=20,
    )
    a = ruin.bootstrap_ruin(md, rng=seeding.substream(ROOT, "ruin-mc"), **kwargs)
    b = ruin.bootstrap_ruin(md, rng=seeding.substream(ROOT, "vector-kelly"), **kwargs)
    # Different sub-streams -> different bootstrap resamples -> the estimates differ (the
    # streams are genuinely independent, not aliased to one shared generator).
    assert (a.prob_ruin != b.prob_ruin) or (
        a.mean_terminal_log_growth != b.mean_terminal_log_growth
    )


# ---------------------------------------------------------------------------
# 4. The slippage quantile is READ FROM CONFIG, not hard-coded.
# ---------------------------------------------------------------------------


_OCM = {
    "n_observable": 1000,
    "pooled": {"p50": 0.0523, "p90": 0.1296, "p95": 0.1630, "p99": 0.2470},
    "by_odds_bucket": {},
}


def test_slippage_quantile_is_config_driven_not_hardcoded():
    """costs.slippage_quantile selects the applied per-leg slippage VALUE (no baked magnitude).

    Building the cost model with different config quantile levels selects a different
    empirical-distribution value each time, and that value equals the corresponding entry
    of the supplied open->close distribution -- i.e. the magnitude lives in the DATA and is
    SELECTED by config, never written into the cost code (CLAUDE.md no-magic-number).
    """
    for level in ("p50", "p90", "p95", "p99"):
        cm = costs.from_config({"slippage_quantile": level}, open_close_moves=_OCM)
        assert cm.slippage.quantile_level == level
        assert cm.slippage.value == pytest.approx(_OCM["pooled"][level])
    # Changing only the config level changes the applied slippage value (config drives it).
    v50 = costs.from_config({"slippage_quantile": "p50"}, open_close_moves=_OCM).slippage.value
    v95 = costs.from_config({"slippage_quantile": "p95"}, open_close_moves=_OCM).slippage.value
    assert v50 != v95
    assert v95 > v50  # the tail level is a larger adverse move


def test_net_return_uses_the_config_selected_slippage_value():
    """The selected quantile flows through to the net win return (config -> applied cost).

    The effective win odds are o*(1 - s) with s the config-selected slippage value; a
    larger config quantile level -> a larger shave -> a strictly smaller net win return.
    No slippage magnitude is hard-coded -- swapping the config level moves the net number.
    """
    o = WORKED_O
    cm50 = costs.from_config({"slippage_quantile": "p50"}, open_close_moves=_OCM)
    cm95 = costs.from_config({"slippage_quantile": "p95"}, open_close_moves=_OCM)
    net50 = cm50.net_return(o, o)
    net95 = cm95.net_return(o, o)
    assert net50 == pytest.approx(o * (1.0 - _OCM["pooled"]["p50"]), abs=1e-9)
    assert net95 == pytest.approx(o * (1.0 - _OCM["pooled"]["p95"]), abs=1e-9)
    assert net95 < net50 < o  # heavier config slippage -> deeper cost; both below gross


def test_net_of_cost_strictly_below_gross_on_a_win():
    """Net-of-cost < gross on a win (the brief's precondition for any reported net metric)."""
    cm = costs.from_config({"slippage_quantile": "p50"}, open_close_moves=_OCM)
    o = WORKED_O
    gross_win = o  # settlement gross win multiple
    net_win = cm.net_return(o, gross_win)
    assert net_win < gross_win  # costs strictly bite on the realised win
    # Push and loss carry no cost (stake refunded / fully lost), so net == gross there.
    assert cm.net_return(o, 1.0) == 1.0
    assert cm.net_return(o, 0.0) == 0.0
