"""Closed-form EV / three-point variance / push-Kelly for the DNB bet (CALC §5-§7).

Phase 2 (plan task 4; CALC §5 EV, §6 variance, §7 push-Kelly). This module owns the
analytic closed forms for the three-outcome (win / push / loss) Draw-No-Bet lottery.
The full staking SCHEMES (flat / fixed-fraction / level-to-odds / fractional Kelly,
the ledger, the vector-Kelly program, the risk-of-ruin Monte-Carlo) are Phase 3
(plan §"Phase 3"); this file provides only the per-bet closed-form helpers those
schemes -- and the Phase-4 inference -- consume. The metrics-facing EV / variance
helpers are re-exported through :mod:`src.metrics`.

Notation (CALC §5-§7), per unit stake on the underdog DNB:

    p_W      true probability the underdog WINS in 90 minutes  -> net return b
    p_D      true probability of a 90-minute DRAW (push)        -> net return 0
    p_fav    true probability the FAVOURITE wins (= 1 - p_W - p_D) -> net return -1
    o_dnb    the DNB decimal odds (CALC §3: o_DNB = W*(D-1)/D)
    b        = o_dnb - 1, the net win profit per unit
    mu       = EV(R) the per-bet mean net return

Closed forms implemented (verbatim from CALC):

    EV       mu  = p_W*(o_dnb - 1) - p_fav        = p_W*o_dnb - (1 - p_D)   (§5)
             the push contributes 0; positive-EV iff p_W*o_dnb > 1 - p_D.
    Var      Var_DNB = p_W*b^2 + p_fav - mu^2     with b = o_dnb - 1         (§6.1)
    push-Kelly
             f* = (p~_A*b - p~_H) / (b*(p~_A + p~_H))                        (§7.1)
             on the NO-PUSH-renormalised probs p~_A = p_W/(1-p_D),
             p~_H = p_fav/(1-p_D); negative-edge -> f* = 0 (no short side).
    fair-price identity
             Var_winbet(fair) - Var_DNB(fair) = p_D*p_fav/p_W               (§6.2)
             (documented helper; the always-signed statement, NOT a general bound).

The de-vig method that produces (p_W, p_D, p_fav) is frozen a priori (Shin primary;
plan task 5/6, CALC §4.6) and is NOT selected here -- these helpers take the
probabilities as inputs and are de-vig-agnostic.

No magic numbers (every constant is a probability/odds input or the structural 0/1
of the no-short branch); pure numeric (no pathlib needed); vectorised over numpy
arrays and python scalars alike.
"""

from __future__ import annotations

import numpy as np
import numpy.typing as npt

# ---------------------------------------------------------------------------
# Internal helpers (shared by EV / variance / Kelly so the three never diverge).
# ---------------------------------------------------------------------------


def _favourite_prob(p_win: npt.ArrayLike, p_draw: npt.ArrayLike) -> npt.NDArray[np.float64]:
    """Favourite-win probability ``p_fav = 1 - p_W - p_D`` (CALC §6.1).

    The three outcomes partition the sample space, so the favourite (loss) mass is
    the complement of win + push. Kept as one helper so EV, variance, and Kelly all
    use an identical ``p_fav`` and cannot drift.
    """
    pw = np.asarray(p_win, dtype="float64")
    pd_ = np.asarray(p_draw, dtype="float64")
    return 1.0 - pw - pd_


# ---------------------------------------------------------------------------
# §5  Expected value.
# ---------------------------------------------------------------------------


def expected_value(
    p_win: npt.ArrayLike, p_draw: npt.ArrayLike, o_dnb: npt.ArrayLike
) -> npt.NDArray[np.float64] | float:
    """Per-unit EV of the underdog DNB bet ``mu = p_W*(o_dnb-1) - p_fav`` (CALC §5).

    Equivalently ``p_W*o_dnb - (1 - p_D)`` (the push contributes 0; the favourite
    state contributes ``-p_fav``). Positive iff ``p_W*o_dnb > 1 - p_D`` -- the
    §5 positive-EV condition, which is also exactly where the §7 Kelly ``f*`` turns
    positive.

    Parameters
    ----------
    p_win, p_draw : float | ndarray
        The TRUE underdog-win and draw probabilities (de-vigged; CALC §4). The
        favourite-loss probability is ``1 - p_win - p_draw``.
    o_dnb : float | ndarray
        DNB decimal odds (``src.pricing.synthetic_dnb`` or a quoted AH-0 price).

    Returns
    -------
    float | ndarray
        ``mu``. Scalar in -> scalar out.
    """
    pw = np.asarray(p_win, dtype="float64")
    o = np.asarray(o_dnb, dtype="float64")
    p_fav = _favourite_prob(p_win, p_draw)
    b = o - 1.0
    mu = pw * b - p_fav  # == pw*o - (1 - p_draw)
    return float(mu) if np.ndim(mu) == 0 else mu


# ---------------------------------------------------------------------------
# §6  Three-point return variance.
# ---------------------------------------------------------------------------


def per_bet_variance(
    p_win: npt.ArrayLike, p_draw: npt.ArrayLike, o_dnb: npt.ArrayLike
) -> npt.NDArray[np.float64] | float:
    """Three-point per-bet variance ``Var_DNB = p_W*b^2 + p_fav - mu^2`` (CALC §6.1).

    With ``b = o_dnb - 1`` and ``p_fav = 1 - p_W - p_D``. Derivation: the second
    moment is ``E[R^2] = p_W*b^2 + p_D*0 + p_fav*1`` (push contributes 0, loss
    contributes ``(-1)^2``), and ``Var = E[R^2] - mu^2`` with ``mu`` the §5 EV.

    This is the STRATEGY variance. It is distinct from the fair-WIN-bet benchmark
    ``Var = o - 1`` (CALC §6.2, :func:`fair_win_bet_variance`), which holds only at
    a fair price / same-view comparison -- ``Var_DNB`` is NOT universally below
    ``o - 1`` at arbitrarily mispriced odds (CALC §6.2 counterexample).
    """
    pw = np.asarray(p_win, dtype="float64")
    o = np.asarray(o_dnb, dtype="float64")
    p_fav = _favourite_prob(p_win, p_draw)
    b = o - 1.0
    mu = pw * b - p_fav
    var = pw * b**2 + p_fav - mu**2
    return float(var) if np.ndim(var) == 0 else var


def fair_win_bet_variance(o: npt.ArrayLike) -> npt.NDArray[np.float64] | float:
    """Variance of a FAIR straight win bet at decimal ``o``: ``Var = o - 1`` (CALC §6.2).

    For a fair win bet (win prob ``p = 1/o`` so ``mu = 0``, no push):
    ``Var = (1/o)(o-1)^2 + (1 - 1/o) = (o-1)``. This is the project's stated
    benchmark identity and the unit-test target -- a *fair-bet* benchmark, NOT a
    generic upper bound on the DNB variance.
    """
    oo = np.asarray(o, dtype="float64")
    out = oo - 1.0
    return float(out) if np.ndim(out) == 0 else out


def fair_price_variance_reduction(
    p_win: npt.ArrayLike, p_draw: npt.ArrayLike
) -> npt.NDArray[np.float64] | float:
    """Fair-price variance gap ``Var_winbet(fair) - Var_DNB(fair) = p_D*p_fav/p_W`` (CALC §6.2).

    The clean, ALWAYS-signed identity (resolved CALC Open Question 5): at the DNB's
    own fair price ``o_DNB = (1 - p_D)/p_W`` (so ``mu = 0``), the difference between
    the same-odds fair win bet's variance and the DNB variance collapses to
    ``p_D * p_fav / p_W`` with ``p_fav = 1 - p_W - p_D``. Non-negative for any valid
    simplex point with ``p_W > 0``; strictly positive iff ``p_D > 0`` and
    ``p_fav > 0``. This is the documented helper the variance unit test asserts
    against direct evaluation of ``fair_win_bet_variance(o_fair) -
    per_bet_variance(p_W, p_D, o_fair)``.

    NOTE: this is the FAIR-PRICE statement only. At arbitrary mispriced odds the
    win-bet-minus-DNB variance gap is not given by this expression and is not even
    universally signed (CALC §6.2, §8.2).
    """
    pw = np.asarray(p_win, dtype="float64")
    pd_ = np.asarray(p_draw, dtype="float64")
    p_fav = 1.0 - pw - pd_
    out = pd_ * p_fav / pw
    return float(out) if np.ndim(out) == 0 else out


def fair_dnb_odds(p_win: npt.ArrayLike, p_draw: npt.ArrayLike) -> npt.NDArray[np.float64] | float:
    """Fair (zero-EV) DNB odds ``o_DNB^fair = (1 - p_D)/p_W = 1/q_W`` (CALC §5, §6.2).

    The price at which the §5 EV is exactly zero; used by the fair-price variance
    identity helper and the worked-example tests. ``q_W = p_W/(1 - p_D)`` is the
    conditional no-draw win probability.
    """
    pw = np.asarray(p_win, dtype="float64")
    pd_ = np.asarray(p_draw, dtype="float64")
    out = (1.0 - pd_) / pw
    return float(out) if np.ndim(out) == 0 else out


# ---------------------------------------------------------------------------
# §7  Push-Kelly stake.
# ---------------------------------------------------------------------------


def push_kelly_fraction(
    p_win: npt.ArrayLike,
    p_draw: npt.ArrayLike,
    o_dnb: npt.ArrayLike,
    *,
    clip_negative: bool = True,
) -> npt.NDArray[np.float64] | float:
    """Push-Kelly fraction ``f*`` for the win/push/loss DNB lottery (CALC §7.1; STAKE §3.2).

    The Kelly stake is the binary Kelly evaluated on the NO-PUSH-renormalised
    probabilities ``p~_A = p_W/(1-p_D)`` (the conditional win prob, the underdog =
    "A" side in the STAKE notation) and ``p~_H = p_fav/(1-p_D)`` (conditional
    favourite-win / loss prob):

        f* = (p~_A * b - p~_H) / (b * (p~_A + p~_H)),   b = o_dnb - 1.

    Because ``p~_A + p~_H = 1`` after renormalisation, this is algebraically the
    same closed form as the un-renormalised CALC §7.1 expression
    ``f* = (p_W*b - p_fav) / (b*(p_W + p_fav))`` with ``p_W + p_fav = 1 - p_D``
    (the ``1/(1-p_D)`` cancels top and bottom); both are implemented via the
    no-push-renormalised probs as the slice brief specifies.

    Negative-edge branch (default ``clip_negative=True``): a DNB market has no short
    side, so when ``f* < 0`` (i.e. ``p~_A * d_A <= 1`` <=> ``p_W*o_dnb <= 1-p_D``,
    the §5 negative-EV region) the stake is **0**, not a negative (short) position.
    Set ``clip_negative=False`` to return the raw signed FOC root (for the
    self-check / d->0 degeneration test, where the un-clipped value must match the
    textbook two-outcome Kelly including its sign).

    Parameters
    ----------
    p_win, p_draw : float | ndarray
        TRUE underdog-win / draw probabilities (de-vigged; CALC §4).
    o_dnb : float | ndarray
        DNB decimal odds.
    clip_negative : bool, default True
        Apply the negative-edge -> 0 branch (no short side). The production stake
        path uses the default; the degeneration self-check uses ``False``.

    Returns
    -------
    float | ndarray
        ``f*`` in ``[0, 1)`` when clipped (a fraction of bankroll), or the raw
        signed FOC root when ``clip_negative=False``. Scalar in -> scalar out.
    """
    pw = np.asarray(p_win, dtype="float64")
    pd_ = np.asarray(p_draw, dtype="float64")
    o = np.asarray(o_dnb, dtype="float64")
    b = o - 1.0

    no_push = 1.0 - pd_  # = p_W + p_fav, the conditional renormaliser
    with np.errstate(divide="ignore", invalid="ignore"):
        p_a = pw / no_push  # p~_A  (conditional underdog-win prob)
        p_h = _favourite_prob(p_win, p_draw) / no_push  # p~_H (conditional loss prob)
        f = (p_a * b - p_h) / (b * (p_a + p_h))

    if clip_negative:
        # No short side in a DNB market: negative edge -> stake 0 (CALC §7.2).
        f = np.where(f > 0.0, f, 0.0)
    out = np.asarray(f, dtype="float64")
    return float(out) if out.ndim == 0 else out


def two_outcome_kelly(p_win: npt.ArrayLike, o: npt.ArrayLike) -> npt.NDArray[np.float64] | float:
    """Textbook two-outcome Kelly ``f* = (p*o - 1)/(o - 1) = edge/odds`` (CALC §7.2).

    The no-draw limit of :func:`push_kelly_fraction` (``p_D -> 0``): the brief's
    self-check asserts ``push_kelly_fraction(p_win, p_draw=d, o, clip_negative=False)
    -> two_outcome_kelly(p_win, o)`` as ``d -> 0``. Provided as the reference
    closed form for that degeneration test; NOT clipped (the test checks the raw
    signed value, including the negative-edge sign).
    """
    p = np.asarray(p_win, dtype="float64")
    oo = np.asarray(o, dtype="float64")
    out = (p * oo - 1.0) / (oo - 1.0)
    return float(out) if np.ndim(out) == 0 else out


# ===========================================================================
# Phase 3 task 1 -- the FIVE staking SCHEMES as stake-sizing functions of
# (o_dnb, p, bankroll_before) ONLY (STAKE §2, §7.1; ARCH §2.2 staking contract;
# STAT §9.2 non-anticipation property).
# ===========================================================================
#
# NON-ANTICIPATION (load-bearing, the property test in test_staking_schemes.py
# enforces it): every stake below is a pure function of the pre-kickoff signal
# tuple ``(o_dnb, p_win, p_draw, bankroll_before)`` and the scheme's free
# parameter. NONE of them reads the realised result (settle_disposition,
# settle_net_profit, FTR, ...). Permuting the *future* outcomes therefore can
# never change any stake -- the formal statement of "a stake is a function of
# (o_dnb, p, bankroll_before) only" (slice brief; STAT §9.2).
#
# Each function returns the CASH stake ``s_t`` for one bet given the bankroll
# *before* that bet (``bankroll_before``), so the ledger (src.ledger) can apply
# ``W_t = W_{t-1} + s_t * r_t`` with ``r_t`` the settled net-return multiple
# (settlement.py). flat takes a unit ``k``; fixed_fraction a fraction ``phi``;
# level_to_odds a target-profit ``c``; kelly the push-Kelly ``f*``;
# fractional_kelly ``lambda * f*``. The fraction-of-current-bankroll schemes
# (fixed_fraction / kelly / fractional_kelly) multiply by ``bankroll_before``;
# flat and level_to_odds are scale-free cash stakes that do not (STAKE §2 table).

# The canonical scheme set, byte-identical to config/baseline.yaml staking.schemes
# and config/multipletest_family.yaml headline_family.dimensions.staking_scheme
# (a four-vs-five mismatch corrupts the K denominator -- plan task 4.1).
STAKING_SCHEMES: tuple[str, ...] = (
    "flat",
    "fixed_fraction",
    "level_to_odds",
    "kelly",
    "fractional_kelly",
)


def stake_flat(
    o_dnb: npt.ArrayLike,
    p_win: npt.ArrayLike,
    p_draw: npt.ArrayLike,
    bankroll_before: npt.ArrayLike,
    *,
    unit: float,
) -> npt.NDArray[np.float64] | float:
    """Flat / level stake ``s_t = unit`` (STAKE §2: constant cash unit).

    The level-stake comparator: a constant cash unit per bet, independent of odds,
    edge, or bankroll. Additive (non-compounding) dynamics. Takes the full
    ``(o_dnb, p_win, p_draw, bankroll_before)`` signal tuple for a UNIFORM scheme
    signature (the ledger calls every scheme the same way) but uses none of it --
    which is exactly the "sizing varies with odds? No" row of the STAKE §2 table.

    ``unit`` is the level cash stake ``k``; a config tunable (no magic number).
    Broadcast to the shape of ``o_dnb`` so the vectorised ledger path matches the
    scalar path.
    """
    shape_like = np.asarray(o_dnb, dtype="float64")
    out = np.full_like(shape_like, float(unit), dtype="float64")
    return float(out) if out.ndim == 0 else out


def stake_fixed_fraction(
    o_dnb: npt.ArrayLike,
    p_win: npt.ArrayLike,
    p_draw: npt.ArrayLike,
    bankroll_before: npt.ArrayLike,
    *,
    phi: float,
) -> npt.NDArray[np.float64] | float:
    """Fixed-fraction stake ``s_t = phi * bankroll_before`` (STAKE §2, §7.1).

    The canonical scale-free "flat" comparator: a constant fraction ``phi`` of the
    CURRENT bankroll, independent of odds/edge (STAKE §7.1 "constant fraction
    regardless of price/edge"). Multiplicative dynamics -- directly comparable to
    Kelly (also a fraction of current bankroll). ``phi`` is swept on the
    walk-forward grid (config staking.phi_grid; no magic number).
    """
    w = np.asarray(bankroll_before, dtype="float64")
    out = float(phi) * w
    return float(out) if np.ndim(out) == 0 else out


def stake_level_to_odds(
    o_dnb: npt.ArrayLike,
    p_win: npt.ArrayLike,
    p_draw: npt.ArrayLike,
    bankroll_before: npt.ArrayLike,
    *,
    c: float,
) -> npt.NDArray[np.float64] | float:
    """Level-stake-to-odds ``s_t = c / (d - 1)`` with ``d = o_dnb`` (STAKE §2, §7.1).

    Equalises the *target profit* ``c`` per bet: stake ``proportional to 1/(d-1)``,
    so MORE on shorter prices / LESS on longer prices -- the opposite tilt to Kelly
    when edge is concentrated in longshots (STAKE §2). Scale-free cash stake (does
    NOT scale with bankroll). ``c`` is the swept target-profit grid
    (config staking.c_grid). ``b = d - 1`` is the net win odds; a non-positive or
    null ``b`` (degenerate price) yields NaN, never a fabricated stake.
    """
    b = np.asarray(o_dnb, dtype="float64") - 1.0
    with np.errstate(divide="ignore", invalid="ignore"):
        out = np.where(np.isfinite(b) & (b > 0.0), float(c) / b, np.nan)
    return float(out) if out.ndim == 0 else out


def stake_kelly(
    o_dnb: npt.ArrayLike,
    p_win: npt.ArrayLike,
    p_draw: npt.ArrayLike,
    bankroll_before: npt.ArrayLike,
) -> npt.NDArray[np.float64] | float:
    """Full push-Kelly stake ``s_t = f*(p, o_dnb) * bankroll_before`` (STAKE §3.2, §7.1).

    Reuses the Phase-2 :func:`push_kelly_fraction` (the clipped, no-short ``f*``):
    the stake is the Kelly fraction of the CURRENT bankroll. Endogenous,
    edge-proportional sizing -- tilts toward high-edge bets (STAKE §7.1). The
    negative-edge branch is inherited from ``push_kelly_fraction``: ``f* = 0`` ->
    stake 0 (no short side; the honest-prior all-negative-edge case, slice brief /
    STAKE §7.3). No free parameter (uses ``p, o`` directly).
    """
    f = push_kelly_fraction(p_win, p_draw, o_dnb, clip_negative=True)
    w = np.asarray(bankroll_before, dtype="float64")
    out = np.asarray(f, dtype="float64") * w
    return float(out) if out.ndim == 0 else out


def stake_fractional_kelly(
    o_dnb: npt.ArrayLike,
    p_win: npt.ArrayLike,
    p_draw: npt.ArrayLike,
    bankroll_before: npt.ArrayLike,
    *,
    lam: float,
) -> npt.NDArray[np.float64] | float:
    """Fractional-Kelly stake ``s_t = lam * f*(p, o_dnb) * bankroll_before`` (STAKE §4, §7.1).

    The deployable rule: a fractional multiplier ``lam in (0, 1]`` on the full
    push-Kelly stake. ``lam`` is DATA-DERIVED (Bayesian shrinkage
    ``lam ~ 1/(1+CV^2)``, :func:`shrinkage_lambda`, and/or the binding BRB
    drawdown constraint over the methodology.md §1.2 ``(alpha_dd, beta_dd)`` grid,
    :func:`brb_bound_exponent` + the drawdown-constrained solve in src.ruin) --
    NEVER hand-set; half-Kelly is the PRIOR, not the answer (STAKE §4.2-§4.3).
    Negative edge -> ``f* = 0`` -> stake 0 (inherited from push_kelly_fraction).
    """
    f = push_kelly_fraction(p_win, p_draw, o_dnb, clip_negative=True)
    w = np.asarray(bankroll_before, dtype="float64")
    out = float(lam) * np.asarray(f, dtype="float64") * w
    return float(out) if out.ndim == 0 else out


# Dispatch table: scheme name -> (sizing function, set of required keyword params).
# The required-param set lets src.ledger validate that the per-scheme parameter is
# present (and a single source of truth for which schemes carry a free parameter).
_SCHEME_DISPATCH = {
    "flat": (stake_flat, ("unit",)),
    "fixed_fraction": (stake_fixed_fraction, ("phi",)),
    "level_to_odds": (stake_level_to_odds, ("c",)),
    "kelly": (stake_kelly, ()),
    "fractional_kelly": (stake_fractional_kelly, ("lam",)),
}


def stake(
    scheme: str,
    o_dnb: npt.ArrayLike,
    p_win: npt.ArrayLike,
    p_draw: npt.ArrayLike,
    bankroll_before: npt.ArrayLike,
    **params: float,
) -> npt.NDArray[np.float64] | float:
    """Dispatch to one of the five staking schemes by name (STAKE §2, §7.1).

    The single entry point the ledger calls. ``scheme`` in
    :data:`STAKING_SCHEMES`; ``params`` carries the scheme's free parameter
    (``unit`` / ``phi`` / ``c`` / ``lam``; ``kelly`` takes none). Raises on an
    unknown scheme or a missing/extra parameter rather than silently mis-sizing.

    Non-anticipation: the call signature contains ONLY the pre-kickoff signal
    ``(o_dnb, p_win, p_draw, bankroll_before)`` and the parameter -- there is no
    channel through which a result could enter a stake.
    """
    if scheme not in _SCHEME_DISPATCH:
        raise ValueError(f"unknown staking scheme {scheme!r}; expected one of {STAKING_SCHEMES}")
    fn, required = _SCHEME_DISPATCH[scheme]
    missing = set(required) - set(params)
    extra = set(params) - set(required)
    if missing:
        raise ValueError(
            f"staking scheme {scheme!r} missing required parameter(s): {sorted(missing)}"
        )
    if extra:
        raise ValueError(f"staking scheme {scheme!r} got unexpected parameter(s): {sorted(extra)}")
    return fn(o_dnb, p_win, p_draw, bankroll_before, **params)


# ===========================================================================
# Phase 3 task 5 -- data-derived fractional-Kelly multiplier lambda (STAKE §4.2,
# §6.2). lambda is NOT hand-set: it is either the Bayesian-shrinkage
# 1/(1+CV^2) certainty-equivalent (estimation-error route, §4.2) or the multiplier
# at which the Busseti-Ryu-Boyd drawdown constraint binds (risk-control route,
# §6.2 -- the binding solve lives in src.ruin, which consumes brb_bound_exponent).
# ===========================================================================


def shrinkage_lambda(
    edge: npt.ArrayLike, edge_sd: npt.ArrayLike
) -> npt.NDArray[np.float64] | float:
    """Bayesian-shrinkage fractional-Kelly multiplier ``lam = 1/(1 + CV^2)`` (STAKE §4.2).

    Under a Gaussian posterior on the edge, the certainty-equivalent optimal Kelly
    fraction shrinks toward 0 as the coefficient of variation
    ``CV = edge_sd/edge`` of the *estimated edge* rises (MacLean-Ziemba-Blazenko
    1992; STAKE §4.2): ``lam = 1/(1 + (edge_sd/edge)^2) = edge^2/(edge^2 +
    edge_sd^2)``. A unit signal-to-noise ratio (``CV = 1``) gives ``lam = 0.5``
    (half-Kelly as a *consequence*, not an assertion -- STAKE §4.2-§4.3). This
    makes ``lam`` a DATA-DERIVED quantity (the edge and its sampling SD come from
    the calibration/bootstrap), the slice brief's "data-derived lambda" route.

    ``edge`` here is the per-bet expected return ``mu`` (or a strategy-level mean
    edge); a non-positive edge yields ``lam = 0`` (no positive-edge stake to
    fractionate -- consistent with the f*=0 no-bet branch). ``edge_sd >= 0``.
    """
    e = np.asarray(edge, dtype="float64")
    s = np.asarray(edge_sd, dtype="float64")
    with np.errstate(divide="ignore", invalid="ignore"):
        lam = np.where(e > 0.0, e * e / (e * e + s * s), 0.0)
    out = np.asarray(lam, dtype="float64")
    return float(out) if out.ndim == 0 else out


def brb_bound_exponent(alpha_dd: float, beta_dd: float) -> float:
    """Busseti-Ryu-Boyd drawdown-bound exponent ``theta = log(beta_dd)/log(alpha_dd)`` (STAKE §6.2).

    For the drawdown target "no more than ``beta_dd`` probability of the running-
    minimum wealth ever falling below ``alpha_dd`` of bankroll", BRB (2016) eq. (9)
    gives the bound exponent ``theta = log beta_dd / log alpha_dd`` (their notation;
    ``> 1`` for any nontrivial target). The fractional multiplier ``lam < 1`` is
    then the value at which the constraint ``E[(r^T b)^{-theta}] <= 1`` BINDS (the
    binding solve is the empirical-bootstrap bisection in src.ruin; this helper
    supplies the exponent it solves at). ``theta`` is the risk-aversion STRICTNESS,
    NOT the bet size (the STAKE §6.2 notation guard: do not read theta as lambda).

    Worked (STAKE §6.2): ``alpha_dd=0.5, beta_dd=0.1 -> theta = log0.1/log0.5 =
    3.3219``. Requires ``alpha_dd, beta_dd in (0, 1)``.
    """
    if not (0.0 < alpha_dd < 1.0):
        raise ValueError(f"alpha_dd (drawdown floor) must be in (0,1), got {alpha_dd}")
    if not (0.0 < beta_dd < 1.0):
        raise ValueError(f"beta_dd (breach probability) must be in (0,1), got {beta_dd}")
    return float(np.log(beta_dd) / np.log(alpha_dd))
