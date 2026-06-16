"""Growth-drawdown efficient frontier per staking scheme (Phase 3 task 6; STAKE §7.3).

The engine behind F-07 / F-08 / F-09 and T-04 / T-05 / T-06 (the rendered figures are
Phase 5; this produces the DATA / tables). For each scheme, sweeping its parameter
traces a curve in ``(expected log-growth, max-drawdown-quantile)`` space (the
matchday-block-bootstrap outputs of src.ruin); the EFFICIENT FRONTIER is the upper-left
envelope -- maximum growth for each drawdown budget (STAKE §7.3).

Theory (STAKE §7.3): edge-proportional Kelly-family sizing DOMINATES odds-agnostic
(fixed-fraction) and naively-tilted (level-to-odds) sizing at each drawdown budget; the
honest ordering is ``RCK >= fractional-Kelly >= {fixed-fraction, level-to-odds}`` with
the RCK-vs-fractional gap closing toward zero as the return distribution becomes
continuous. This module traces the EMPIRICAL frontier from the bootstrap (not just
theory), reporting fractional Kelly AND the RCK solution so the gap is measured.

HONEST-PRIOR all-negative-edge handling (slice brief; STAKE §7.3, Open Question 6). For
the underdog DNB the de-vigged edge is negative for (almost) every bet, so ``f* <= 0 ->
stake 0`` and the Kelly-family frontier collapses to the single cash point
``(growth=0, drawdown=0)``: every cell sits ON the zero-growth axis, none above it. The
honest output is then ``lambda* = 0 (do not bet)``. The module DETECTS this case and,
rather than emitting a degenerate frontier, also reports the COUNTERFACTUAL: the
bankroll / ``lambda`` that WOULD be required were the edge real -- a power/feasibility
statement (:func:`required_lambda_if_edge_real`), per the slice brief. ``lambda* = 0
dominating`` is flagged explicitly in :class:`FrontierReport.lambda_star_zero_dominates`.

No magic numbers: the parameter grids are the swept config grids / methodology.md §1.2
risk grids; ``B`` from the precision target (src.ruin); the drawdown quantile level is a
reported position in the empirical distribution. pathlib not required (pure numeric; the
empirical returns + grids are supplied by the caller).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from src import ruin, staking

# The drawdown-quantile level the frontier x-axis uses (the max-DD budget). p95 is the
# reported budget level (a tail position in the empirical max-DD distribution, not an
# asserted magnitude); the full ladder is carried per point for the figures.
DEFAULT_DD_QUANTILE_LEVEL = "p95"


@dataclass(frozen=True)
class FrontierPoint:
    """One (scheme, parameter) point on the growth-drawdown frontier."""

    scheme: str
    param_name: str  # "phi" / "c" / "lam" / "" (kelly takes none)
    param_value: float
    expected_log_growth: float  # mean terminal log-growth from the bootstrap (src.ruin)
    drawdown_budget: float  # max-DD at DEFAULT_DD_QUANTILE_LEVEL
    prob_ruin: float
    prob_ruin_ci: tuple[float, float]
    drawdown_quantiles: dict[str, float]
    n_staked_per_path_mean: float


@dataclass(frozen=True)
class SchemeFrontier:
    """The growth-drawdown curve for one scheme across its parameter grid (STAKE §7.3)."""

    scheme: str
    points: list[FrontierPoint]
    efficient_points: list[FrontierPoint]  # the upper-left envelope (max growth per DD budget)
    all_below_zero_growth: bool  # True iff no point achieves positive expected log-growth


@dataclass(frozen=True)
class RequiredEdgeFeasibility:
    """The bankroll / lambda that WOULD be required were the edge real (STAKE §7.3 / OQ6)."""

    hypothetical_edge: float  # the assumed per-bet positive edge mu (literature-anchored)
    o_dnb_ref: float  # the reference DNB price the counterfactual is evaluated at
    p_draw_ref: float  # the reference draw prob
    implied_full_kelly_f: float  # the push-Kelly f* that edge WOULD imply
    rck_lambda: float  # the drawdown-constrained lambda at the operating (alpha_dd, beta_dd)
    operating_alpha_dd: float
    operating_beta_dd: float
    deployed_fraction: float  # rck_lambda * implied_full_kelly_f (the WOULD-BE stake fraction)
    note: str = ""


@dataclass(frozen=True)
class FrontierReport:
    """The full per-scheme frontier deliverable + the honest lambda*=0 verdict (Phase 3 task 6)."""

    scheme_frontiers: dict[str, SchemeFrontier]
    rck_grid: list[ruin.RCKResult]  # lambda(alpha_dd, beta_dd) across methodology.md §1.2
    lambda_star_zero_dominates: bool  # True iff the Kelly-family frontier is the cash point only
    n_positive_edge_bets: int
    n_bets: int
    required_if_edge_real: RequiredEdgeFeasibility | None
    dd_quantile_level: str = DEFAULT_DD_QUANTILE_LEVEL
    note: str = ""


def _efficient_envelope(points: list[FrontierPoint]) -> list[FrontierPoint]:
    """Upper-left envelope: for each point keep it iff no other point has >= growth AND <= DD.

    A point is on the efficient frontier iff it is not DOMINATED -- i.e. no other point
    delivers at least as much expected log-growth at no greater drawdown budget (with a
    strict improvement on at least one axis). This is the maximum-growth-per-drawdown-
    budget envelope (STAKE §7.3). Ties (identical growth AND drawdown) keep the first.
    """
    eff: list[FrontierPoint] = []
    for i, p in enumerate(points):
        dominated = False
        for j, q in enumerate(points):
            if i == j:
                continue
            better_or_equal = (
                q.expected_log_growth >= p.expected_log_growth
                and q.drawdown_budget <= p.drawdown_budget
            )
            strictly_better = (
                q.expected_log_growth > p.expected_log_growth
                or q.drawdown_budget < p.drawdown_budget
            )
            if better_or_equal and strictly_better:
                dominated = True
                break
        if not dominated:
            eff.append(p)
    eff.sort(key=lambda pt: pt.drawdown_budget)
    return eff


def trace_scheme_frontier(
    md: ruin.MatchdayReturns,
    *,
    scheme: str,
    param_grid: list[float] | None,
    rho: float,
    rng: np.random.Generator,
    n_paths: int | None = None,
    mean_block: float = ruin.DEFAULT_MEAN_BLOCK_MATCHDAYS,
    dd_quantile_level: str = DEFAULT_DD_QUANTILE_LEVEL,
) -> SchemeFrontier:
    """Trace one scheme's growth-drawdown curve across its parameter grid (STAKE §7.3).

    Runs the matchday-block bootstrap (src.ruin.bootstrap_ruin) at each grid value and
    records the ``(expected log-growth, drawdown-budget)`` point. ``kelly`` takes no
    parameter (a single point); ``fixed_fraction`` sweeps ``phi``; ``fractional_kelly``
    sweeps ``lam``. The efficient envelope is the upper-left frontier. The RNG MUST be
    the ``ruin-mc`` sub-stream.
    """
    points: list[FrontierPoint] = []
    # Each scheme sweeps its own free parameter (STAKE §2 table): kelly takes none;
    # fixed_fraction sweeps phi; fractional_kelly sweeps lam; the ADDITIVE cash schemes
    # sweep the constant cash unit (flat) / target profit (level_to_odds). The additive
    # schemes are simulated by the additive (cash) branch of src.ruin.bootstrap_ruin.
    param_name_by_scheme = {
        "fixed_fraction": "phi",
        "fractional_kelly": "lam",
        "flat": "unit",
        "level_to_odds": "c",
    }
    if scheme == "kelly":
        grid_iter: list[tuple[str, float]] = [("", float("nan"))]
    elif scheme in param_name_by_scheme:
        pname = param_name_by_scheme[scheme]
        grid_iter = [(pname, float(v)) for v in (param_grid or [])]
    else:
        raise ValueError(
            f"scheme {scheme!r} not supported by the bootstrap frontier; use one of "
            f"{(*tuple(param_name_by_scheme), 'kelly')}"
        )

    for pname, pval in grid_iter:
        params = {pname: pval} if pname else {}
        res = ruin.bootstrap_ruin(
            md,
            scheme=scheme,
            scheme_params=params,
            rho=rho,
            rng=rng,
            n_paths=n_paths,
            mean_block=mean_block,
        )
        points.append(
            FrontierPoint(
                scheme=scheme,
                param_name=pname,
                param_value=pval,
                expected_log_growth=res.mean_terminal_log_growth,
                drawdown_budget=res.drawdown_quantiles.get(dd_quantile_level, float("nan")),
                prob_ruin=res.prob_ruin,
                prob_ruin_ci=res.prob_ruin_ci,
                drawdown_quantiles=res.drawdown_quantiles,
                n_staked_per_path_mean=res.n_staked_per_path_mean,
            )
        )
    all_below = all(
        (not np.isfinite(p.expected_log_growth)) or p.expected_log_growth <= 0.0 for p in points
    )
    return SchemeFrontier(
        scheme=scheme,
        points=points,
        efficient_points=_efficient_envelope(points),
        all_below_zero_growth=all_below,
    )


def required_lambda_if_edge_real(
    *,
    hypothetical_edge: float,
    o_dnb_ref: float,
    p_draw_ref: float,
    profit_multiples_if_edge: npt.ArrayLike,
    operating_alpha_dd: float,
    operating_beta_dd: float,
) -> RequiredEdgeFeasibility:
    """The bankroll/lambda that WOULD be required were the edge real (STAKE §7.3, OQ6).

    The honest-prior verdict is ``lambda* = 0`` (do not bet) because the de-vigged edge
    is negative everywhere. This computes the COUNTERFACTUAL feasibility statement the
    slice brief mandates: given a hypothetical literature-anchored positive per-bet edge
    ``mu`` at a reference DNB price ``o_dnb_ref`` with draw prob ``p_draw_ref``,
      1. invert the edge to the win prob it implies:
         ``mu = p_W*(o-1) - (1 - p_W - p_D)`` => ``p_W = (mu + 1 - p_D) / o``;
      2. compute the push-Kelly ``f*`` that win prob WOULD give (src.staking);
      3. solve the RCK multiplier ``lambda`` at the operating drawdown target on the
         WOULD-BE positive-edge return stream (src.ruin.solve_rck_lambda);
      4. report the deployed fraction ``lambda * f*`` -- the stake that would be run.
    This is a power/feasibility statement ("what would have had to be true for EV>0",
    EDGE §5.4), NOT a profit claim.
    """
    o = float(o_dnb_ref)
    pd_ = float(p_draw_ref)
    # Invert mu = p_W*(o-1) - p_fav, p_fav = 1 - p_W - p_D -> p_W = (mu + 1 - p_D)/o.
    p_win = (float(hypothetical_edge) + 1.0 - pd_) / o
    p_win = min(max(p_win, 0.0), 1.0 - pd_)  # clamp to the valid simplex slice
    fstar = float(staking.push_kelly_fraction(p_win, pd_, o, clip_negative=True))
    rck = ruin.solve_rck_lambda(
        profit_multiples_if_edge,
        fstar,
        alpha_dd=operating_alpha_dd,
        beta_dd=operating_beta_dd,
    )
    return RequiredEdgeFeasibility(
        hypothetical_edge=float(hypothetical_edge),
        o_dnb_ref=o,
        p_draw_ref=pd_,
        implied_full_kelly_f=fstar,
        rck_lambda=rck.lam_rck,
        operating_alpha_dd=operating_alpha_dd,
        operating_beta_dd=operating_beta_dd,
        deployed_fraction=rck.lam_rck * fstar,
        note=(
            "counterfactual feasibility: the stake fraction that WOULD be run were the "
            f"edge a real +{hypothetical_edge:.4f} per bet at o_dnb={o:.3f}; a "
            "power/feasibility statement, NOT a profit claim (STAKE §7.3, EDGE §5.4)"
        ),
    )


def build_frontier_report(
    md: ruin.MatchdayReturns,
    *,
    rho: float,
    rng: np.random.Generator,
    phi_grid: list[float],
    lambda_grid: list[float],
    alpha_dd_grid: tuple[float, ...],
    beta_dd_grid: tuple[float, ...],
    operating_alpha_dd: float,
    operating_beta_dd: float,
    n_positive_edge_bets: int,
    unit_grid: list[float] | None = None,
    c_grid: list[float] | None = None,
    n_paths: int | None = None,
    mean_block: float = ruin.DEFAULT_MEAN_BLOCK_MATCHDAYS,
    hypothetical_edge: float | None = None,
    o_dnb_ref: float | None = None,
    p_draw_ref: float | None = None,
    dd_quantile_level: str = DEFAULT_DD_QUANTILE_LEVEL,
) -> FrontierReport:
    """Assemble the full per-scheme frontier report + the honest lambda*=0 verdict (task 6).

    Traces all FIVE staking-scheme frontiers -- the multiplicative fixed-fraction, Kelly,
    and fractional-Kelly curves PLUS the additive (cash) flat and level-to-odds curves
    (STAKE §7.3 ordering ``RCK >= fractional-Kelly >= {fixed-fraction, level-to-odds}``;
    plan acceptance line 318 requires all five + RCK on F-07/T-04/T-05). The additive
    schemes use the additive (cash) branch of src.ruin (W_t = W_{t-1} + s_t*r_t); flat
    sweeps its cash unit, level_to_odds its target profit ``c``. The RCK
    ``lambda(alpha_dd, beta_dd)`` grid (src.ruin.brb_drawdown_grid) is swept on the
    empirical per-bet returns + single-bet ``f*``; the all-negative-edge dominance is
    detected, and when ``lambda* = 0`` dominates (no positive-edge bet) AND a hypothetical
    edge is supplied, the COUNTERFACTUAL bankroll/lambda feasibility is attached.

    The single-bet ``f*`` and per-bet profit-multiples for the RCK grid are taken from
    the matchday blocks (concatenated in chronological block order). ``unit_grid`` /
    ``c_grid`` default to the multiplicative-fraction grids (``phi_grid``) when not
    supplied, since the cash schemes' parameters are also fractions of initial bankroll
    on the W_0 = 1 normalisation (a documented sweep position, not an asserted value).
    """
    # The BRB / RCK constraint is a per-MATCHDAY-PERIOD statement (STAKE §6.2 eq. 9; the
    # period is the matchday concurrency unit), so the RCK solve is fed the matchday
    # GROUPING (md.blocks) and the matching per-block single-bet f*, NOT a flattened
    # per-bet array -- otherwise within-matchday concurrency is dropped and the deployed
    # lambda is biased (the load-bearing (alpha_dd, beta_dd) -> lambda mapping). The
    # concatenated arrays are kept only for the positive-edge tally and n_bets reporting.
    r_blocks = [np.asarray(blk, dtype="float64").ravel() for blk in md.blocks]
    fstar_blocks = [
        np.atleast_1d(
            np.asarray(
                staking.push_kelly_fraction(
                    md.pwin_blocks[d], md.pdraw_blocks[d], md.odds_blocks[d], clip_negative=True
                ),
                float,
            )
        )
        for d in range(md.n_matchdays)
    ]
    r_all = np.concatenate(md.blocks) if md.blocks else np.array([], dtype="float64")
    # The de-vigged draw probs, concatenated, are used only as the counterfactual's
    # fallback reference draw rate when no explicit p_draw_ref is supplied (below).
    pd_all = np.concatenate(md.pdraw_blocks) if md.pdraw_blocks else np.array([], dtype="float64")

    # The cash schemes' sweep grids default to the fixed-fraction grid (both are
    # fractions of initial bankroll on the W_0 = 1 normalisation; STAKE §2 "constant % of
    # initial bankroll"), so all five curves trace over comparable sweep positions.
    units = unit_grid if unit_grid is not None else phi_grid
    cs = c_grid if c_grid is not None else phi_grid

    scheme_frontiers: dict[str, SchemeFrontier] = {}
    # All FIVE schemes + the additive cash schemes (plan acceptance line 318): flat /
    # fixed_fraction / level_to_odds / kelly / fractional_kelly. RCK is reported via
    # rck_grid below. The level_to_odds-vs-Kelly tilt contrast (STAKE §7.1, §7.3) is now
    # measured because both curves render on the frontier.
    for scheme, grid in (
        ("flat", units),
        ("fixed_fraction", phi_grid),
        ("level_to_odds", cs),
        ("kelly", None),
        ("fractional_kelly", lambda_grid),
    ):
        scheme_frontiers[scheme] = trace_scheme_frontier(
            md,
            scheme=scheme,
            param_grid=grid,
            rho=rho,
            rng=rng,
            n_paths=n_paths,
            mean_block=mean_block,
            dd_quantile_level=dd_quantile_level,
        )

    rck_grid = ruin.brb_drawdown_grid(
        r_blocks,
        fstar_blocks,
        alpha_dd_grid=alpha_dd_grid,
        beta_dd_grid=beta_dd_grid,
    )

    # lambda*=0 dominates iff the Kelly-family frontier is the cash point only -- i.e. no
    # positive-edge bet exists, so every Kelly/fractional-Kelly point sits on the zero-
    # growth axis (the slice-brief honest-prior verdict).
    lambda_zero = (n_positive_edge_bets == 0) or scheme_frontiers["kelly"].all_below_zero_growth

    required = None
    if lambda_zero and hypothetical_edge is not None and o_dnb_ref is not None:
        # Build the WOULD-BE positive-edge return stream at the reference price: a
        # win/push/loss multiset whose mean equals the hypothetical edge, used to bind
        # the RCK constraint counterfactually. We reuse the empirical push/loss structure
        # but re-weight to the implied win prob at the reference price.
        if p_draw_ref is not None:
            pd_ref = float(p_draw_ref)
        elif pd_all.size:
            pd_ref = float(np.nanmean(pd_all))
        else:
            pd_ref = 0.28  # fallback modern-WC 90-min draw rate (EDGE §4.1) if no panel draw
        o_ref = float(o_dnb_ref)
        p_win_imp = min(max((float(hypothetical_edge) + 1.0 - pd_ref) / o_ref, 0.0), 1.0 - pd_ref)
        b_ref = o_ref - 1.0
        # A representative 3-point return stream {+b, 0, -1} at the implied probabilities.
        # 1000 draws is a DETERMINISTIC representative quantisation (not a Monte-Carlo;
        # the proportions are exact), so the RCK solve sees the hypothetical edge's tail.
        n_q = 1000
        n_win = round(p_win_imp * n_q)
        n_push = round(pd_ref * n_q)
        n_loss = n_q - n_win - n_push
        stream = np.concatenate(
            [np.full(n_win, b_ref), np.zeros(n_push), np.full(max(n_loss, 0), -1.0)]
        )
        required = required_lambda_if_edge_real(
            hypothetical_edge=float(hypothetical_edge),
            o_dnb_ref=o_ref,
            p_draw_ref=pd_ref,
            profit_multiples_if_edge=stream,
            operating_alpha_dd=operating_alpha_dd,
            operating_beta_dd=operating_beta_dd,
        )

    return FrontierReport(
        scheme_frontiers=scheme_frontiers,
        rck_grid=rck_grid,
        lambda_star_zero_dominates=lambda_zero,
        n_positive_edge_bets=int(n_positive_edge_bets),
        n_bets=int(r_all.size),
        required_if_edge_real=required,
        dd_quantile_level=dd_quantile_level,
        note=(
            "growth-drawdown frontier per scheme (F-07/F-08/F-09/T-04/T-05/T-06 data); "
            + (
                "lambda*=0 (do not bet) dominates -- all-negative-edge honest prior; the "
                "required-if-edge-real counterfactual is attached (STAKE §7.3, OQ6)"
                if lambda_zero
                else "positive-edge cells exist; RCK >= fractional-Kelly gap reported"
            )
        ),
    )
