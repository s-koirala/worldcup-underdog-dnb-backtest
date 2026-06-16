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
