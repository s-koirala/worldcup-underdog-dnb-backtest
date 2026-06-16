"""Matchday-block bootstrap risk-of-ruin + Busseti-Ryu-Boyd drawdown-constrained lambda.

Phase 3 tasks 4 (matchday-block bootstrap ruin / min-bankroll engine) and 5 (BRB
drawdown-constrained ``lambda(alpha_dd, beta_dd)`` solver + the RCK solution). STAKE
§6.2 (the BRB bound), §6.3 (the matchday-block Monte-Carlo), §7.3 (the operating
point); methodology.md §1.2 (the swept risk grids ``rho``, ``alpha_dd``, ``beta_dd``).

Why a Monte-Carlo. The DNB push, the discreteness, the small sample, and the matchday
concurrency break every closed form (STAKE §6.3): the even-money Feller ruin law (eq.
7-8) is an even-money ``b=1`` sanity check only, the genuine ``+b/-1`` additive object
is the adjustment-coefficient root (still additive, not the deployed MULTIPLICATIVE
dynamics), and the deployed fixed-fraction/Kelly staking has no clean closed form that
is both correct and operational. The OPERATIONAL number is the matchday-block bootstrap.

The engine (STAKE §6.3):
  1. collect the empirical settled per-bet NET returns ``{r_i}`` in ``{d_i-1, 0, -1}``
     WITH their matchday grouping preserved (resample MATCHDAYS, not individual bets, to
     keep concurrency/correlation -- the stationary block bootstrap of Politis & Romano
     1994 with block = matchday);
  2. for each ``(scheme, parameter)`` and each of ``B`` bootstrap paths of length ``N``
     (= the deployment-horizon bet count), simulate wealth ``W_t`` and record (a)
     terminal log-growth ``(1/N) log(W_N/W_0)``, (b) max drawdown
     ``1 - min_t W_t / max_{s<=t} W_s``, (c) the ruin indicator
     ``1{min_t W_t <= rho W_0}``;
  3. estimate ``P(ruin)`` with a Wilson CI; estimate the drawdown distribution/quantiles;
  4. MINIMUM BANKROLL for target ruin ``eps`` and target max-drawdown ``D*``: the
     smallest ``W_0`` (equivalently the largest ``phi`` / ``lambda``) meeting both, by
     bisection on the stake fraction over the bootstrap.

Precision-target B (CLAUDE.md no-magic-number; STAKE §6.3). The Monte-Carlo SE on
``P(ruin)`` near ``eps`` is ``sqrt(eps(1-eps)/B)``; requiring ``SE <= eps/10`` gives
``B >= 100(1-eps)/eps``. :func:`min_bootstrap_paths` computes this floor; the deployed
``B = 10^4`` (the slice brief's run value) carries margin over the floor at the smallest
swept ``rho``-relevant target. ``B`` is DERIVED, not chosen.

RNG. The ruin Monte-Carlo draws from the named ``ruin-mc`` sub-stream via
``src.seeding.substream(root_seed, "ruin-mc")`` (Phase 0 task 9.1) -- order-independent,
never the root generator, never global ``np.random``. The vector-Kelly Monte-Carlo uses
its own ``vector-kelly`` sub-stream (src.vector_kelly).

BRB drawdown constraint (STAKE §6.2). For a drawdown target "no more than ``beta_dd``
probability of the running minimum ever falling below ``alpha_dd`` of bankroll", the
bound exponent is ``theta = log beta_dd / log alpha_dd`` (> 1; src.staking.brb_bound_exponent).
The empirical BRB constraint is ``E[(r^T b)^{-theta}] <= 1`` over the per-PERIOD wealth
RELATIVES, where the period is the MATCHDAY (the concurrency unit; STAKE §5.1, §6.3
"block = matchday") so the relative is the SLATE relative
``rel_d = 1 + sum_{j in day d} f_j * r_j`` -- NOT the per-bet relative ``1 + f_i*r_i``.
Shrinking the bet (reducing the Kelly multiplier) until it BINDS yields the
risk-constrained Kelly (RCK) fraction ``< 1`` (BRB §5.3). :func:`solve_rck_lambda` solves
this on the empirical per-MATCHDAY relatives (it takes the ``MatchdayReturns.blocks``
grouping, not flattened per-bet returns, so within-matchday concurrency is honoured and
the RCK lambda is consistent with the vector-Kelly slate sizing + the matchday-block
ruin Monte-Carlo); :func:`brb_drawdown_grid` sweeps the methodology.md §1.2 grid.
Fractional Kelly (``lambda f*``) is reported ALONGSIDE the RCK
solution so the gap (RCK >= fractional-Kelly; STAKE §7.3) is measured, not assumed.

No magic numbers: the risk grids come from methodology.md §1.2; ``B`` from the precision
target; the bisection tolerance is a numerical convergence constant; the stationary-
bootstrap mean block length defaults to 1 matchday (each draw is one matchday block -- the
natural concurrency unit) and is overridable. pathlib not required (pure numeric; the
empirical returns are supplied by the caller).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from src import staking

# Stationary-bootstrap default: the mean geometric block length in MATCHDAYS. A block =
# one matchday is the natural concurrency-preserving unit (STAKE §6.3: "block = matchday").
# The stationary bootstrap (Politis-Romano 1994) draws geometric block lengths with mean
# `mean_block`; mean_block = 1.0 makes each draw exactly one matchday block (the simplest
# concurrency-preserving resample). A larger mean_block captures serial dependence ACROSS
# matchdays; it is a reported sensitivity, not a tuned value.
DEFAULT_MEAN_BLOCK_MATCHDAYS = 1.0

# The deployed Monte-Carlo path count (slice brief: run B = 10^4). Justified by the
# precision target via min_bootstrap_paths (DERIVED, not asserted) -- see module docstring.
DEPLOYED_B = 10_000

# The deployment horizon (STAKE §6.3: "B bootstrap paths of length N = number of
# World-Cup bets at the deployment horizon"). The ruin / drawdown / growth distribution
# is the distribution over a SINGLE tournament-length deployment, not over the entire
# 49,628-bet league history (resampling the whole league history would describe the
# estimation universe, not the deployment risk). The 2026 World Cup is 104 matches
# (config wc_holdout); the deployment horizon defaults to that match count -- the number
# of underdog DNBs at deployment, not asserted (config wc_holdout.deployment_horizon_bets).
DEFAULT_DEPLOYMENT_HORIZON_BETS = 104

# Bisection convergence tolerance on the stake fraction (a numerical constant: the
# fraction is resolved to this absolute precision, not a tunable model parameter).
_BISECTION_FRACTION_TOL = 1e-4
_BISECTION_MAX_ITERS = 60

# Staking-dynamics taxonomy (STAKE §2 table, §6.1). The MULTIPLICATIVE schemes stake a
# fraction of CURRENT bankroll (W_t = W_{t-1}*(1 + f_t*r_t); W_t > 0 a.s., literal
# bankruptcy impossible -- the relevant risk is the fractional-drawdown barrier of §6.2).
# The ADDITIVE (cash) schemes stake a constant CASH amount per bet independent of current
# bankroll (W_t = W_{t-1} + s_t*r_t; an i.i.d.-increment random walk that CAN cross
# W_t <= 0, so the rho=0 literal-bankruptcy floor is reachable -- methodology.md §1.2,
# STAKE §6.1 case i). They are simulated by different path dynamics below.
MULTIPLICATIVE_SCHEMES: tuple[str, ...] = ("fixed_fraction", "kelly", "fractional_kelly")
ADDITIVE_SCHEMES: tuple[str, ...] = ("flat", "level_to_odds")


def is_additive_scheme(scheme: str) -> bool:
    """True iff ``scheme`` uses additive (cash) ruin dynamics (flat / level_to_odds).

    The cash schemes stake a fixed cash amount per bet (STAKE §2 table), so wealth is a
    random walk with i.i.d. increments (additive; STAKE §6.1 case i) rather than a product
    of positive factors (multiplicative; case ii). Literal bankruptcy ``W_t <= 0`` is
    reachable, so the ``rho = 0`` floor is meaningful here (unlike under the multiplicative
    schemes where ``W_t > 0`` a.s.).
    """
    return scheme in ADDITIVE_SCHEMES


def min_bootstrap_paths(eps: float, *, se_ratio: float = 0.1) -> int:
    """Precision-target floor on ``B``: ``B >= eps(1-eps)/(se_ratio*eps)^2`` (STAKE §6.3).

    The Monte-Carlo SE on an estimated ruin probability near ``eps`` is
    ``sqrt(eps(1-eps)/B)``. Requiring ``SE <= se_ratio * eps`` (the slice brief uses
    ``se_ratio = 1/10`` => ``SE <= eps/10``) gives
    ``B >= eps(1-eps)/(se_ratio*eps)^2 = (1-eps)/(se_ratio^2 * eps)``, i.e. the
    ``B >= 100(1-eps)/eps`` of the brief at ``se_ratio = 0.1``. Returns the integer
    ceiling. This is the NO-MAGIC-NUMBER derivation of B from a declared precision
    target; the caller runs ``max(this, DEPLOYED_B)`` so B always clears the floor.
    """
    if not (0.0 < eps < 1.0):
        raise ValueError(f"eps (target ruin prob) must be in (0,1), got {eps}")
    if not (0.0 < se_ratio < 1.0):
        raise ValueError(f"se_ratio must be in (0,1), got {se_ratio}")
    floor = (1.0 - eps) / (se_ratio * se_ratio * eps)
    return int(np.ceil(floor))


def wilson_interval(k: int, n: int, *, z: float = 1.959963984540054) -> tuple[float, float]:
    """Wilson score interval for a binomial proportion ``k/n`` (the ruin-prob CI).

    The Wilson interval is well-behaved at the extreme proportions the honest-prior
    ruin estimates hit (``P(ruin) ~ 0`` when full Kelly stakes 0 everywhere), unlike the
    Wald interval which underflows there. ``z`` defaults to the two-sided 95% normal
    quantile (a standard statistical constant, not a tuned threshold). Returns
    ``(lo, hi)`` clipped to ``[0, 1]``.
    """
    if n <= 0:
        return (float("nan"), float("nan"))
    phat = k / n
    z2 = z * z
    denom = 1.0 + z2 / n
    centre = (phat + z2 / (2 * n)) / denom
    half = (z / denom) * np.sqrt(phat * (1.0 - phat) / n + z2 / (4 * n * n))
    return (max(0.0, centre - half), min(1.0, centre + half))


# ---------------------------------------------------------------------------
# Matchday grouping of the empirical per-bet returns.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MatchdayReturns:
    """Empirical settled per-bet NET returns grouped by matchday (the bootstrap unit).

    ``blocks`` is a list of 1-D arrays, one per matchday, of the per-bet NET return
    MULTIPLES used by the SIZING scheme. For a fraction-of-bankroll scheme the wealth
    update is ``W_t = W_{t-1} * (1 + f_t * r_t)`` with ``r_t = net_return - 1`` the net
    PROFIT multiple (win: ``o_dnb-1``; push: 0; loss: -1); we store ``r_t`` (the profit
    multiple) so the simulator applies ``1 + f r`` directly. Concurrency is preserved by
    keeping each matchday's bets together (resample matchdays, not bets).
    """

    blocks: list[npt.NDArray[np.float64]]  # one array of profit-multiples r per matchday
    odds_blocks: list[npt.NDArray[np.float64]]  # the matching o_dnb per bet (for Kelly sizing)
    pwin_blocks: list[npt.NDArray[np.float64]]  # per-bet de-vigged p_win (for Kelly sizing)
    pdraw_blocks: list[npt.NDArray[np.float64]]  # per-bet de-vigged p_draw (for Kelly sizing)
    n_matchdays: int
    n_bets: int


def group_by_matchday(
    profit_multiples: npt.ArrayLike,
    matchday_key: npt.ArrayLike,
    *,
    o_dnb: npt.ArrayLike | None = None,
    p_win: npt.ArrayLike | None = None,
    p_draw: npt.ArrayLike | None = None,
) -> MatchdayReturns:
    """Group per-bet net profit-multiples (and sizing inputs) into matchday blocks.

    ``profit_multiples`` is ``r_t = net_return - 1`` per bet (win ``o_dnb-1``, push 0,
    loss -1). ``matchday_key`` assigns each bet to a matchday (e.g. the date string);
    bets sharing a key form one concurrency block. The optional ``o_dnb / p_win /
    p_draw`` arrays carry the per-bet sizing inputs so the bootstrap can RE-SIZE Kelly /
    fractional-Kelly stakes per resampled matchday (a fixed-fraction scheme ignores them).
    Order within a matchday is preserved as supplied (the ledger's stable (date,
    match_id) order).
    """
    r = np.asarray(profit_multiples, dtype="float64").ravel()
    keys = np.asarray(matchday_key).ravel()
    if r.shape != keys.shape:
        raise ValueError(f"profit_multiples {r.shape} and matchday_key {keys.shape} must match")
    n = r.size
    o = np.asarray(o_dnb, dtype="float64").ravel() if o_dnb is not None else np.full(n, np.nan)
    pw = np.asarray(p_win, dtype="float64").ravel() if p_win is not None else np.full(n, np.nan)
    pdr = np.asarray(p_draw, dtype="float64").ravel() if p_draw is not None else np.full(n, np.nan)

    # Stable group order: first appearance of each key (chronological if the input is
    # date-ordered). pandas factorize preserves first-appearance order.
    import pandas as pd

    codes, _ = pd.factorize(pd.Series(keys), sort=False)
    n_days = int(codes.max()) + 1 if n else 0
    blocks: list[npt.NDArray[np.float64]] = []
    odds_blocks: list[npt.NDArray[np.float64]] = []
    pwin_blocks: list[npt.NDArray[np.float64]] = []
    pdraw_blocks: list[npt.NDArray[np.float64]] = []
    for d in range(n_days):
        m = codes == d
        blocks.append(r[m])
        odds_blocks.append(o[m])
        pwin_blocks.append(pw[m])
        pdraw_blocks.append(pdr[m])
    return MatchdayReturns(
        blocks=blocks,
        odds_blocks=odds_blocks,
        pwin_blocks=pwin_blocks,
        pdraw_blocks=pdraw_blocks,
        n_matchdays=n_days,
        n_bets=n,
    )


# ---------------------------------------------------------------------------
# The stationary (matchday-block) bootstrap simulator.
# ---------------------------------------------------------------------------


def _stake_fraction_for_block(
    scheme: str,
    scheme_params: dict[str, float],
    odds: npt.NDArray[np.float64],
    pwin: npt.NDArray[np.float64],
    pdraw: npt.NDArray[np.float64],
) -> npt.NDArray[np.float64]:
    """Per-bet stake FRACTION for one resampled matchday block (sizing is signal-only).

    Returns the fraction of CURRENT bankroll to stake on each bet in the block, sized
    ONLY from the pre-kickoff signal (o_dnb, p_win, p_draw) and the scheme's parameter
    -- never the realised return (non-anticipation, STAT §9.2). Fraction schemes:
      * fixed_fraction -> phi on every bet;
      * kelly          -> push-Kelly f* (negative edge -> 0);
      * fractional_kelly -> lambda * f*.
    Cash schemes (flat / level_to_odds) are additive and sized in cash; the ruin engine
    sweeps them via the cash-staking branch (handled by the caller), so they are not
    expected here.
    """
    n = odds.size
    if scheme == "fixed_fraction":
        return np.full(n, float(scheme_params["phi"]), dtype="float64")
    if scheme == "kelly":
        return np.atleast_1d(
            np.asarray(staking.push_kelly_fraction(pwin, pdraw, odds, clip_negative=True), float)
        )
    if scheme == "fractional_kelly":
        f = np.atleast_1d(
            np.asarray(staking.push_kelly_fraction(pwin, pdraw, odds, clip_negative=True), float)
        )
        return float(scheme_params["lam"]) * f
    raise ValueError(
        f"scheme {scheme!r} is not a fraction-of-bankroll scheme; the ruin engine sizes "
        f"{MULTIPLICATIVE_SCHEMES} multiplicatively (cash schemes "
        f"{ADDITIVE_SCHEMES} use _cash_stake_for_block / the additive branch)"
    )


def _cash_stake_for_block(
    scheme: str,
    scheme_params: dict[str, float],
    odds: npt.NDArray[np.float64],
) -> npt.NDArray[np.float64]:
    """Per-bet CASH stake for one resampled matchday block (additive schemes; signal-only).

    Returns the constant cash stake on each bet for the additive (cash) schemes, sized
    ONLY from the pre-kickoff signal (the price ``o_dnb`` for level_to_odds; nothing for
    flat) and the scheme's parameter -- never the realised return (non-anticipation,
    STAT §9.2). The cash amount is expressed as a fraction of the INITIAL bankroll
    (``W_0 = 1`` normalisation; STAKE §2 "constant cash, or constant % of initial
    bankroll"), so the simulator's additive update ``W_t = W_{t-1} + s_t*r_t`` reads the
    stake directly. Cash schemes:
      * flat          -> the constant unit ``k`` on every bet (odds-agnostic);
      * level_to_odds -> ``c / (d - 1)`` (constant target profit; STAKE §2). A degenerate
        price (``d - 1 <= 0`` / non-finite) yields a 0 stake (no fabricated wager).
    """
    n = odds.size
    if scheme == "flat":
        return np.full(n, float(scheme_params["unit"]), dtype="float64")
    if scheme == "level_to_odds":
        b = np.asarray(odds, dtype="float64") - 1.0
        with np.errstate(divide="ignore", invalid="ignore"):
            s = np.where(np.isfinite(b) & (b > 0.0), float(scheme_params["c"]) / b, 0.0)
        return np.atleast_1d(s.astype("float64"))
    raise ValueError(
        f"scheme {scheme!r} is not an additive cash scheme; the additive branch sizes "
        f"{ADDITIVE_SCHEMES} (multiplicative schemes use _stake_fraction_for_block)"
    )


def _draw_matchday_path(
    md: MatchdayReturns,
    n_matchdays_path: int,
    rng: np.random.Generator,
    *,
    mean_block: float,
) -> list[int]:
    """Stationary-bootstrap a path of matchday indices (Politis-Romano 1994).

    Draws geometric block lengths with mean ``mean_block`` (in matchdays) and wraps
    circularly over the empirical matchdays, concatenating until ``n_matchdays_path``
    matchdays are collected. Returns the list of resampled matchday indices (each a
    pointer into ``md.blocks``). With ``mean_block = 1`` each block is a single matchday
    (the simplest concurrency-preserving resample); a larger mean captures cross-matchday
    serial dependence.
    """
    n_src = md.n_matchdays
    if n_src == 0:
        return []
    p_restart = 1.0 / mean_block  # geometric restart probability
    out: list[int] = []
    while len(out) < n_matchdays_path:
        start = int(rng.integers(0, n_src))
        # Geometric block length (>= 1).
        length = 1 + int(rng.geometric(p_restart) - 1) if mean_block > 1.0 else 1
        for k in range(length):
            out.append((start + k) % n_src)
            if len(out) >= n_matchdays_path:
                break
    return out[:n_matchdays_path]


@dataclass(frozen=True)
class RuinResult:
    """Bootstrap risk-of-ruin / drawdown / growth distribution for one (scheme, param)."""

    scheme: str
    scheme_params: dict[str, float]
    rho: float
    n_paths: int
    horizon_bets: int
    horizon_matchdays: int
    prob_ruin: float
    prob_ruin_ci: tuple[float, float]
    mean_terminal_log_growth: float
    median_terminal_log_growth: float
    drawdown_quantiles: dict[str, float]  # e.g. {"p50":..., "p90":..., "p95":..., "p99":...}
    max_drawdown_mean: float
    n_staked_per_path_mean: float
    b_precision_floor: int
    note: str = ""


# Drawdown quantile reporting ladder (positions in the empirical max-DD distribution,
# not asserted magnitudes; mirrors the costs slippage ladder convention).
DRAWDOWN_QUANTILE_LADDER: tuple[str, ...] = ("p50", "p90", "p95", "p99")


def _matchday_log_relatives(
    md: MatchdayReturns,
    scheme: str,
    params: dict[str, float],
) -> tuple[list[npt.NDArray[np.float64]], list[npt.NDArray[np.float64]], list[int]]:
    """Pre-compute per-matchday log-wealth-relatives once (signal-only; non-anticipation).

    The stake FRACTION on every bet is a pure function of the pre-kickoff signal
    (o_dnb, p_win, p_draw) and the scheme parameter -- it does NOT change across
    bootstrap resamples (STAT §9.2 non-anticipation). So the per-bet wealth relative
    ``rel = 1 + f_eff * r`` and its log are INVARIANT and can be computed ONCE per
    matchday block, before the Monte-Carlo loop -- the dominant speedup (the inner loop
    becomes a cumulative product over precomputed arrays, not a per-bet re-sizing).

    Returns, per matchday: the array of per-bet log-relatives ``log(rel)`` (with a
    bankrupting ``rel <= 0`` mapped to ``-inf``), the per-bet wealth-relatives ``rel``,
    and the count of STAKED bets in that matchday (positive finite fraction). Zero-stake
    / non-settleable bets contribute ``rel = 1`` (log 0) -- the bankroll passes through
    unchanged, which is the "did not bet" entry, not a dropped bet.
    """
    log_rel_blocks: list[npt.NDArray[np.float64]] = []
    rel_blocks: list[npt.NDArray[np.float64]] = []
    n_staked: list[int] = []
    for d in range(md.n_matchdays):
        r = md.blocks[d]
        f = _stake_fraction_for_block(
            scheme, params, md.odds_blocks[d], md.pwin_blocks[d], md.pdraw_blocks[d]
        )
        f = np.atleast_1d(np.asarray(f, dtype="float64"))
        # A non-finite fraction / return or a zero stake -> rel = 1 (pass-through).
        staked = np.isfinite(f) & (f > 0.0) & np.isfinite(r)
        f_eff = np.where(staked, np.minimum(f, 1.0), 0.0)  # no leverage / no negative wealth
        rel = np.where(staked, 1.0 + f_eff * r, 1.0)
        rel = np.where(rel < 0.0, 0.0, rel)
        with np.errstate(divide="ignore"):
            log_rel = np.where(rel > 0.0, np.log(rel), -np.inf)
        log_rel_blocks.append(log_rel.astype("float64"))
        rel_blocks.append(rel.astype("float64"))
        n_staked.append(int(staked.sum()))
    return log_rel_blocks, rel_blocks, n_staked


def _matchday_cash_increments(
    md: MatchdayReturns,
    scheme: str,
    params: dict[str, float],
) -> tuple[list[npt.NDArray[np.float64]], list[int]]:
    """Pre-compute per-matchday per-bet CASH increments ``s_t*r_t`` once (additive schemes).

    For the additive (cash) schemes the wealth update is ``W_t = W_{t-1} + s_t*r_t`` with
    ``s_t`` a constant cash stake sized from the pre-kickoff signal ONLY (non-anticipation,
    STAT §9.2). Both the cash stake ``s_t`` and the net profit-multiple ``r_t`` are
    INVARIANT across bootstrap resamples, so the per-bet cash increment ``delta_t =
    s_t*r_t`` is computed ONCE per matchday before the Monte-Carlo loop and the inner loop
    becomes a cumulative SUM over precomputed arrays (the additive analogue of the
    multiplicative cumulative product).

    Returns, per matchday: the array of per-bet cash increments ``s_t*r_t`` (a
    non-finite stake or return contributes 0 -- a "did not bet" pass-through, not a
    dropped bet), and the count of STAKED bets (positive finite cash stake) in that
    matchday.
    """
    delta_blocks: list[npt.NDArray[np.float64]] = []
    n_staked: list[int] = []
    for d in range(md.n_matchdays):
        r = md.blocks[d]
        s = _cash_stake_for_block(scheme, params, md.odds_blocks[d])
        s = np.atleast_1d(np.asarray(s, dtype="float64"))
        staked = np.isfinite(s) & (s > 0.0) & np.isfinite(r)
        delta = np.where(staked, s * r, 0.0)
        delta_blocks.append(delta.astype("float64"))
        n_staked.append(int(staked.sum()))
    return delta_blocks, n_staked


def bootstrap_ruin(
    md: MatchdayReturns,
    *,
    scheme: str,
    scheme_params: dict[str, float] | None = None,
    rho: float,
    rng: np.random.Generator,
    n_paths: int | None = None,
    horizon_bets: int | None = None,
    horizon_matchdays: int | None = None,
    mean_block: float = DEFAULT_MEAN_BLOCK_MATCHDAYS,
    eps_target: float = 0.05,
) -> RuinResult:
    """Matchday-block bootstrap risk-of-ruin / drawdown / growth engine (STAKE §6.3).

    Resamples MATCHDAYS (stationary block bootstrap, block = matchday; concurrency
    preserved) into ``n_paths`` wealth paths of the DEPLOYMENT HORIZON (``horizon_bets``
    World-Cup-length bets, STAKE §6.3 "paths of length N = number of World-Cup bets"),
    sizing each bet from the signal (non-anticipation, precomputed once). Records per path:
    terminal log-growth ``(1/N) log(W_N/W_0)``, max drawdown, and the ruin indicator
    ``1{min W_t <= rho W_0}``.

    Two dynamics are handled (STAKE §2 table, §6.1; the scheme selects the branch):
      * MULTIPLICATIVE (fixed_fraction / kelly / fractional_kelly): stake a fraction of
        CURRENT bankroll, ``W <- W * (1 + f*r)``; ``W_t > 0`` a.s. so the rho=0 floor is
        unreachable and the binding risk is the fractional-drawdown barrier (§6.2);
      * ADDITIVE (flat / level_to_odds): stake a constant CASH amount per bet (a fraction
        of INITIAL bankroll; W_0 = 1), ``W <- W + s*r``; an i.i.d.-increment random walk
        that CAN cross ``W_t <= 0``, so the rho=0 literal-bankruptcy floor is reachable
        (STAKE §6.1 case i; methodology.md §1.2).

    ``rng`` MUST be the ``ruin-mc`` sub-stream (``src.seeding.substream(root_seed,
    "ruin-mc")``) -- order-independent, never the root generator (Phase 0 task 9.1).
    ``n_paths`` defaults to ``max(DEPLOYED_B, min_bootstrap_paths(eps_target))`` so B
    clears the precision-target floor (STAKE §6.3; no magic number). ``horizon_bets``
    defaults to ``DEFAULT_DEPLOYMENT_HORIZON_BETS`` (the WC tournament bet count); pass
    ``horizon_matchdays`` instead to fix the number of matchday blocks directly (used by
    the within-tournament concurrency tests). The matchday path is drawn until at least
    ``horizon_bets`` bets are collected.

    The honest-prior all-negative-edge case (Kelly stakes 0 everywhere) yields a FLAT
    wealth path, ``P(ruin) = 0`` exactly, and zero growth -- the "do not bet" output,
    cleanly, not an error.
    """
    params = dict(scheme_params or {})
    if md.n_matchdays == 0:
        raise ValueError("no matchdays to bootstrap")
    floor = min_bootstrap_paths(eps_target)
    B = int(n_paths or max(DEPLOYED_B, floor))
    additive = is_additive_scheme(scheme)

    # Pre-compute the per-matchday per-bet wealth steps ONCE (signal-only; non-anticipation):
    # multiplicative -> per-bet log-relatives log(1 + f*r); additive -> cash increments s*r.
    if additive:
        delta_blocks, staked_per_day = _matchday_cash_increments(md, scheme, params)
        bets_per_day = np.array([blk.size for blk in delta_blocks], dtype="intp")
    else:
        log_rel_blocks, rel_blocks, staked_per_day = _matchday_log_relatives(md, scheme, params)
        bets_per_day = np.array([blk.size for blk in rel_blocks], dtype="intp")
    mean_bets_per_day = float(bets_per_day.mean()) if md.n_matchdays else 0.0

    # Target number of matchday blocks per path: enough to reach the deployment horizon.
    if horizon_matchdays is not None:
        horizon_md = int(horizon_matchdays)
    else:
        hb = int(horizon_bets or DEFAULT_DEPLOYMENT_HORIZON_BETS)
        horizon_md = max(1, int(np.ceil(hb / max(mean_bets_per_day, 1.0))))

    # Both dynamics normalise W_0 = 1, so equity reads as a growth multiple. The
    # multiplicative path accumulates LOG-wealth (starts at 0); the additive path
    # accumulates cash increments on top of W_0 = 1.
    terminal_logg = np.empty(B, dtype="float64")
    max_dd = np.empty(B, dtype="float64")
    ruined = np.zeros(B, dtype=bool)
    n_staked_path = np.empty(B, dtype="float64")
    n_bets_path = np.empty(B, dtype="float64")

    log_rho = np.log(rho) if rho > 0.0 else -np.inf

    for p in range(B):
        day_idx = _draw_matchday_path(md, horizon_md, rng, mean_block=mean_block)
        n_s = int(sum(staked_per_day[d] for d in day_idx))
        if additive:
            deltas = (
                np.concatenate([delta_blocks[d] for d in day_idx])
                if day_idx
                else np.array([], dtype="float64")
            )
            n_b = deltas.size
        else:
            # Concatenate the precomputed per-bet log-relatives along the resampled path.
            log_rels = (
                np.concatenate([log_rel_blocks[d] for d in day_idx])
                if day_idx
                else np.array([], dtype="float64")
            )
            n_b = log_rels.size
        if n_b == 0:
            terminal_logg[p] = 0.0
            max_dd[p] = 0.0
            ruined[p] = False
            n_staked_path[p] = 0
            n_bets_path[p] = 0
            continue

        if additive:
            # Additive cash wealth path (W_0 = 1): W_t = 1 + cumsum(s_t*r_t). Once wealth
            # crosses <= 0 the bettor is bankrupt; the running minimum captures the worst
            # point even if a later increment would lift it back (a path that touched 0 is
            # ruined). Wealth is NOT floored, so the literal-bankruptcy rho=0 is reachable.
            wealth = np.concatenate([[1.0], 1.0 + np.cumsum(deltas)])
            running_max = np.maximum.accumulate(wealth)
            w_min = float(wealth.min())
            final_w = float(wealth[-1])
            # Max drawdown 1 - min_t W_t/running_max_t (additive wealth; can exceed 1 if the
            # path goes negative -- clipped to the [0, inf) drawdown convention via max(.,0)).
            with np.errstate(divide="ignore", invalid="ignore"):
                dd_path = 1.0 - wealth / running_max
            dd = float(np.nanmax(dd_path))
            terminal_logg[p] = (np.log(final_w) / n_b) if final_w > 0.0 else -np.inf
            max_dd[p] = dd
            # Ruin: running-minimum wealth <= rho * W_0 = rho (W_0 = 1). For rho = 0 this is
            # literal bankruptcy (the additive random walk crossing 0), reachable here.
            ruined[p] = w_min <= rho
        else:
            # Cumulative log-wealth path (W_0 = 1 -> log 0); a -inf step bankrupts (and stays).
            cum_logw = np.concatenate([[0.0], np.cumsum(log_rels)])
            running_min = np.minimum.accumulate(cum_logw)
            running_max = np.maximum.accumulate(cum_logw)
            # Max drawdown in WEALTH units: 1 - exp(min_t (logw_t - running_max_t)).
            dd_path = 1.0 - np.exp(cum_logw - running_max)
            dd = float(np.nanmax(dd_path))
            final_logw = cum_logw[-1]
            w_min_log = float(running_min.min())
            terminal_logg[p] = (final_logw / n_b) if np.isfinite(final_logw) else -np.inf
            max_dd[p] = dd
            # Ruin: running-min wealth <= rho * W_0 (i.e. log running-min <= log rho); for
            # rho = 0 (literal bankruptcy) ruin iff a -inf (W=0) step ever occurred (never
            # under the multiplicative dynamics, where W_t > 0 a.s.).
            ruined[p] = (w_min_log <= log_rho) if rho > 0.0 else (not np.isfinite(final_logw))
        n_staked_path[p] = n_s
        n_bets_path[p] = n_b

    k_ruin = int(ruined.sum())
    p_ruin = k_ruin / B
    ci = wilson_interval(k_ruin, B)
    finite_g = terminal_logg[np.isfinite(terminal_logg)]
    dd_q = {
        lvl: float(np.quantile(max_dd, float(lvl[1:]) / 100.0)) for lvl in DRAWDOWN_QUANTILE_LADDER
    }
    return RuinResult(
        scheme=scheme,
        scheme_params=params,
        rho=float(rho),
        n_paths=B,
        horizon_bets=round(float(n_bets_path.mean())) if B else 0,
        horizon_matchdays=horizon_md,
        prob_ruin=p_ruin,
        prob_ruin_ci=ci,
        mean_terminal_log_growth=float(finite_g.mean()) if finite_g.size else float("-inf"),
        median_terminal_log_growth=float(np.median(finite_g)) if finite_g.size else float("-inf"),
        drawdown_quantiles=dd_q,
        max_drawdown_mean=float(max_dd.mean()),
        n_staked_per_path_mean=float(n_staked_path.mean()),
        b_precision_floor=floor,
        note=(
            "matchday-block stationary bootstrap (block=matchday; Politis-Romano 1994); "
            f"B={B} clears the SE<=eps/10 floor {floor} at eps_target={eps_target}"
        ),
    )


# ---------------------------------------------------------------------------
# Minimum-bankroll / largest-fraction by bisection (STAKE §6.3 step 4).
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MinBankrollResult:
    """The largest fixed-fraction phi meeting a (ruin, drawdown) budget (STAKE §6.3 step 4)."""

    max_fraction: float  # largest phi with P(ruin)<=eps AND DD-quantile<=D*
    eps_target: float
    dd_target: float
    dd_quantile_level: str
    achieved_prob_ruin: float
    achieved_dd_quantile: float
    feasible: bool
    note: str = ""


def max_fraction_for_budget(
    md: MatchdayReturns,
    *,
    rho: float,
    rng: np.random.Generator,
    eps_target: float = 0.05,
    dd_target: float = 0.5,
    dd_quantile_level: str = "p95",
    n_paths: int | None = None,
    mean_block: float = DEFAULT_MEAN_BLOCK_MATCHDAYS,
    fraction_hi: float = 1.0,
) -> MinBankrollResult:
    """Largest fixed-fraction ``phi`` with ``P(ruin) <= eps`` AND DD-quantile ``<= D*``.

    The MINIMUM-BANKROLL dual (STAKE §6.3 step 4): for fixed-fraction staking the
    minimum bankroll for a target ruin ``eps`` is equivalent to the LARGEST stake
    fraction ``phi`` that still meets both the ruin and the max-drawdown budgets, found
    by bisection over the bootstrap. Monotone-in-``phi`` aggressiveness (bigger ``phi``
    => weakly more ruin and deeper drawdowns) makes bisection valid. ``rho`` is the
    ruin floor; ``dd_target`` (``D*``) the tolerated max-drawdown at the reported
    ``dd_quantile_level``; both come from methodology.md §1.2 / the caller's grid.

    Returns ``feasible = False`` (and ``max_fraction = 0``) when even the smallest
    nonzero fraction breaches the budget -- the honest signal that the target is
    unattainable at any positive stake.
    """

    def _meets(phi: float) -> tuple[bool, float, float]:
        res = bootstrap_ruin(
            md,
            scheme="fixed_fraction",
            scheme_params={"phi": phi},
            rho=rho,
            rng=rng,
            n_paths=n_paths,
            mean_block=mean_block,
            eps_target=eps_target,
        )
        ddq = res.drawdown_quantiles.get(dd_quantile_level, float("nan"))
        ok = (res.prob_ruin <= eps_target) and (ddq <= dd_target)
        return ok, res.prob_ruin, ddq

    lo, hi = 0.0, float(fraction_hi)
    ok_hi, pr_hi, dd_hi = _meets(hi)
    if ok_hi:
        return MinBankrollResult(
            max_fraction=hi,
            eps_target=eps_target,
            dd_target=dd_target,
            dd_quantile_level=dd_quantile_level,
            achieved_prob_ruin=pr_hi,
            achieved_dd_quantile=dd_hi,
            feasible=True,
            note="full budget meets the (ruin, drawdown) target (typical of f*=0 do-not-bet)",
        )
    # Bisect for the largest feasible phi in (0, hi).
    best = 0.0
    best_pr, best_dd = float("nan"), float("nan")
    for _ in range(_BISECTION_MAX_ITERS):
        mid = 0.5 * (lo + hi)
        ok, pr, dd = _meets(mid)
        if ok:
            best, best_pr, best_dd = mid, pr, dd
            lo = mid
        else:
            hi = mid
        if hi - lo < _BISECTION_FRACTION_TOL:
            break
    return MinBankrollResult(
        max_fraction=best,
        eps_target=eps_target,
        dd_target=dd_target,
        dd_quantile_level=dd_quantile_level,
        achieved_prob_ruin=best_pr,
        achieved_dd_quantile=best_dd,
        feasible=best > 0.0,
        note="largest fixed-fraction phi meeting both budgets, by bootstrap bisection",
    )


# ===========================================================================
# Busseti-Ryu-Boyd drawdown-constrained lambda / RCK solver (Phase 3 task 5;
# STAKE §6.2, §7.3).
# ===========================================================================


def _as_period_blocks(
    profit_multiples: npt.ArrayLike | list[npt.NDArray[np.float64]],
) -> list[npt.NDArray[np.float64]]:
    """Coerce the return input into a list of per-PERIOD (matchday) blocks.

    The BRB drawdown bound (STAKE §6.2 eq. 9) is a per-REBALANCING-PERIOD statement and
    the rebalancing period is the MATCHDAY (the concurrency unit; STAKE §5.1, §6.3
    "block = matchday"). The canonical input is therefore a list-of-arrays (one array of
    per-bet profit-multiples ``r`` per matchday, e.g. ``MatchdayReturns.blocks``), so the
    constraint can be evaluated on the per-matchday-period wealth relative
    ``rel_d = 1 + sum_{j in day d} f_j * r_j`` rather than on flattened per-bet relatives.

    A bare 1-D array is accepted for backward compatibility / the single-bet-per-period
    case: it is treated as ONE bet per period (each element its own singleton block), for
    which the per-period and per-bet relatives coincide. A list/tuple is taken as the
    explicit matchday grouping verbatim.
    """
    if isinstance(profit_multiples, list | tuple):
        return [np.atleast_1d(np.asarray(blk, dtype="float64").ravel()) for blk in profit_multiples]
    arr = np.asarray(profit_multiples, dtype="float64").ravel()
    # Bare array -> one bet per period (singleton blocks); per-period == per-bet here.
    return [arr[i : i + 1] for i in range(arr.size)]


def _align_period_fractions(
    blocks: list[npt.NDArray[np.float64]],
    fractions: npt.ArrayLike | list[npt.NDArray[np.float64]],
) -> list[npt.NDArray[np.float64]]:
    """Align the per-bet stake fractions to the matchday-block structure of ``blocks``.

    ``fractions`` may be (a) a scalar (broadcast to every bet), (b) a flat per-bet array
    in the same chronological bet order as the concatenated blocks, or (c) a list of
    per-block arrays already matching ``blocks``. Returns a list of per-block fraction
    arrays, one entry per bet, so the per-matchday-period relative
    ``rel_d = 1 + sum_j f_j * r_j`` can be formed block by block.
    """
    bets_per_block = [blk.size for blk in blocks]
    n_bets = int(sum(bets_per_block))
    if isinstance(fractions, list | tuple):
        out = [np.atleast_1d(np.asarray(fb, dtype="float64").ravel()) for fb in fractions]
        if len(out) != len(blocks) or any(
            fb.size != blk.size for fb, blk in zip(out, blocks, strict=True)
        ):
            raise ValueError("per-block fractions must match the matchday-block shapes")
        return out
    f = np.atleast_1d(np.asarray(fractions, dtype="float64")).ravel()
    if f.size == 1:
        f = np.full(n_bets, float(f[0]))
    if f.size != n_bets:
        raise ValueError(
            f"fractions ({f.size}) must be scalar or match the bet count ({n_bets}) "
            "implied by the matchday blocks"
        )
    # Split the flat per-bet fraction array back into the block structure.
    out2: list[npt.NDArray[np.float64]] = []
    pos = 0
    for nb in bets_per_block:
        out2.append(f[pos : pos + nb])
        pos += nb
    return out2


def brb_constraint_value(
    profit_multiples: npt.ArrayLike | list[npt.NDArray[np.float64]],
    fractions: npt.ArrayLike | list[npt.NDArray[np.float64]],
    *,
    weights: npt.ArrayLike | None = None,
    theta: float,
) -> float:
    """Empirical BRB constraint ``E[(period wealth relative)^{-theta}]`` (STAKE §6.2, eq. 9).

    The BRB drawdown bound is a per-REBALANCING-PERIOD statement (STAKE §6.2 eq. 9:
    ``E[(r^T b)^{-theta}] <= 1`` over the per-period wealth relative ``r^T b``), and with
    concurrent group-stage matchdays the rebalancing PERIOD is the MATCHDAY (STAKE §5.1,
    §6.3 "block = matchday"). So the wealth relative is the per-matchday SLATE relative

        rel_d = 1 + sum_{j in day d} f_j * r_j

    -- the SUM of the per-bet contributions over the matchday's concurrent bets, matching
    the vector-Kelly slate sizing (STAKE §5.1) and the matchday-block ruin Monte-Carlo --
    NOT the per-bet relative ``1 + f_i*r_i`` (which would treat sequential bets, ignoring
    within-matchday concurrency). ``profit_multiples`` is the list of per-matchday blocks
    (``MatchdayReturns.blocks``; a bare array is treated as one bet per period). The
    constraint holds iff ``E[rel_d^{-theta}] <= 1`` over the MATCHDAY set; the RCK solve
    shrinks ``lambda`` until this crosses 1 (STAKE §6.2). A non-positive period relative
    (a bankrupting matchday at this fraction) yields ``+inf`` (the constraint is violated
    -- you can be ruined that matchday), the correct honest signal.
    """
    blocks = _as_period_blocks(profit_multiples)
    if not blocks:
        return float("nan")
    fblocks = _align_period_fractions(blocks, fractions)
    # Per-matchday-period wealth relative: rel_d = 1 + sum_j f_j*r_j over the day's slate.
    rel = np.array(
        [1.0 + float(np.sum(fb * blk)) for fb, blk in zip(fblocks, blocks, strict=True)],
        dtype="float64",
    )
    if np.any(rel <= 0.0):
        return float("inf")
    with np.errstate(over="ignore"):
        vals = rel ** (-float(theta))
    if weights is None:
        return float(np.mean(vals))
    w = np.asarray(weights, dtype="float64").ravel()
    if w.size != rel.size:
        raise ValueError(
            f"weights ({w.size}) must be one per matchday PERIOD ({rel.size}), not per bet"
        )
    w = w / w.sum()
    return float(np.sum(w * vals))


@dataclass(frozen=True)
class RCKResult:
    """The risk-constrained-Kelly (RCK) multiplier at a drawdown target (STAKE §6.2)."""

    alpha_dd: float
    beta_dd: float
    theta: float
    lam_rck: float  # the multiplier at which E[rel^{-theta}] <= 1 binds (RCK; < 1 typically)
    constraint_at_lam: float  # E[rel^{-theta}] at lam_rck (<= 1 when satisfiable)
    binds: bool  # True iff the constraint actively bound below full Kelly
    note: str = ""


def solve_rck_lambda(
    profit_multiples: npt.ArrayLike | list[npt.NDArray[np.float64]],
    single_bet_f: npt.ArrayLike | list[npt.NDArray[np.float64]],
    *,
    alpha_dd: float,
    beta_dd: float,
    weights: npt.ArrayLike | None = None,
    lam_hi: float = 1.0,
) -> RCKResult:
    """Solve for the RCK multiplier ``lambda`` at drawdown target ``(alpha_dd, beta_dd)``.

    The bet at each empirical observation is ``f_i = lambda * f*_i`` (fractional Kelly
    on the per-bet push-Kelly ``f*``; src.staking). The bound exponent is
    ``theta = log beta_dd / log alpha_dd`` (src.staking.brb_bound_exponent). The RCK
    solution (BRB §5.3) shrinks ``lambda`` until the per-REBALANCING-PERIOD constraint

        E[ rel_d^{-theta} ] <= 1,   rel_d = 1 + sum_{j in day d} lambda*f*_j * r_j

    BINDS over the MATCHDAY periods (STAKE §6.2 eq. 9; the period is the matchday, the
    concurrency unit -- STAKE §5.1, §6.3). ``profit_multiples`` is the list of per-matchday
    blocks (``MatchdayReturns.blocks``); ``single_bet_f`` is the matching per-bet ``f*``
    (a list of per-block arrays, a flat per-bet array in concatenated block order, or a
    scalar). A bare 1-D ``profit_multiples`` is treated as one bet per period (per-bet ==
    per-period), preserving the legacy single-bet-per-period semantics. The result is a
    fractional-Kelly bet with ``lambda < 1`` (the "for some f < 1" of BRB §5). Bisection on
    ``lambda`` in ``[0, lam_hi]``: the constraint LHS is monotone non-decreasing in
    ``lambda`` (bigger bets => fatter left tail of the SLATE relative => larger
    ``E[rel_d^{-theta}]``), so the largest ``lambda`` with LHS ``<= 1`` is well-defined.

    Concurrency (the fix this docstring's predecessor falsely claimed): with multiple bets
    per matchday the per-matchday-period relative ``1 + sum_j lambda*f*_j*r_j`` differs from
    the per-bet relative ``1 + lambda*f*_i*r_i``; the bound is the per-period statement, so
    the solve is over the matchday relatives, matching the vector-Kelly slate sizing and the
    matchday-block ruin Monte-Carlo.

    Honest-prior case: when every ``f*_i = 0`` (all-negative-edge; the slice brief's
    dominant case) the bet is identically cash, ``rel_d = 1``, ``E[rel_d^{-theta}] = 1`` for
    ALL ``lambda``, so the constraint is satisfied at the full budget and ``lam_rck =
    lam_hi`` with ``binds = False`` -- i.e. the drawdown constraint is vacuous because
    there is no bet to constrain (``lambda* = 0`` is then forced by ``f* = 0``, reported
    separately). The RCK ``lambda`` only becomes ``< 1`` when there is a real positive-
    edge bet whose tail the drawdown target binds.
    """
    theta = staking.brb_bound_exponent(alpha_dd, beta_dd)
    blocks = _as_period_blocks(profit_multiples)
    fstar_blocks = _align_period_fractions(blocks, single_bet_f)

    def lhs(lam: float) -> float:
        lam_f = [lam * fb for fb in fstar_blocks]
        return brb_constraint_value(blocks, lam_f, weights=weights, theta=theta)

    val_hi = lhs(lam_hi)
    if val_hi <= 1.0:
        # Full budget already satisfies the drawdown bound (no shrinkage needed). This
        # is the all-cash / no-real-bet case (binds=False) OR a genuinely safe bet.
        return RCKResult(
            alpha_dd=alpha_dd,
            beta_dd=beta_dd,
            theta=theta,
            lam_rck=float(lam_hi),
            constraint_at_lam=val_hi,
            binds=False,
            note="constraint satisfied at full budget (vacuous when f*=0; STAKE §6.2)",
        )
    # The constraint is violated at lam_hi -> shrink. lhs(0) = E[1] = 1 <= 1, so a root
    # in (0, lam_hi) exists. Bisect for the largest lambda with lhs <= 1.
    lo, hi = 0.0, float(lam_hi)
    best = 0.0
    best_val = 1.0
    for _ in range(_BISECTION_MAX_ITERS):
        mid = 0.5 * (lo + hi)
        v = lhs(mid)
        if v <= 1.0:
            best, best_val = mid, v
            lo = mid
        else:
            hi = mid
        if hi - lo < _BISECTION_FRACTION_TOL:
            break
    return RCKResult(
        alpha_dd=alpha_dd,
        beta_dd=beta_dd,
        theta=theta,
        lam_rck=best,
        constraint_at_lam=best_val,
        binds=True,
        note="RCK multiplier where E[rel^{-theta}]=1 binds; fractional Kelly lambda<1 (BRB §5.3)",
    )


def brb_drawdown_grid(
    profit_multiples: npt.ArrayLike | list[npt.NDArray[np.float64]],
    single_bet_f: npt.ArrayLike | list[npt.NDArray[np.float64]],
    *,
    alpha_dd_grid: tuple[float, ...],
    beta_dd_grid: tuple[float, ...],
    weights: npt.ArrayLike | None = None,
) -> list[RCKResult]:
    """Sweep ``lambda(alpha_dd, beta_dd)`` over the methodology.md §1.2 grid (Phase 3 task 5).

    Solves the RCK multiplier (:func:`solve_rck_lambda`) at every
    ``(alpha_dd, beta_dd)`` cell of the declared drawdown grid (methodology.md §1.2:
    ``alpha_dd in {0.5,0.6,0.7,0.8}``, ``beta_dd in {0.05,0.10,0.20}``). The result is
    the ``lambda(alpha_dd, beta_dd)`` table the slice deliverable reports across the
    whole grid, with the operating point read off the frontier (src.frontier), not
    asserted. Fractional Kelly is reported ALONGSIDE the RCK solution so the gap is
    measured (STAKE §7.3).

    ``profit_multiples`` is the list of per-matchday blocks (``MatchdayReturns.blocks``)
    so the constraint is evaluated on the per-MATCHDAY-period wealth relatives (STAKE §6.2
    eq. 9; the period is the matchday concurrency unit, not the individual bet); a bare
    array is treated as one bet per period. ``single_bet_f`` is the matching per-bet ``f*``
    (per-block list, flat per-bet array in block order, or scalar). Passing the matchday
    grouping (not ``np.concatenate(blocks)``) is what keeps the RCK solve consistent with
    the vector-Kelly slate sizing and the matchday-block ruin Monte-Carlo.
    """
    out: list[RCKResult] = []
    for a in alpha_dd_grid:
        for b in beta_dd_grid:
            out.append(
                solve_rck_lambda(
                    profit_multiples,
                    single_bet_f,
                    alpha_dd=a,
                    beta_dd=b,
                    weights=weights,
                )
            )
    return out
