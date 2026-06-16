"""Pricing + de-vig core: synthetic DNB, implied probabilities, fair-probability recovery.

Phase 2 task 1 + task 7 (plan §C Phase 2; CALC §3, §4). This module owns the
load-bearing odds/DNB identity layer the rest of the backtest stands on:

  * ``synthetic_dnb(W, D)``        -- the no-arbitrage synthetic DNB price on the
    underdog side, ``o_DNB = W·(D-1)/D = W·(1 - r_D)`` (CALC §3.1-§3.3). The single
    source of truth for the identity that ``src/selection.py`` / ``src/settlement.py``
    consume, RECONCILED bit-for-bit with ``src/assemble.py`` (see below).
  * ``implied_probs(H, D, A)``     -- raw reciprocal (vigged) probabilities + the
    overround ``M = Π - 1`` (CALC §1, §4).
  * ``devig(H, D, A, method)``     -- the de-vig dispatcher returning fair
    ``(p_H, p_D, p_A)`` summing to 1, for method ∈ {basic, shin, power} (CALC §4).
  * ``conditional_win_prob(p_W, p_D)`` -- the no-draw conditional ``q_W = p_W/(1 - p_D)``
    (CALC §3.4, §5), the two-way DNB view formed from the THREE-WAY fair probs.
  * ``shin_z`` / ``shin_z_two_way`` -- the Shin (1992/1993) insider-fraction root and
    its exact two-way Jullien-Salanié closed form (estimator-verification gate, task 7).
  * ``margin_wedge`` / ``dnb_price`` -- the synthetic-vs-quoted AH-0 margin gap
    ``M_1X2 - M_AH`` and the prefer-quoted-then-synthetic price selector (CALC §3.5).

The synthetic-DNB identity (CALC §3.1-§3.3): ``o_DNB = W·(D-1)/D``, where ``W`` is the
underdog win price (the higher of the two win prices) and ``D`` is the draw price.
Hedging ``1/D`` on the draw and ``(D-1)/D`` on the win returns the unit stake on a
90-minute draw (a push) and ``o_DNB`` on an underdog win.

RECONCILIATION WITH ``src/assemble.py`` (load-bearing, per the slice brief).
``src.ingest.attach_reference_price`` ALREADY derives
``o_dnb_underdog = under_price * (refC_D - 1) / refC_D`` with the underdog price chosen
by the tie-break ``refC_A >= refC_H -> away`` (away wins exact ties). ``synthetic_dnb``
here reproduces that arithmetic *exactly* (same operation order ``W * (D - 1.0) / D``,
same divide-guard, same NaN propagation), so importing it into ``assemble.py`` leaves
``data/processed/matches.parquet`` byte-identical -- the content SHA is unchanged
(re-verified by re-running the assemble/validate stages and pinned by a unit test).

De-vig method policy (FROZEN a priori, not searched). Shin is the primary; power and
basic are pre-registered sensitivity branches (design.md §3; CALC §4.6). The method is
NOT a per-fold-selected hyperparameter, so it does not enter the multiple-testing
family ``K``.

Shin-on-the-right-book (CALC §4.2 applicability note, the load-bearing correctness
constraint). Shin requires an OVER-round book (Π > 1). For the synthetic DNB the
correct route is to run Shin on the full THREE-WAY 1X2 book and form
``q_W = p_W/(1 - p_D)`` from the resulting fair probabilities -- NOT on the under-round
draw-dropped residual (``r_W + r_fav < 1``), which makes the n=2 closed form return an
invalid ``z < 0``. The quoted two-way AH-0/DNB book has its own margin > 0 and is the
only place the n=2 form is used (``shin_z_two_way``).

ARCH §2.2 pricing contract. ``devig`` enforces ``0 < p_i`` and ``Σ p = 1`` (so in
particular ``0 < p_D`` and ``p_W + p_D ≤ 1``); ``synthetic_dnb`` enforces ``D > 0``.

No magic numbers; pathlib not required (pure numeric); pure NumPy/SciPy, no global RNG.
Vectorized (numpy) and scalar inputs both supported for ``synthetic_dnb``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, overload

import numpy as np
import numpy.typing as npt
from scipy.optimize import brentq

DevigMethod = Literal["basic", "shin", "power"]
DEVIG_METHODS: tuple[str, ...] = ("basic", "shin", "power")

# Numerical tolerance for the de-vig root solvers and the simplex/contract checks.
# This is a SOLVER convergence/feasibility tolerance (a numerical-analysis constant,
# not a model hyperparameter or a tuned threshold), so it is exempt from the
# no-magic-number rule: it governs floating-point feasibility of the pricing contract
# (Σ p = 1 to within rounding), never a decision. Set at ~1e-12, comfortably above f64
# epsilon (~2.2e-16) and below any economically meaningful probability gap.
_SOLVER_TOL = 1e-12
# Upper bracket for the Shin z root: z ∈ [0, 1); approach 1 from below without hitting
# the (1 - z) singularity. Numerical bracket bound, not a tunable.
_Z_UPPER = 1.0 - 1e-12


@overload
def synthetic_dnb(win_price: float, draw_price: float) -> float: ...
@overload
def synthetic_dnb(
    win_price: npt.NDArray[np.floating], draw_price: npt.NDArray[np.floating]
) -> npt.NDArray[np.floating]: ...


def synthetic_dnb(win_price, draw_price):  # type: ignore[no-untyped-def]
    """Synthetic DNB decimal odds ``o_DNB = W * (D - 1) / D`` (CALC §3.1-§3.3).

    Parameters
    ----------
    win_price : float | ndarray
        The decimal win price ``W`` of the side being backed (for the strategy this is
        the **underdog** win price = the higher of ``refC_H``/``refC_A``; see
        ``src.selection.underdog_win_price``). Must be > 1 for a meaningful price.
    draw_price : float | ndarray
        The decimal draw price ``D`` (``refC_D``). Must be > 0; a non-positive or NaN
        ``D`` propagates as NaN (no fabricated price), mirroring
        ``src.ingest.attach_reference_price``'s divide-guard.

    Returns
    -------
    float | ndarray
        ``W * (D - 1) / D``. NaN where ``D`` is null/non-positive or ``W`` is null.

    Notes
    -----
    The arithmetic is written ``W * (D - 1) / D`` (multiply-then-divide, the same
    operation order as ``src.ingest``) so the result is bit-identical to the value
    already stored in ``data/processed/matches.parquet``'s ``o_dnb_underdog`` column.
    Algebraically equal forms (e.g. ``W * (1 - 1/D)``) can differ in the last ULP and
    would change the panel content SHA; do not "simplify" this expression.
    """
    w = np.asarray(win_price, dtype="float64")
    d = np.asarray(draw_price, dtype="float64")
    with np.errstate(divide="ignore", invalid="ignore"):
        out = np.where(
            np.isfinite(d) & (d > 0.0),
            w * (d - 1.0) / d,
            np.nan,
        )
    # Preserve scalar-in -> scalar-out.
    if out.ndim == 0:
        return float(out)
    return out


def raw_implied_prob(odds: float) -> float:
    """Raw implied probability ``r = 1/o`` of a decimal price (CALC §1).

    Not a fair probability: across the three 1X2 outcomes ``sum r = 1 + M`` carries the
    overround ``M``. De-vigging to fair ``(p_W, p_D, p_fav)`` is the ``devig`` dispatcher
    below (Phase 2 task 1). This helper exists for the selection min-implied-prob
    equivalence check and as the scalar reciprocal used throughout.
    """
    if not np.isfinite(odds) or odds <= 0.0:
        return float("nan")
    return 1.0 / odds


# ===========================================================================
# Implied (raw) probabilities + overround (CALC §1, §4).
# ===========================================================================


@dataclass(frozen=True)
class ImpliedProbs:
    """Raw reciprocal (vigged) 1X2 probabilities and the overround (CALC §1)."""

    r_H: float
    r_D: float
    r_A: float
    booksum: float  # Π = Σ r_i
    overround: float  # M = Π - 1 ≥ 0


def implied_probs(home: float, draw: float, away: float) -> ImpliedProbs:
    """Raw reciprocal implied probabilities ``r_i = 1/o_i`` and the overround.

    These are the VIGGED prices (``Σ r_i = Π = 1 + M > 1``); they are NOT fair
    probabilities -- removing ``M`` is the de-vig step (``devig``). The booksum and
    overround ``M = Π - 1`` are the bookmaker margin (CALC §1, eq. ``M = Π - 1``).
    """
    for name, o in (("home", home), ("draw", draw), ("away", away)):
        if not (o > 1.0):
            raise ValueError(f"decimal odds must be > 1 (profit on a win); {name}={o!r}")
    r_h, r_d, r_a = 1.0 / home, 1.0 / draw, 1.0 / away
    booksum = r_h + r_d + r_a
    return ImpliedProbs(r_H=r_h, r_D=r_d, r_A=r_a, booksum=booksum, overround=booksum - 1.0)


# ===========================================================================
# De-vig methods (CALC §4): basic / Shin / power.
# ===========================================================================


def devig_basic(home: float, draw: float, away: float) -> tuple[float, float, float]:
    """Basic / proportional (multiplicative) de-vig: ``p_i = r_i / Π`` (CALC §4.1).

    Spreads the margin in proportion to each raw price; cannot represent the
    favourite-longshot bias (preserves the raw odds ranking). The baseline branch.
    """
    ip = implied_probs(home, draw, away)
    pi = ip.booksum
    return ip.r_H / pi, ip.r_D / pi, ip.r_A / pi


def devig_power(home: float, draw: float, away: float) -> tuple[float, float, float]:
    """Power / logarithmic de-vig: fit exponent so ``Σ r_i^{k} = 1`` (CALC §4.4).

    The power transform ``p_i ∝ r_i^{1/n}`` with ``n`` chosen so the fair book sums to
    1 (Buchdahl; Vovk-Zhdanov 2009; Clarke et al. 2017). Working from raw prices, solve
    for ``k = 1/n`` such that the UN-normalised ``Σ r_i^k = 1`` (the fair-book booksum);
    ``n < 1`` ⇔ ``k > 1`` shortens longshots more than favourites, reproducing the FLB.
    Range-safe by construction (CALC §4.6 table).
    """
    ip = implied_probs(home, draw, away)
    r = np.array([ip.r_H, ip.r_D, ip.r_A], dtype="float64")

    def _booksum_minus_one(k: float) -> float:
        return float(np.sum(r**k) - 1.0)

    # Σ r^k at k=1 is Π > 1 (f > 0); as k→∞ each r_i^k → 0 so the sum → 0 (f < 0). The
    # target Σ r_i^k is strictly decreasing in k (all raw prices r_i < 1), so a unique
    # root exists on [1, k_hi]; grow k_hi until it straddles the root, then bisect.
    k_lo, k_hi = 1.0, 2.0
    while _booksum_minus_one(k_hi) > 0.0:
        k_hi *= 2.0
        if k_hi > 1e6:  # pragma: no cover - degenerate guard
            raise RuntimeError("power de-vig failed to bracket the exponent root")
    k = brentq(_booksum_minus_one, k_lo, k_hi, xtol=_SOLVER_TOL)
    p = r**k  # already sums to 1 at the solved k (the defining condition)
    return float(p[0]), float(p[1]), float(p[2])


def shin_probs_from_raw(r: npt.NDArray[np.floating], z: float) -> npt.NDArray[np.floating]:
    """Shin fair probabilities for raw prices ``r`` at insider fraction ``z`` (CALC §4.2).

    ``p_i = [√(z² + 4(1-z)·r_i²/Π) - z] / [2(1-z)]`` with ``Π = Σ r_j`` (the
    Jullien-Salanié 1994 closed form restated by Štrumbelj 2014). Valid for ``z ∈
    [0,1)`` on an over-round book (``Π > 1``).
    """
    r = np.asarray(r, dtype="float64")
    pi = r.sum()
    return (np.sqrt(z * z + 4.0 * (1.0 - z) * r * r / pi) - z) / (2.0 * (1.0 - z))


def shin_z(odds: tuple[float, ...] | list[float] | npt.NDArray[np.floating]) -> float:
    """Solve the Shin insider-fraction ``z`` so that ``Σ_i p_i(z) = 1`` (CALC §4.2).

    Fixed-point root of ``Σ shin_probs - 1`` on ``z ∈ [0, 1)``. Requires an OVER-round
    book (``Π = Σ 1/o_i > 1``) -- on an under-round book (the draw-dropped 1X2 residual)
    the root is invalid ``z < 0`` (CALC §4.2 applicability note), so we fail loudly
    rather than return a degenerate value. Works for any ``n`` (the three-way 1X2 book
    and, via ``shin_z_two_way`` as the exact cross-check, the quoted two-way AH-0 book).
    """
    r = np.array([1.0 / o for o in odds], dtype="float64")
    pi = r.sum()
    if not (pi > 1.0 + _SOLVER_TOL):
        raise ValueError(
            f"Shin requires an over-round book (Π > 1); got Π={pi:.6f}. The "
            "draw-dropped 1X2 residual is UNDER-round -- run Shin on the three-way 1X2 "
            "book and form q_W, or use the quoted two-way AH-0 book (CALC §4.2)."
        )

    def _sum_minus_one(z: float) -> float:
        return float(shin_probs_from_raw(r, z).sum() - 1.0)

    # shin_probs(z=0) = sqrt(4 r^2/Π)/2 = r/sqrt(Π), so Σ = Π/sqrt(Π) = sqrt(Π) > 1 for
    # an over-round book ⇒ f(0) > 0. As z→1 the probabilities approach r_i/Π (sum 1)
    # from below, giving a sign change; brentq on [0, 1-ε] isolates the unique root
    # (Štrumbelj 2014 fixed point).
    if abs(_sum_minus_one(0.0)) <= _SOLVER_TOL:
        return 0.0
    return brentq(_sum_minus_one, 0.0, _Z_UPPER, xtol=_SOLVER_TOL)


def shin_z_two_way(o_a: float, o_b: float) -> float:
    """Exact two-outcome Shin ``z`` closed form (Jullien-Salanié 1994; Štrumbelj 2016).

    With ``π₊ = r_a + r_b``, ``π₋ = r_a - r_b``:
        ``z = (Π - 1)(π₋² - π₊) / [π₊·(π₋² - 1)]``.
    Applicable ONLY to a genuine two-way OVER-round book (the quoted AH-0/DNB market),
    NOT the draw-dropped 1X2 residual (CALC §4.2). Used as the analytic ground-truth
    cross-check for the numeric ``shin_z`` n=2 special case (estimator-verification gate,
    task 7).
    """
    r_a, r_b = 1.0 / o_a, 1.0 / o_b
    pi = r_a + r_b
    if not (pi > 1.0 + _SOLVER_TOL):
        raise ValueError(
            f"two-way Shin requires an over-round book (Π > 1); got Π={pi:.6f} "
            "(under-round residual -- CALC §4.2 applicability note)."
        )
    pi_plus = r_a + r_b
    pi_minus = r_a - r_b
    return ((pi - 1.0) * (pi_minus**2 - pi_plus)) / (pi_plus * (pi_minus**2 - 1.0))


def devig_shin(home: float, draw: float, away: float) -> tuple[float, float, float]:
    """Shin (1992/1993) de-vig on the THREE-WAY 1X2 book (CALC §4.2; project primary).

    Solves the insider fraction ``z`` (``shin_z``) on the full over-round 1X2 book and
    returns the fair ``(p_H, p_D, p_A)``. Shin endogenously produces the
    favourite-longshot bias (longshots shaded down relative to favourites), the reason
    Štrumbelj (2014) finds it the most accurate soccer-odds probability forecast. Runs on
    the THREE-WAY book by construction -- never the under-round draw-dropped residual
    (CALC §4.2). Form the DNB conditional with ``conditional_win_prob`` AFTER de-vigging.
    """
    ip = implied_probs(home, draw, away)
    r = np.array([ip.r_H, ip.r_D, ip.r_A], dtype="float64")
    z = shin_z((home, draw, away))
    p = shin_probs_from_raw(r, z)
    return float(p[0]), float(p[1]), float(p[2])


_DISPATCH = {"basic": devig_basic, "shin": devig_shin, "power": devig_power}


def devig(
    home: float, draw: float, away: float, method: DevigMethod = "shin"
) -> tuple[float, float, float]:
    """De-vig dispatcher -> fair ``(p_H, p_D, p_A)`` summing to 1 (CALC §4).

    ``method`` ∈ {basic, shin, power}; default ``shin`` (the a-priori-frozen primary,
    design.md §3). Enforces the ARCH §2.2 pricing contract on the result: every fair
    probability is strictly positive and they sum to 1 (so ``0 < p_D`` and
    ``p_W + p_D ≤ 1`` hold for any pair). Raises on an out-of-contract result rather than
    passing a degenerate probability downstream.
    """
    if method not in _DISPATCH:
        raise ValueError(f"unknown de-vig method {method!r}; expected one of {DEVIG_METHODS}")
    p_h, p_d, p_a = _DISPATCH[method](home, draw, away)
    _check_fair_probs(p_h, p_d, p_a, method=method)
    return p_h, p_d, p_a


def _check_fair_probs(p_h: float, p_d: float, p_a: float, *, method: str) -> None:
    """Enforce the ARCH §2.2 pricing contract: 0 < p_i and Σ p = 1."""
    for name, p in (("p_H", p_h), ("p_D", p_d), ("p_A", p_a)):
        if not (p > 0.0):
            raise ValueError(
                f"de-vig method {method!r} produced non-positive {name}={p!r} "
                "(violates the ARCH §2.2 pricing contract 0 < p)"
            )
    total = p_h + p_d + p_a
    if abs(total - 1.0) > 1e-9:
        raise ValueError(
            f"de-vig method {method!r} fair probabilities sum to {total!r}, not 1 "
            "(violates Σ p = 1)"
        )


# ===========================================================================
# DNB conditional (no-draw) win probability and the margin wedge (CALC §3.4, §3.5, §5).
# ===========================================================================


def conditional_win_prob(p_win: float, p_draw: float) -> float:
    """The DNB (no-draw) conditional win probability ``q_W = p_W / (1 - p_D)`` (CALC §3.4, §5).

    The two-way DNB view: remove the draw and renormalise the two win states. Formed
    from the THREE-WAY fair probabilities (``devig``), never from a draw-dropped raw
    residual. ``1 - p_D = p_W + p_fav`` is the no-draw mass.
    """
    denom = 1.0 - p_draw
    if not (denom > 0.0):
        raise ValueError(f"draw probability must satisfy p_D < 1 to condition; p_D={p_draw!r}")
    return p_win / denom


@dataclass(frozen=True)
class MarginWedge:
    """The synthetic-vs-quoted DNB margin gap (CALC §3.5)."""

    m_1x2: float  # the 1X2 three-way overround the synthetic DNB inherits on both legs
    m_ah: float | None  # the quoted two-way AH-0 overround (None if no quote)
    wedge: float | None  # m_1x2 - m_ah (None if no quote)


def margin_wedge(
    home: float,
    draw: float,
    away: float,
    *,
    quoted_ah_win: float | None = None,
    quoted_ah_fav: float | None = None,
) -> MarginWedge:
    """Expose the margin wedge ``M_1X2 - M_AH`` (CALC §3.5; preferred-quoted policy).

    The synthetic DNB inherits the full three-way 1X2 margin on both legs; a quoted
    two-way AH-0 book carries its own (usually lower) margin. The pipeline prefers the
    quoted price when present and logs this wedge in the edge accounting (CALC §3.5,
    §8.3). When no AH-0 quote is supplied, ``m_ah``/``wedge`` are None.
    """
    m_1x2 = implied_probs(home, draw, away).overround
    if quoted_ah_win is None or quoted_ah_fav is None:
        return MarginWedge(m_1x2=m_1x2, m_ah=None, wedge=None)
    if not (quoted_ah_win > 1.0 and quoted_ah_fav > 1.0):
        raise ValueError("quoted AH-0 decimal odds must be > 1 on both legs")
    m_ah = (1.0 / quoted_ah_win + 1.0 / quoted_ah_fav) - 1.0
    return MarginWedge(m_1x2=m_1x2, m_ah=m_ah, wedge=m_1x2 - m_ah)


def dnb_price(
    win_price: float,
    draw_price: float,
    *,
    quoted_ah_price: float | None = None,
) -> tuple[float, str]:
    """Return the DNB price to use and its source, preferring the QUOTED AH-0 line.

    Policy (CALC §3.5; design.md §3): the quoted (tradable) AH-0 price on the underdog
    side is preferred where present (lower implied cost); the synthetic ``W·(D-1)/D`` is
    the fallback/cross-check. Returns ``(price, source)`` with ``source`` ∈
    {``"quoted_ah"``, ``"synthetic"``}.
    """
    if quoted_ah_price is not None:
        if not (quoted_ah_price > 1.0):
            raise ValueError(f"quoted AH-0 price must be > 1, got {quoted_ah_price!r}")
        return quoted_ah_price, "quoted_ah"
    return float(synthetic_dnb(win_price, draw_price)), "synthetic"
