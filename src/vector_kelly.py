"""Concurrent-matchday vector (multivariate) Kelly program (Phase 3 task 3; STAKE §5).

Group-stage matchdays settle several World-Cup matches SIMULTANEOUSLY. Sizing each
bet by the single-bet push-Kelly ``f*`` (src.staking) ignores the shared calendar
exposure and OVER-bets the aggregate matchday slate, because the budget constraint
``1^T f <= 1`` is not enforced across the concurrent bets (STAKE §5.1). The correct
object is the vector log-optimal portfolio program that sizes the WHOLE slate at once.

The exact program (STAKE §5.2, eq. 6; Kelly 1956; Thorp 2006; Busseti-Ryu-Boyd 2016;
Uhrin et al. 2021):

    maximise_f   sum_k pi_k * log( (O f)_k )
    subject to   1^T f = 1,   f >= 0.

``f in R^n`` are the wealth fractions over ``n-1`` underdog-DNB bets PLUS cash (asset
``n``); ``O`` is the payoff matrix whose ``(k, j)`` entry is the gross return multiple
of asset ``j`` in joint-outcome scenario ``k`` (a match-``j`` draw sets that column's
multiple to 1 -- the push -- in the scenarios where match ``j`` draws; cash is always
1); ``pi_k`` is the modeled probability of scenario ``k``. This is a CONCAVE program
(log of a non-negative linear function) solved by cvxpy with the pinned Clarabel
solver (ADR-0001). The single-bet formula (src.staking.push_kelly_fraction) is the
``n = 2`` special case.

The DEPLOYABLE rule (STAKE §5.3): the cheap, defensible approximation is to compute
the single-bet ``f*_j`` independently, then RENORMALISE so ``sum_j f*_j <= f_max``
(the budget cap) and apply the global fractional multiplier ``lambda``. The exact
program is the BENCHMARK; the renormalised-and-capped approximation is the reported
deployable rule, with its EXPECTED-LOG-GROWTH GAP to the exact solution quantified
(:func:`growth_gap`).

Independence of concurrent matches is the DEFAULT, to be TESTED (final-round
dead-rubber / "biscotto" collusion; STAKE §5.3, Open Question 2). When matches are
modeled independent ``pi_k = prod_j P(outcome_j)``; the dependence test lives in
:func:`independence_lr_test`. Both the independent-joint and a supplied dependent
joint can feed the program -- the program itself is agnostic to how ``pi`` was built.

DETERMINISM / NO MONTE-CARLO (provenance accuracy; ADR-0005). The DEPLOYED vector-Kelly
path is a fully DETERMINISTIC convex program: :func:`solve_vector_kelly` /
:func:`approx_vector_kelly` / :func:`growth_gap` enumerate the EXACT joint-scenario
probabilities (``3^n`` outcomes) and call the pinned Clarabel convex solver -- there is
NO random draw, no rng, and no resampling here, so two runs produce byte-identical
``f``/``growth_gap``. Consequently this module does NOT consume a ``vector-kelly`` RNG
sub-stream; the ``vector-kelly`` slot in ``src.seeding.STAGE_SPAWN_MAP`` (and its mirror
in config) is RESERVED for a future scenario-RESAMPLED evaluation (e.g. bootstrap over
resampled joint scenarios) but is currently UNUSED -- the recorded substream label
documents the reservation, not an exercised draw (ADR-0005 "vector-kelly: reserved").
Were such a resampled evaluation added it MUST draw from ``src.seeding.substream(
root_seed, 'vector-kelly')`` and carry an order-independence / byte-reproducibility test
mirroring ``tests/test_ruin.py::test_ruin_mc_deterministic_and_order_independent``.

No magic numbers: the budget cap ``f_max`` is the BRB-drawdown-constrained fraction
(src.ruin) or the explicit 1.0 full-budget; ``lambda`` is data-derived (src.staking);
the cvxpy solver tolerances are the library defaults (numerical, not tunable). pathlib
not required (pure numeric). The solver is Clarabel, pinned in ADR-0001.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field

import cvxpy as cp
import numpy as np
import numpy.typing as npt

from src import staking

# The pinned convex solver (ADR-0001). Named explicitly so a different default in a
# future cvxpy never silently changes the vector-Kelly numbers.
SOLVER = cp.CLARABEL

# The cvxpy solve statuses that license consuming ``f.value`` as a deployable allocation.
# Only OPTIMAL and OPTIMAL_INACCURATE return a usable primal solution; INFEASIBLE /
# UNBOUNDED / *_INACCURATE-without-a-solution / SOLVER_ERROR all leave ``f.value`` None
# or meaningless, and for a sizing engine that funds a real stake a degraded solve must
# FAIL CLOSED (raise) rather than silently returning an all-zero "do not bet" that a
# caller cannot distinguish from a legitimate all-cash optimum.
# cvxpy status semantics: https://www.cvxpy.org/tutorial/intro/index.html#infeasible-and-unbounded-problems
_ACCEPTED_SOLVER_STATUSES = (cp.OPTIMAL, cp.OPTIMAL_INACCURATE)

# The three per-match outcomes, in a FIXED order so the scenario enumeration and the
# payoff matrix are reproducible. Index meaning per match j:
#   0 = underdog WINS  -> column multiple o_dnb_j   (net +b_j)
#   1 = DRAW (push)    -> column multiple 1.0        (stake refunded)
#   2 = favourite wins -> column multiple 0.0        (loss)
_OUTCOME_WIN, _OUTCOME_DRAW, _OUTCOME_LOSS = 0, 1, 2
_N_OUTCOMES = 3


@dataclass(frozen=True)
class VectorKellyResult:
    """The exact vector-Kelly solution for one concurrent slate (STAKE §5.2)."""

    f: npt.NDArray[np.float64]  # length n: [f_bet_1, ..., f_bet_{n-1}, f_cash]
    f_bets: npt.NDArray[np.float64]  # the n-1 bet fractions (excludes cash)
    f_cash: float  # the cash residual fraction
    expected_log_growth: float  # sum_k pi_k log((O f)_k) at the optimum
    n_bets: int
    solver_status: str
    budget_used: float  # sum of bet fractions (<= f_max); the rest is cash


@dataclass(frozen=True)
class ApproxKellyResult:
    """The renormalised-and-capped single-bet approximation (the deployable rule; STAKE §5.3)."""

    f_bets: npt.NDArray[np.float64]  # capped, lambda-scaled bet fractions
    f_cash: float
    expected_log_growth: float  # evaluated under the SAME joint pi as the exact program
    single_bet_f: npt.NDArray[np.float64]  # the raw per-bet push-Kelly f* (pre-cap)
    budget_used: float
    renormalised: bool  # True iff the budget cap bound (sum f* > f_max)
    lam: float


@dataclass(frozen=True)
class GrowthGapResult:
    """The exact-vs-approximation expected-log-growth gap (STAKE §5.3 deliverable)."""

    exact: VectorKellyResult
    approx: ApproxKellyResult
    growth_gap: float  # exact.expected_log_growth - approx.expected_log_growth (>= 0)
    relative_gap: float  # growth_gap / |exact.expected_log_growth| (nan if exact ~ 0)


# ---------------------------------------------------------------------------
# Scenario enumeration + payoff matrix.
# ---------------------------------------------------------------------------


def enumerate_scenarios(n_bets: int) -> npt.NDArray[np.intp]:
    """All ``3^n_bets`` joint outcome scenarios as an array of per-match outcome indices.

    Row ``k`` is the joint realisation (one of {win, draw, loss} per match) of scenario
    ``k``; column ``j`` is match ``j``'s outcome index (0/1/2). Cartesian product in a
    FIXED lexicographic order so the scenario index is reproducible across runs.
    """
    if n_bets < 1:
        raise ValueError(f"n_bets must be >= 1, got {n_bets}")
    grid = itertools.product(range(_N_OUTCOMES), repeat=n_bets)
    return np.array(list(grid), dtype=np.intp)


def payoff_matrix(o_dnb: npt.ArrayLike) -> npt.NDArray[np.float64]:
    """Gross-return payoff matrix ``O`` for ``n_bets`` concurrent DNBs + cash (STAKE §5.2).

    ``O`` has one row per joint scenario (``3^n_bets`` rows) and ``n_bets + 1`` columns:
    one per bet plus a trailing CASH column (always 1.0). Entry ``O[k, j]`` is bet
    ``j``'s gross multiple in scenario ``k``: ``o_dnb_j`` if match ``j`` WINS in that
    scenario, ``1.0`` if it DRAWS (push -- stake refunded), ``0.0`` if it LOSES. The
    cash column is identically 1.0 (holding cash neither grows nor risks).
    """
    o = np.asarray(o_dnb, dtype="float64").ravel()
    n_bets = o.size
    scenarios = enumerate_scenarios(n_bets)
    n_scen = scenarios.shape[0]
    # `payoff` is the matrix written `O` in STAKE §5.2 eq. 6 (the variable name avoids
    # the single-letter `O`/`0` ambiguity; the maths symbol stays `O` in the docstrings).
    payoff = np.empty((n_scen, n_bets + 1), dtype="float64")
    for j in range(n_bets):
        col_outcome = scenarios[:, j]
        # win -> o_dnb_j ; draw -> 1.0 (push) ; loss -> 0.0
        payoff[:, j] = np.where(
            col_outcome == _OUTCOME_WIN,
            o[j],
            np.where(col_outcome == _OUTCOME_DRAW, 1.0, 0.0),
        )
    payoff[:, n_bets] = 1.0  # cash column
    return payoff


def independent_joint(p_win: npt.ArrayLike, p_draw: npt.ArrayLike) -> npt.NDArray[np.float64]:
    """Scenario probabilities ``pi_k = prod_j P(outcome_j)`` under the independence default.

    For each scenario (row of :func:`enumerate_scenarios`) multiply the per-match
    marginal of the realised outcome: ``p_win_j`` if match ``j`` wins, ``p_draw_j`` if
    it draws, ``p_fav_j = 1 - p_win_j - p_draw_j`` if it loses. Independence is the
    STAKE §5.3 default, to be tested (:func:`independence_lr_test`); a DEPENDENT joint
    can be supplied directly to the program instead.
    """
    pw = np.asarray(p_win, dtype="float64").ravel()
    pd_ = np.asarray(p_draw, dtype="float64").ravel()
    if pw.shape != pd_.shape:
        raise ValueError(f"p_win {pw.shape} and p_draw {pd_.shape} must match")
    p_fav = 1.0 - pw - pd_
    per_match = np.stack([pw, pd_, p_fav], axis=1)  # (n_bets, 3) in outcome order
    scenarios = enumerate_scenarios(pw.size)
    # pi_k = prod_j per_match[j, outcome_kj]
    rows = np.arange(pw.size)
    probs = per_match[rows[None, :], scenarios]  # (n_scen, n_bets)
    return probs.prod(axis=1)


# ---------------------------------------------------------------------------
# The exact convex vector-Kelly program (cvxpy / Clarabel).
# ---------------------------------------------------------------------------


def solve_vector_kelly(
    o_dnb: npt.ArrayLike,
    p_win: npt.ArrayLike,
    p_draw: npt.ArrayLike,
    *,
    pi: npt.ArrayLike | None = None,
    f_max: float = 1.0,
) -> VectorKellyResult:
    """Solve the exact concurrent-matchday vector-Kelly program (STAKE §5.2, eq. 6).

    ``maximise_f sum_k pi_k log((O f)_k)  s.t.  1^T f = 1, f >= 0`` over ``n_bets``
    concurrent underdog DNBs plus cash, with cvxpy + the pinned Clarabel solver
    (ADR-0001). The objective is concave; the budget constraint binds the total
    matchday stake (STAKE §5.3). When ``pi`` is omitted the independence default
    (:func:`independent_joint`) is used; pass a dependent joint to relax it.

    ``f_max`` optionally caps the total BET budget (``sum of bet fractions <= f_max``),
    so the drawdown-constrained budget from src.ruin can be threaded in; the residual
    ``1 - sum f_bets`` is cash. With ``f_max = 1`` the only cap is the simplex itself.

    The all-negative-edge honest-prior case (slice brief; STAKE §7.3) is handled
    cleanly: when no bet has positive edge the optimum puts ALL weight on cash
    (``f_cash ~ 1``, every ``f_bet ~ 0``, ``expected_log_growth ~ 0``) -- "do not bet"
    as a legitimate, solver-reported output, not an error.
    """
    o = np.asarray(o_dnb, dtype="float64").ravel()
    n_bets = o.size
    payoff = payoff_matrix(o)  # the `O` of STAKE §5.2 eq. 6
    if pi is None:
        pi_arr = independent_joint(p_win, p_draw)
    else:
        pi_arr = np.asarray(pi, dtype="float64").ravel()
        if pi_arr.size != payoff.shape[0]:
            raise ValueError(f"pi has {pi_arr.size} scenarios; payoff matrix has {payoff.shape[0]}")
    # Normalise pi defensively (a supplied joint may carry rounding drift).
    pi_arr = pi_arr / pi_arr.sum()

    f = cp.Variable(n_bets + 1, nonneg=True)
    # Objective: sum_k pi_k log((O f)_k). cp.log is concave; the weighted sum is concave.
    objective = cp.Maximize(pi_arr @ cp.log(payoff @ f))
    constraints = [cp.sum(f) == 1.0]
    if f_max < 1.0:
        # Cap the BET budget (exclude the cash asset, index n_bets).
        constraints.append(cp.sum(f[:n_bets]) <= float(f_max))
    problem = cp.Problem(objective, constraints)
    try:
        problem.solve(solver=SOLVER)
    except cp.error.SolverError as exc:  # numerical failure inside Clarabel
        raise RuntimeError(
            f"vector-Kelly solve raised a SolverError (solver={SOLVER}): {exc}"
        ) from exc

    # FAIL CLOSED on a non-converged solve. An infeasible / unbounded / errored status
    # leaves ``f.value`` either None or numerically meaningless; consuming it would report
    # a degraded solve as a legitimate all-cash "do not bet" (a fail-OPEN default). A
    # sizing engine that funds a deployable stake must raise instead so the failure is
    # visible to the caller (growth_gap, the report stage), not buried in solver_status.
    if problem.status not in _ACCEPTED_SOLVER_STATUSES or f.value is None:
        raise RuntimeError(
            f"vector-Kelly solve did not converge to a usable solution: "
            f"status={problem.status!r} (accepted: {_ACCEPTED_SOLVER_STATUSES}); "
            f"f.value is {'None' if f.value is None else 'present'}"
        )

    f_val = np.asarray(f.value, dtype="float64").ravel()
    # Clip tiny negative numerical residuals from the interior-point solver to 0.
    f_val = np.where(f_val < 0.0, 0.0, f_val)
    f_bets = f_val[:n_bets]
    f_cash = float(f_val[n_bets])
    g = float(expected_log_growth(payoff, f_val, pi_arr))
    return VectorKellyResult(
        f=f_val,
        f_bets=f_bets,
        f_cash=f_cash,
        expected_log_growth=g,
        n_bets=n_bets,
        solver_status=str(problem.status),
        budget_used=float(f_bets.sum()),
    )


def expected_log_growth(
    payoff: npt.NDArray[np.float64], f: npt.ArrayLike, pi: npt.ArrayLike
) -> float:
    """Evaluate ``sum_k pi_k log((O f)_k)`` for a given allocation ``f`` under joint ``pi``.

    ``payoff`` is the matrix written ``O`` in STAKE §5.2 eq. 6. The shared growth
    objective both the exact program maximises and the approximation is SCORED at, so
    the growth gap (:func:`growth_gap`) compares like with like. A non-positive
    ``(O f)_k`` (a bankrupting scenario) yields ``-inf`` growth -- the correct, honest
    signal that the allocation can ruin in that scenario.
    """
    fv = np.asarray(f, dtype="float64").ravel()
    piv = np.asarray(pi, dtype="float64").ravel()
    wealth = payoff @ fv
    with np.errstate(divide="ignore", invalid="ignore"):
        logw = np.where(wealth > 0.0, np.log(wealth), -np.inf)
    return float(np.sum(piv * logw))


# ---------------------------------------------------------------------------
# The renormalised-and-capped single-bet approximation (the deployable rule).
# ---------------------------------------------------------------------------


def approx_vector_kelly(
    o_dnb: npt.ArrayLike,
    p_win: npt.ArrayLike,
    p_draw: npt.ArrayLike,
    *,
    pi: npt.ArrayLike | None = None,
    f_max: float = 1.0,
    lam: float = 1.0,
) -> ApproxKellyResult:
    """The renormalised-and-capped single-bet approximation (STAKE §5.3 deployable rule).

    Compute the single-bet push-Kelly ``f*_j`` independently (src.staking), then:
      1. apply the global fractional multiplier ``lambda`` (``f_j <- lambda * f*_j``);
      2. if ``sum_j f_j > f_max`` RENORMALISE so ``sum_j f_j = f_max`` (the budget cap
         caps total matchday stake below the sum of independent single-bet Kelly
         fractions -- STAKE §5.3); otherwise leave them (the budget did not bind).
    The residual ``1 - sum f_j`` is cash. The expected log-growth is scored under the
    SAME joint ``pi`` as the exact program so :func:`growth_gap` is apples-to-apples.

    Negative-edge bets contribute ``f*_j = 0`` (no short side; inherited from
    push_kelly_fraction), so the all-negative-edge case yields all-cash cleanly.
    """
    o = np.asarray(o_dnb, dtype="float64").ravel()
    single = staking.push_kelly_fraction(p_win, p_draw, o, clip_negative=True)
    single = np.atleast_1d(np.asarray(single, dtype="float64"))
    scaled = float(lam) * single
    total = float(scaled.sum())
    renorm = total > f_max + 1e-15
    f_bets = scaled * (f_max / total) if (renorm and total > 0.0) else scaled
    f_cash = 1.0 - float(f_bets.sum())
    f_full = np.concatenate([f_bets, [f_cash]])

    payoff = payoff_matrix(o)
    if pi is None:
        pi_arr = independent_joint(p_win, p_draw)
    else:
        pi_arr = np.asarray(pi, dtype="float64").ravel()
    pi_arr = pi_arr / pi_arr.sum()
    g = expected_log_growth(payoff, f_full, pi_arr)
    return ApproxKellyResult(
        f_bets=f_bets,
        f_cash=f_cash,
        expected_log_growth=g,
        single_bet_f=single,
        budget_used=float(f_bets.sum()),
        renormalised=renorm,
        lam=float(lam),
    )


def growth_gap(
    o_dnb: npt.ArrayLike,
    p_win: npt.ArrayLike,
    p_draw: npt.ArrayLike,
    *,
    pi: npt.ArrayLike | None = None,
    f_max: float = 1.0,
    lam: float = 1.0,
) -> GrowthGapResult:
    """Expected-log-growth gap of the deployable approximation vs the exact program (STAKE §5.3).

    Runs both :func:`solve_vector_kelly` (exact benchmark) and
    :func:`approx_vector_kelly` (renormalised-capped deployable rule) under the SAME
    joint ``pi`` and budget cap, and reports ``exact_growth - approx_growth`` (>= 0 by
    optimality of the exact program, up to solver tolerance) plus the relative gap. The
    slice deliverable: "report the growth gap" of the deployable rule to the exact
    vector program.
    """
    exact = solve_vector_kelly(o_dnb, p_win, p_draw, pi=pi, f_max=f_max)
    approx = approx_vector_kelly(o_dnb, p_win, p_draw, pi=pi, f_max=f_max, lam=lam)
    gap = exact.expected_log_growth - approx.expected_log_growth
    denom = abs(exact.expected_log_growth)
    rel = gap / denom if denom > 1e-15 else float("nan")
    return GrowthGapResult(exact=exact, approx=approx, growth_gap=gap, relative_gap=rel)


# ---------------------------------------------------------------------------
# Concurrent-match independence test (Phase 3 task 8; STAKE §5.3, Open Question 2).
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class IndependenceTestResult:
    """Likelihood-ratio test of concurrent-match outcome independence (STAKE Open Question 2)."""

    lr_statistic: float
    dof: int
    p_value: float
    n_matchdays: int
    reject_independence: bool  # at the supplied alpha
    alpha: float
    note: str = ""
    per_cell: dict[str, int] = field(default_factory=dict)


def independence_lr_test(
    matchday_outcomes: list[npt.ArrayLike],
    *,
    alpha: float = 0.05,
) -> IndependenceTestResult:
    """G-test (LR chi-square) of independence between PAIRED concurrent-match outcomes.

    The renormalised single-bet approximation (STAKE §5.3) is only defensible if
    concurrent matches are (close to) independent in OUTCOME -- final-round dead-rubber
    / "biscotto" collusion is the documented violation (STAKE Open Question 2). This is
    the test gating that assumption (Phase 3 task 8): pool every adjacent within-matchday
    PAIR of underdog-DNB outcomes (each in {win, draw, loss}) into a 3x3 contingency
    table and run the likelihood-ratio (G) test of independence. Rejection => the joint
    ``pi`` must be modeled dependently and the EXACT vector program (not the renormalised
    approximation) is required.

    ``matchday_outcomes`` is a list (one per matchday) of arrays of per-bet outcome
    indices (0=win, 1=draw, 2=loss). Matchdays with < 2 concurrent bets contribute no
    pair (independence is undefined for a singleton slate). ``alpha`` is the declared
    test SIZE (a decision input; the default mirrors methodology.md's conventional 0.05,
    overridable). The G-statistic is ``2 sum O ln(O/E)`` with ``dof = (3-1)(3-1) = 4``.
    """
    from scipy import stats

    table = np.zeros((_N_OUTCOMES, _N_OUTCOMES), dtype="float64")
    n_pairs = 0
    n_matchdays = 0
    for day in matchday_outcomes:
        arr = np.atleast_1d(np.asarray(day, dtype=np.intp)).ravel()
        if arr.size < 2:
            continue
        n_matchdays += 1
        # All adjacent pairs within the matchday (preserves the within-day clustering).
        for a, b in itertools.pairwise(arr):
            if 0 <= a < _N_OUTCOMES and 0 <= b < _N_OUTCOMES:
                table[a, b] += 1.0
                n_pairs += 1

    if n_pairs == 0:
        return IndependenceTestResult(
            lr_statistic=float("nan"),
            dof=0,
            p_value=float("nan"),
            n_matchdays=0,
            reject_independence=False,
            alpha=alpha,
            note="no concurrent within-matchday pairs (every slate is a singleton)",
        )

    row = table.sum(axis=1, keepdims=True)
    col = table.sum(axis=0, keepdims=True)
    total = table.sum()
    expected = row @ col / total
    mask = (table > 0.0) & (expected > 0.0)
    g_stat = 2.0 * float(np.sum(table[mask] * np.log(table[mask] / expected[mask])))
    # dof = (rows used - 1)(cols used - 1); collapse empty margins so dof is honest.
    used_rows = int((row.ravel() > 0).sum())
    used_cols = int((col.ravel() > 0).sum())
    dof = max((used_rows - 1) * (used_cols - 1), 1)
    p = float(stats.chi2.sf(g_stat, dof))
    per_cell = {f"{i}{j}": int(table[i, j]) for i in range(_N_OUTCOMES) for j in range(_N_OUTCOMES)}
    return IndependenceTestResult(
        lr_statistic=g_stat,
        dof=dof,
        p_value=p,
        n_matchdays=n_matchdays,
        reject_independence=bool(p < alpha),
        alpha=alpha,
        note=(
            f"G-test of independence on {n_pairs} within-matchday outcome pairs "
            "(0=win,1=draw,2=loss); reject => model the joint pi dependently, run the "
            "exact vector program (STAKE Open Question 2)"
        ),
        per_cell=per_cell,
    )
