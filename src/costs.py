"""Transaction-cost / execution model for the two-leg synthetic DNB (Phase 3 task 9; ADR-0004).

The synthetic DNB is a TWO-LEG position -- stake ``1/D`` on the draw and ``(D-1)/D``
on the win (CALC §3.1, §5.1) -- and the EV identity ``o_DNB = W*(D-1)/D`` assumes
BOTH legs fill at the quoted closing line simultaneously at ZERO slippage. That
idealization is modeled and stressed here, never assumed: net-of-cost is a
precondition for any reported growth/ROI/Sharpe (slice brief; Phase 4/5 acceptance).

Three components (ADR-0004; STAKE §6.3 / Phase-3 methods "Transaction-cost / execution
model"):

  (i)  PER-LEG SLIPPAGE, calibrated from the Phase-1 open->close move distribution
       (``src.ingest.open_close_moves``, written to logs/data_quality_<run_id>.json
       under "open_close_moves", per division-season x reference regime x odds
       bucket). The applied slippage is a DATA-SELECTED quantile of the *absolute*
       open->close relative move (the §D.3 selection procedure -- empirical quantile,
       NOT a magic number). It is APPLIED PER ODDS BUCKET, not pooled: a bet's odds
       bucket is resolved from its underdog price via the persisted quantile EDGES
       (``SlippageCalibration.resolve_odds_bucket``) and the per-bucket value
       (``by_odds_bucket[bucket]``, e.g. longshot bucket_4 p50 ~6.8% vs pooled ~5.2%)
       is shaved, falling back to pooled only when the bucket is unknown -- so the
       per-division-season x odds-bucket calibration actually bites (ADR-0004; Phase-3
       task 9). See :func:`calibrate_slippage` and the quantile-choice rationale.
  (ii) LEG-OUT assumption. Default ``atomic_two_leg_fill`` -- both legs fill at the
       closing line, stated as an IDEALIZATION -- AND a ``one_tick_adverse`` stress
       branch (the second leg fills one tick worse after the first), bounding
       non-simultaneous (leg-out) execution risk. The DNB is TWO legs (``1/D`` draw +
       ``(D-1)/D`` win); the stress branch shaves BOTH the win-leg fill (one tick on
       the effective win odds) AND the draw-leg fill on a PUSH (the ``1/D`` draw stake
       refunds < 1 unit when the draw leg fills adversely), so the push outcome carries
       its modeled draw-leg execution cost (~p_draw * slippage) instead of an exact 1.0
       refund. Net metrics are reported under BOTH branches (:func:`net_return`
       ``legout_model``).
  (iii) BETFAIR-EXCHANGE (BFEC) COMMISSION as an effective overround. The exchange
       fallback charges commission on NET WINNINGS, not overround (DATA §2.3,
       2-5%). :func:`commission_effective_overround` converts the rate to an
       effective overround on the exchange DNB and reconciles it against the
       Phase-1 synthetic-vs-quoted margin wedge ``M_1X2 - M_AH`` (CALC §3.5;
       Phase-1 pooled mean +0.7985%).

What this module computes. Given the DNB decimal odds ``o_dnb`` and a settled GROSS
per-unit return ``r_gross in {o_dnb, 1.0, 0.0}`` (win / push / loss; settlement.py),
:func:`net_return` returns the NET per-unit return after (a) the slippage-shaved
effective win odds, (b) the leg-out branch, and (c) the exchange commission on net
winnings (when the route is the exchange). The ledger (src.ledger) carries BOTH the
gross and the net per-unit return on every entry; the Phase-4 metrics engine consumes
net (slice brief).

No magic numbers: the slippage quantile LEVEL and value are selected from the
empirical open->close distribution; the commission RATE is read from config within the
DATA §2.3 [0.02, 0.05] range with a documented selection rationale; the only structural
constants are the 0/1 push/loss returns and the unit stake. pathlib only for the
calibration-distribution read.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import numpy as np
import numpy.typing as npt

PROJECT_ROOT = Path(__file__).resolve().parent.parent
LOGS_DIR = PROJECT_ROOT / "logs"

LegOutModel = Literal["atomic_two_leg_fill", "one_tick_adverse"]

# DATA §2.3 Betfair-exchange commission range (on NET WINNINGS). The applied rate is
# selected from THIS range with a documented rationale (see select_commission_rate);
# the bounds themselves are the cited DATA §2.3 figures, not tunables.
BFEC_COMMISSION_MIN = 0.02
BFEC_COMMISSION_MAX = 0.05

# The empirical-quantile LEVELS reported as the slippage ladder. The applied level is
# selected from this ladder (default p50 -- the robust location of the adverse move;
# see calibrate_slippage rationale); p90/p95/p99 are the reported stress rungs. These
# are quantile LEVELS (positions in the empirical distribution), not asserted move
# magnitudes -- the value at each level is read from the data.
SLIPPAGE_QUANTILE_LADDER: tuple[str, ...] = ("p50", "p90", "p95", "p99")


# ===========================================================================
# Component (i): per-leg slippage, calibrated from the open->close distribution.
# ===========================================================================


@dataclass(frozen=True)
class SlippageCalibration:
    """The per-leg slippage selected from the Phase-1 open->close move distribution.

    ``quantile_level`` is the selected empirical-quantile level (default ``"p50"``);
    ``value`` is the relative-move magnitude AT that level (a fraction, e.g. 0.0523
    = a 5.23% adverse relative move on the odds leg); ``source`` records the basis
    so the figure is auditable; ``by_odds_bucket`` carries the per-bucket value at
    the selected level (the slippage is applied per odds bucket, not pooled, when a
    bucket is known). NOTHING here is asserted -- every magnitude is read from the
    data_quality open_close_moves block.
    """

    quantile_level: str
    value: float
    source: str
    n_observable: int
    by_odds_bucket: Mapping[str, float] = field(default_factory=dict)
    ladder: Mapping[str, float] = field(default_factory=dict)
    # The empirical-quantile EDGES of the underdog price that delimit the odds buckets
    # (src.ingest.open_close_moves -> "odds_bucket_edges"). With ``k`` buckets there are
    # ``k + 1`` ascending edges; a bet's underdog price ``o`` lands in ``bucket_i`` when
    # ``edges[i] <= o < edges[i+1]`` (the top bucket is right-closed). Persisted so the
    # per-bucket slippage can be APPLIED per bet (resolve_odds_bucket), not just collected
    # -- the deviation ADR-0004/Phase-3-task-9 flag. Empty => pooled application only.
    odds_bucket_edges: tuple[float, ...] = ()

    def slippage_for_bucket(self, bucket: str | None) -> float:
        """Per-bucket slippage value, falling back to the pooled value when unknown.

        Returns ``by_odds_bucket[bucket]`` when ``bucket`` is a calibrated bucket label
        (e.g. ``"bucket_4"``), else the pooled ``value``. This is the function that makes
        the per-division-season x odds-bucket calibration BITE at application: a longshot
        (bucket_4) bet is shaved by its own larger adverse move (~6.8% p50) rather than
        the pooled ~5.2% (ADR-0004; Phase-3 task 9 "per ... odds bucket").
        """
        if bucket is not None and bucket in self.by_odds_bucket:
            return float(self.by_odds_bucket[bucket])
        return float(self.value)

    def resolve_odds_bucket(self, o_dnb: float) -> str | None:
        """Map an underdog/DNB price to its odds-bucket label via the persisted edges.

        Returns ``"bucket_i"`` for the half-open interval ``[edges[i], edges[i+1])`` the
        price falls in (top bucket right-closed; prices below the first / above the last
        edge clamp to the extreme buckets, so an out-of-sample price still resolves to the
        nearest calibrated bucket rather than the pooled value). Returns ``None`` when no
        edges are available (then :meth:`slippage_for_bucket` uses the pooled value). The
        edges are pre-kickoff closing-price quantiles, so the assignment is non-anticipating
        (a function of the bet's own price only, never the result).
        """
        edges = self.odds_bucket_edges
        if not edges or len(edges) < 2 or not np.isfinite(o_dnb):
            return None
        n_buckets = len(edges) - 1
        # searchsorted on the interior edges gives the half-open bucket index; clamp the
        # extremes so an out-of-range price maps to the nearest bucket, not None.
        idx = int(np.searchsorted(np.asarray(edges[1:-1], dtype="float64"), o_dnb, side="right"))
        idx = min(max(idx, 0), n_buckets - 1)
        return f"bucket_{idx}"


def latest_data_quality_report(logs_dir: Path | None = None) -> Path | None:
    """Return the newest ``logs/data_quality_ingest-*.json`` (the open->close basis).

    The open->close move distribution is written by the Phase-1 ingest stage into
    the data-quality report (``src.ingest.open_close_moves`` -> the
    ``"open_close_moves"`` key). Returns ``None`` if no report exists (the caller
    then carries the league-calibrated value with a flag, per Phase-1 task 9.1).
    """
    d = Path(logs_dir) if logs_dir is not None else LOGS_DIR
    if not d.exists():
        return None
    candidates = sorted(d.glob("data_quality_ingest-*.json"))
    return candidates[-1] if candidates else None


def calibrate_slippage(
    *,
    quantile_level: str = "p50",
    data_quality_report: Path | None = None,
    logs_dir: Path | None = None,
    open_close_moves: Mapping[str, Any] | None = None,
) -> SlippageCalibration:
    """Select the per-leg slippage as a DATA quantile of the open->close move (task 9.1).

    Quantile-choice RATIONALE (no magic number; CLAUDE.md no-arbitrary-thresholds).
    The open->close relative move is the empirical proxy for the adverse price drift
    a bettor incurs between deciding on the closing-line signal and actually filling
    (the closing line is itself the most efficient public line, so the move from the
    pre-match open to the close bounds the realisable execution slippage on a leg).
    The applied per-leg slippage is the **median (p50)** of the *absolute* relative
    move per odds bucket: the p50 is the robust LOCATION of the adverse-move
    distribution (no tail-shape assumption, unaffected by the heavy right tail the
    p99 carries), so it is the principled central execution-cost estimate. The
    p90/p95/p99 rungs are reported as the slippage STRESS ladder (the one-tick-adverse
    leg-out stress is a *separate* axis; this ladder stresses the slippage MAGNITUDE).
    The choice of p50 as the operating level -- vs a tail quantile -- is the documented
    selection; the value at p50 is read from the data, never asserted.

    MAGNITUDE SEMANTICS (the deliberate conservative bias; ADR-0004 "Slippage magnitude").
    Two approximations are made here, both in the CONSERVATIVE (cost-overstating)
    direction, stated rather than hidden:
      (a) Two-sided -> one-sided. The calibrated move is the median of the *absolute*
          (two-sided) open->close relative move ``|refC/PS - 1|``, applied
          ONE-directionally as adverse slippage. For a roughly symmetric move the median
          absolute value is ~2x the expected adverse-only drift, so this OVERSTATES the
          execution cost by up to ~2x. We adopt it deliberately: net-of-cost is a
          precondition for the honest verdict (ADR-0004), and over-charging execution
          cost makes a "do not bet" verdict (the honest prior) HARDER to overturn, not
          easier -- a conservative bias on the load-bearing direction. The signed
          adverse-tail alternative is the less-conservative refinement, not adopted.
      (b) 1X2 leg -> DNB composite. The move is measured on the 1X2 win-side closing
          prices, then applied as a relative shave on the DNB composite
          ``o_dnb = A*(D-1)/D``. The DNB price is a monotone function of the same 1X2
          legs, so a relative move on the win leg maps approximately to a relative move
          on the composite; treating them as equal is a first-order mapping whose error
          is second-order in the (small) draw-leg move. Both approximations are reported
          in the slippage-sensitivity ladder (p50/p90/p95/p99) so the net verdict's
          dependence on the magnitude/definition choice is visible, not assumed away.

    Parameters
    ----------
    quantile_level : str, default "p50"
        Which empirical-quantile level to apply (one of SLIPPAGE_QUANTILE_LADDER).
    data_quality_report / logs_dir : Path, optional
        Where to read the open_close_moves block from; defaults to the newest
        ``logs/data_quality_ingest-*.json``.
    open_close_moves : Mapping, optional
        Pass the block directly (tests / in-memory pipelines) instead of reading a
        file.

    Returns
    -------
    SlippageCalibration
        The selected level, its pooled value, the per-odds-bucket values at that
        level, and the full ladder -- all read from the data.
    """
    if quantile_level not in SLIPPAGE_QUANTILE_LADDER:
        raise ValueError(
            f"quantile_level {quantile_level!r} must be one of {SLIPPAGE_QUANTILE_LADDER}"
        )

    block = open_close_moves
    if block is None:
        report = data_quality_report
        if report is None:
            report = latest_data_quality_report(logs_dir)
        if report is None:
            raise FileNotFoundError(
                "no open->close calibration available: pass open_close_moves=, a "
                "data_quality_report path, or run --stage ingest first (Phase-1 task 9.1)."
            )
        report = Path(report)
        full = json.loads(report.read_text(encoding="utf-8"))
        block = full.get("open_close_moves")
        if not block:
            raise KeyError(f"{report} has no 'open_close_moves' block (Phase-1 task 9.1)")

    pooled = block.get("pooled") or {}
    if quantile_level not in pooled:
        raise KeyError(
            f"open_close_moves.pooled has no {quantile_level!r} level; available: {sorted(pooled)}"
        )
    value = float(pooled[quantile_level])
    ladder = {lvl: float(pooled[lvl]) for lvl in SLIPPAGE_QUANTILE_LADDER if lvl in pooled}

    by_bucket: dict[str, float] = {}
    for bucket, summ in (block.get("by_odds_bucket") or {}).items():
        if quantile_level in summ:
            by_bucket[str(bucket)] = float(summ[quantile_level])

    edges = tuple(float(e) for e in (block.get("odds_bucket_edges") or []))

    n_obs = int(block.get("n_observable", 0))
    source = (
        "open->close absolute relative move, "
        f"{quantile_level} of the empirical distribution "
        f"(n_observable={n_obs}; per division-season x reference regime x odds bucket; "
        "Phase-1 task 9.1)"
    )
    return SlippageCalibration(
        quantile_level=quantile_level,
        value=value,
        source=source,
        n_observable=n_obs,
        by_odds_bucket=by_bucket,
        ladder=ladder,
        odds_bucket_edges=edges,
    )


# ===========================================================================
# Component (iii): BFEC commission as an effective overround.
# ===========================================================================


def select_commission_rate(rate: float | None) -> float:
    """Validate / default the BFEC commission rate within the DATA §2.3 [2%,5%] band.

    RATIONALE (no magic number). DATA §2.3 fixes the Betfair-exchange commission at
    2-5% on net winnings. The applied rate is read from config
    (``costs.bfec_commission_rate``); when unset, the MIDPOINT 3.5% of the cited
    [0.02, 0.05] band is used as the documented default -- the band midpoint is the
    no-information central estimate within the cited range, not an asserted figure,
    and the band ENDPOINTS (2% / 5%) are reported as the commission sensitivity.
    Any explicit rate must lie within the cited band or the function raises (a rate
    outside [2%,5%] is not a DATA §2.3 figure).
    """
    if rate is None:
        return 0.5 * (BFEC_COMMISSION_MIN + BFEC_COMMISSION_MAX)  # band midpoint (3.5%)
    r = float(rate)
    if not (BFEC_COMMISSION_MIN <= r <= BFEC_COMMISSION_MAX):
        raise ValueError(
            f"BFEC commission rate {r} outside the cited DATA §2.3 band "
            f"[{BFEC_COMMISSION_MIN}, {BFEC_COMMISSION_MAX}]"
        )
    return r


def commission_effective_overround(o_dnb: float, commission_rate: float | None) -> float:
    """Convert BFEC commission (on net winnings) to an effective overround (CALC §3.5).

    Betfair charges ``commission_rate`` on NET WINNINGS, not overround. A back bet at
    exchange decimal odds ``o_dnb`` that wins returns net profit ``(o_dnb - 1)``, of
    which the commission takes ``c*(o_dnb - 1)``, so the COMMISSION-NET decimal odds
    are ``o_eff = 1 + (1 - c)*(o_dnb - 1)``. The *implied* probability moves from
    ``1/o_dnb`` to ``1/o_eff``; the EFFECTIVE OVERROUND the commission imposes is the
    extra implied mass it adds on the back side:

        ``M_eff = 1/o_eff - 1/o_dnb``  (>= 0; the commission's overround-equivalent).

    This puts the exchange-route cost on the SAME FOOTING as the quoted/synthetic-route
    margin so it can be reconciled against the Phase-1 ``M_1X2 - M_AH`` wedge
    (:func:`reconcile_commission_vs_wedge`). Returns ``M_eff``.
    """
    c = select_commission_rate(commission_rate)
    if not (o_dnb > 1.0):
        raise ValueError(f"o_dnb must be > 1 to carry net winnings; got {o_dnb}")
    o_eff = 1.0 + (1.0 - c) * (o_dnb - 1.0)
    return (1.0 / o_eff) - (1.0 / o_dnb)


@dataclass(frozen=True)
class CommissionReconciliation:
    """The BFEC-commission effective overround reconciled vs the M_1X2 - M_AH wedge."""

    commission_rate: float
    o_dnb: float
    effective_overround: float
    margin_wedge: float
    # effective_overround - margin_wedge: how much MORE (positive) or less the exchange
    # commission costs than the synthetic-vs-quoted margin wedge, on the same footing.
    gap_vs_wedge: float


def reconcile_commission_vs_wedge(
    o_dnb: float, commission_rate: float | None, margin_wedge: float
) -> CommissionReconciliation:
    """Reconcile the commission effective overround against the Phase-1 wedge (CALC §3.5).

    ``margin_wedge`` is the Phase-1 synthetic-vs-quoted margin gap ``M_1X2 - M_AH``
    (data-quality report ``margin_wedge.wedge_mean``; Phase-1 pooled mean +0.7985%).
    The reconciliation expresses BOTH costs as overround on the back side so the
    exchange route and the quoted/synthetic route are cost-comparable, and reports
    the gap (``effective_overround - margin_wedge``).
    """
    m_eff = commission_effective_overround(o_dnb, commission_rate)
    return CommissionReconciliation(
        commission_rate=select_commission_rate(commission_rate),
        o_dnb=float(o_dnb),
        effective_overround=m_eff,
        margin_wedge=float(margin_wedge),
        gap_vs_wedge=m_eff - float(margin_wedge),
    )


# ===========================================================================
# The applied cost model: gross -> net per-unit return.
# ===========================================================================


@dataclass(frozen=True)
class CostModel:
    """Resolved, applied execution-cost model (the populated ADR-0004 costs block).

    Built from the config ``costs`` block + the Phase-1 calibration via
    :func:`from_config`. Carries the data-selected slippage, the leg-out branch, the
    commission rate, and the route (synthetic/quoted vs exchange) so :func:`net_return`
    is a pure function of the settled gross return and the bet's odds.
    """

    slippage: SlippageCalibration
    legout_model: LegOutModel
    one_tick: float
    commission_rate: float
    route: Literal["book", "exchange"]
    model_id: str = "costs.dnb_two_leg.v1"

    def slippage_value(
        self, o_dnb: float, *, odds_bucket: str | None = None, override: float | None = None
    ) -> float:
        """Resolve the per-bet slippage: explicit override > per-bucket > pooled.

        Application order (ADR-0004; Phase-3 task 9 per-odds-bucket calibration):
          1. an explicit ``override`` (tests / sensitivity sweeps) wins;
          2. else the per-odds-bucket value for ``odds_bucket`` -- resolved from the
             bet's ``o_dnb`` via the persisted bucket EDGES when ``odds_bucket`` is not
             supplied -- so a longshot's larger adverse move actually BITES;
          3. else the pooled value (the documented fallback when no bucket is known).
        """
        if override is not None:
            return float(override)
        bucket = odds_bucket
        if bucket is None:
            bucket = self.slippage.resolve_odds_bucket(float(o_dnb))
        return self.slippage.slippage_for_bucket(bucket)

    def effective_win_odds(
        self,
        o_dnb: npt.ArrayLike,
        *,
        slippage_value: float | None = None,
        odds_bucket: str | None = None,
    ) -> npt.NDArray[np.float64] | float:
        """Slippage- and leg-out-shaved effective WIN-leg decimal odds.

        The win leg fills at a price shaded adversely by the per-leg slippage (a
        relative move on the odds), and -- under the one-tick-adverse leg-out branch
        -- by one additional tick. The slippage applied is the PER-ODDS-BUCKET value
        resolved from the bet's price (or ``odds_bucket``), falling back to the pooled
        value only when the bucket is unknown (ADR-0004; Phase-3 task 9). The slippage
        is applied as a relative shave on ``o_dnb`` so a 5.23% move turns ``o_dnb`` into
        ``o_dnb*(1 - s)``. Floors at 1.0 (odds below evens never improve a back bet).

        ``slippage_value`` (scalar) overrides the resolved value for the whole array
        (tests / sensitivity sweeps); per-element bucket resolution is the ledger path
        (:meth:`net_return`), which calls this per bet.
        """
        o = np.asarray(o_dnb, dtype="float64")
        if slippage_value is not None:
            s: npt.NDArray[np.float64] | float = float(slippage_value)
        elif o.ndim == 0:
            s = self.slippage_value(float(o), odds_bucket=odds_bucket)
        else:
            s = np.array(
                [self.slippage_value(float(v), odds_bucket=odds_bucket) for v in o.ravel()],
                dtype="float64",
            ).reshape(o.shape)
        eff = o * (1.0 - np.asarray(s))
        if self.legout_model == "one_tick_adverse":
            eff = eff - self.one_tick
        eff = np.maximum(eff, 1.0)
        return float(eff) if eff.ndim == 0 else eff

    def net_return(
        self,
        o_dnb: float,
        gross_return: float,
        *,
        slippage_value: float | None = None,
        odds_bucket: str | None = None,
    ) -> float:
        """Net per-unit return from the settled GROSS return (settlement.py r_gross).

        ``gross_return`` is the per-unit gross multiple from settlement: ``o_dnb`` on
        a win, ``1.0`` on a push (stake refunded), ``0.0`` on a loss, ``1.0`` on a
        void/refund. The slippage applied is the per-odds-bucket value resolved from the
        bet's price (or the supplied ``odds_bucket``), pooled only as a fallback. The net
        per-unit return is:

          * WIN  (gross ~ o_dnb): the win fills at the slippage/leg-out effective odds
            ``o_eff``; on the EXCHANGE route the commission takes ``c*(o_eff - 1)`` of
            the net winnings, so net = ``1 + (1 - c)*(o_eff - 1)``; on the BOOK route
            net = ``o_eff`` (no commission).
          * PUSH / VOID (gross ~ 1.0): the synthetic DNB is TWO legs -- ``1/D`` on the
            draw, ``(D-1)/D`` on the win -- so a push refunds the stake only if BOTH legs
            filled at the quoted line (the atomic-fill idealization). Under the ATOMIC
            branch the push refunds exactly 1.0. Under the ONE-TICK-ADVERSE leg-out
            branch the draw leg fills at an adverse ``D'`` and the ``1/D`` draw stake
            returns ``D'/D < 1`` per unit, so the push refund is shaved by the draw-leg
            slippage: net push = ``1 - s`` (the omitted-push-leg cost ADR-0004 flags;
            ~p_draw * s per bet). Floored at 0 (a push cannot lose more than the stake).
          * LOSS (gross ~ 0.0): net 0.0 (the full stake is lost regardless of cost).

        Returned as a GROSS-CONVENTION multiple (incl. stake), matching
        ``settle_*_return`` so the ledger differences it to the net PROFIT the same way
        it differences the gross. Non-anticipation is preserved: this reads only the
        bet's odds and the (already-settled) gross outcome, never re-deciding the bet.
        """
        if not np.isfinite(gross_return):
            return float("nan")
        # Loss: full stake lost; cost cannot make it worse than 0 (no margin liability).
        if gross_return <= 0.0:
            return 0.0
        # Push / void / refund: gross 1.0. Atomic fill -> net 1.0 (stake returned). The
        # one-tick-adverse leg-out branch shaves the draw-leg fill, so the refunded draw
        # stake returns < 1 (the ADR-0004 push-leg execution cost, ~p_draw * slippage).
        if abs(gross_return - 1.0) <= 1e-12:
            if self.legout_model == "one_tick_adverse":
                s = self.slippage_value(o_dnb, odds_bucket=odds_bucket, override=slippage_value)
                return max(1.0 - s, 0.0)
            return 1.0
        # Win: re-price at the effective (slippage + leg-out) win odds.
        o_eff = float(
            self.effective_win_odds(o_dnb, slippage_value=slippage_value, odds_bucket=odds_bucket)
        )
        if self.route == "exchange":
            return 1.0 + (1.0 - self.commission_rate) * (o_eff - 1.0)
        return o_eff


def from_config(
    costs_cfg: Mapping[str, Any],
    *,
    legout_model: LegOutModel = "atomic_two_leg_fill",
    route: Literal["book", "exchange"] = "book",
    one_tick: float = 0.01,
    data_quality_report: Path | None = None,
    logs_dir: Path | None = None,
    open_close_moves: Mapping[str, Any] | None = None,
) -> CostModel:
    """Build a :class:`CostModel` from the config ``costs`` block + Phase-1 calibration.

    Reads ``costs.slippage_quantile`` (the selected empirical-quantile level; default
    p50 if unset -- the documented robust-location choice, calibrate_slippage),
    ``costs.bfec_commission_rate`` (validated within DATA §2.3 [2%,5%]). The slippage
    VALUE is calibrated from the open->close distribution (never asserted). ``one_tick``
    is the one-tick-adverse leg-out increment for the stress branch -- a market
    micro-structure constant (one decimal-odds tick), reported as the leg-out stress,
    not a tuned model parameter.
    """
    level = costs_cfg.get("slippage_quantile") or "p50"
    slip = calibrate_slippage(
        quantile_level=level,
        data_quality_report=data_quality_report,
        logs_dir=logs_dir,
        open_close_moves=open_close_moves,
    )
    rate = select_commission_rate(costs_cfg.get("bfec_commission_rate"))
    return CostModel(
        slippage=slip,
        legout_model=legout_model,
        one_tick=float(one_tick),
        commission_rate=rate,
        route=route,
    )
