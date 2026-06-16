---
name: ADR-0004 — Transaction-cost / execution model (STUB)
description: Three-component execution-cost model for the two-leg synthetic DNB; specified here, calibrated in Phase 3
type: execution
status: proposed  # STUB — components named; calibration + costs config populated in Phase 3
date: 2026-06-16
supersedes:
superseded_by: ""
---

# ADR-0004 — Transaction-cost / execution model (STUB)

> **This is a STUB (plan task 7.1).** It names the three components to be decided and the `costs`
> config block to be populated, and records the reporting precondition. The model is **specified
> and calibrated in Phase 3** (plan methods + task 9) and made a precondition for net metrics in
> Phase 4/5. The decision is recorded from the start so the quant-reporting-rule transaction-cost
> field is never a bare label.

## Context

The quant reporting rule mandates a transaction-cost model, but the research corpus carries only a
report-card label and STAKE Open Question 8 — no calibrated spec. The instrument makes this
load-bearing: the synthetic DNB is a **two-leg** position — stake `1/D` on the draw and `(D−1)/D`
on the win (CALC §3.1, §5.1) — and the EV identity `o_DNB = W·(D−1)/D` assumes **both legs fill at
the quoted closing line simultaneously at zero slippage**. That idealization must be modeled and
stressed, not assumed.

This is load-bearing for the honest verdict (design.md §1; A.2): the EV prior is already
net-negative **gross** (~−5% under the primary Shin de-vig; CALC §8.2; EDGE §5.3), and execution
cost can only deepen it. A "do not bet" verdict (`λ* = 0`) must therefore be defended on
**net-of-cost, executable** terms, not on the idealized synthetic instrument.

## Decision

A `costs` config block plus a `pricing`/`ledger` cost hook implements three components (to be
populated/calibrated in Phase 3; magnitudes are config tunables with documented selection
rationale, never literals in code):

1. **Per-leg slippage.** Calibrated from the **open→close move distribution** observed on the
   football-data Main leagues (Phase 1 task 9.1; both pre-match `PSH/PSD/PSA` and closing
   `refC_*` exist there), per division-season × reference regime × odds bucket. The applied
   slippage is a **data-selected quantile of the absolute open→close move** (the §D.3 selection
   procedure — empirical-quantile with documented rationale and citation), applied to each leg's
   effective fill price. **Not a magic number** — left a `null` placeholder until Phase 1 supplies
   the distribution.
   - **Applied PER ODDS BUCKET, not pooled (Phase 3, decided).** The per-bucket calibration is
     *applied*, not merely collected: `src.ingest.open_close_moves` persists the underdog-price
     quantile **edges** (`odds_bucket_edges`) alongside the per-bucket move quantiles; the cost
     model (`SlippageCalibration.resolve_odds_bucket` / `slippage_for_bucket`) maps each bet's
     **underdog 1X2 closing price** (the bucket-cut variable) to its bucket and shaves by that
     bucket's slippage (e.g. longshot `bucket_4` p50 ≈ 6.8 % vs pooled ≈ 5.2 %), falling back to
     the pooled value only when the bucket is unknown (out-of-edges prices clamp to the nearest
     bucket). The bucket is threaded through `src.ledger.build_ledger` and the `src.run` risk
     engines per bet, so the per-division-season × odds-bucket calibration the plan mandates
     actually bites. The bucket is resolved from the **underdog 1X2 price**, not the DNB composite
     `o_dnb` (a different price object); see the magnitude note below.
2. **Leg-out assumption.** Default: **atomic two-leg fill at the closing line**, stated explicitly
   as an **idealization**, and **stress-tested by a one-tick adverse-move sensitivity** — re-price
   with the win leg (and the draw leg) filling one tick worse after the other fills, bounding the
   cost of non-simultaneous (leg-out) execution. Net metrics are reported under **both** the
   atomic-fill idealization and the one-tick adverse stress.
   - **Both legs modeled in the stress branch (Phase 3, decided).** The synthetic DNB is two legs
     (`1/D` on the draw + `(D−1)/D` on the win). The win-leg slippage shades the **win** payoff;
     the draw-leg slippage shades the **push** payoff: on a 90-minute draw (~26 % of bets) the
     `1/D` draw stake refunds `D'/D < 1` per unit if the draw leg filled at an adverse `D'`. Under
     the **one-tick-adverse** branch the push return is therefore `1 − s` (not an exact `1.0`),
     carrying the modeled push-leg execution cost ≈ `p_draw · s` ≈ 0.26 · 0.052 ≈ 1.4 % per bet.
     Under the **atomic-fill** idealization the push still refunds exactly `1.0` (both legs at the
     quoted line by assumption). This removes the prior downward bias whereby the push state carried
     zero execution cost regardless of the leg-out branch.

   **Slippage magnitude semantics (Phase 3, documented conservative bias).** The applied slippage
   is the **median of the absolute (two-sided)** open→close relative move, applied **one-directionally**
   as adverse slippage on the DNB composite. Two approximations, both **cost-overstating** (conservative)
   and stated rather than hidden:
   - *Two-sided → one-sided.* For a roughly symmetric move, the median |move| is ≈ 2× the expected
     adverse-only drift, so this over-charges execution cost by up to ≈ 2×. Adopted deliberately:
     net-of-cost is the precondition for the honest verdict, and over-charging cost makes a
     `λ* = 0` "do not bet" verdict **harder** to overturn (a conservative bias on the load-bearing
     direction), not easier. The signed adverse-tail half of the move is the less-conservative
     refinement, **not** adopted; the directional bias is the deliberate choice.
   - *1X2 leg → DNB composite.* The move is measured on the 1X2 win-side closing prices and applied
     as a relative shave on `o_dnb = A·(D−1)/D`. Because the DNB price is a monotone function of the
     same 1X2 legs, a relative move on the win leg maps to first order onto the composite; the bucket,
     however, is resolved from the **underdog 1X2 price** the move was estimated on (component 1).
   - *Sensitivity reported.* The p50/p90/p95/p99 slippage ladder is the reported magnitude
     sensitivity, so the net verdict's dependence on the slippage quantile/definition is visible.
     A 5.23 % shave cuts net win profit `b` by ≈ 8.3 % of its value — load-bearing relative to the
     ≈ 0.93 % candidate reverse-FLB edge — which is precisely why the conservative direction is chosen.
3. **Betfair-exchange (BFEC) commission as an effective overround.** The exchange fallback carries
   **2-5% commission on net winnings, not overround** (DATA §2.3). Convert the commission to an
   **effective overround** on the exchange DNB and **reconcile it against the synthetic-vs-quoted
   margin wedge `M_1X2 − M_AH`** (CALC §3.5; quantified Phase 1 task 9), so the exchange-route cost
   is on the same footing as the quoted/synthetic-route cost.

`costs` config block (Phase-0 skeleton; all magnitudes `null` until Phase 3):

```yaml
costs:
  model_id: costs.dnb_two_leg.v0
  slippage:
    source: open_close_move_distribution   # Phase 1 task 9.1
    selection: empirical_quantile           # §D.3; quantile level filled by search
    quantile_level: null                    # data-selected, not asserted
    per_leg: true
  leg_out:
    fill_mode: atomic_two_leg_close         # idealization (default)
    stress: one_tick_adverse                # reported alongside the idealization
  commission:
    venue: betfair_exchange
    rate: null                              # 2-5% range (DATA §2.3); reconciled vs M_1X2 - M_AH
    as_effective_overround: true
  report_net: required_before_headline      # see reporting precondition below
```

**Reporting precondition (binding).** **No ROI / Sharpe / growth number is reported as net until
this block is populated and applied** (Phase 4/5 acceptance). Gross figures may be shown only
alongside their net counterparts and explicitly labelled gross; every headline metric is net, under
both the atomic-fill idealization and the one-tick adverse stress.

## Consequences

- **Positive.** The honest verdict rests on the tradable instrument, not the idealized synthetic
  one; the slippage magnitude is data-derived (no magic number); the exchange and quoted/synthetic
  routes are cost-comparable via the effective-overround reconciliation.
- **New obligations.** Phase 1 must supply the open→close move distribution (task 9.1) and the
  `M_1X2 − M_AH` wedge (task 9); Phase 3 must implement the cost hook so every ledger PnL entry
  carries gross **and** net values; Phase 4 metrics consume net only.
- **Negative.** Adds a calibration dependency before any net number can be reported; deepens the
  already-negative gross EV prior — which is the intended honest accounting, not a defect.

## Alternatives considered

- **Zero-cost / gross-only reporting.** Rejected: violates the quant reporting rule and would
  present an un-tradable idealization as the headline; the synthetic identity's zero-slippage
  simultaneous-fill assumption is counterfactual.
- **A single asserted slippage / commission constant.** Rejected: a magic number; the slippage must
  be selected from the empirical open→close distribution and the commission taken from the DATA §2.3
  range with documented rationale.
- **Atomic-fill only (no leg-out stress).** Rejected: the two-leg synthetic carries genuine
  non-simultaneous-fill (leg-out) risk; the one-tick adverse stress bounds it and must be reported.

## References

- [plan_phased-workplan_2026-06-16.md](../protocol/plan_phased-workplan_2026-06-16.md) Phase 0 task 7.1 (this stub), Phase 1 tasks 9 / 9.1, Phase 3 methods + task 9, §D.9 (net-of-cost accounting).
- [research_dnb-odds-calculations_2026-06-16.md](../research/research_dnb-odds-calculations_2026-06-16.md) §3.1, §3.5, §5.1, §8.2-§8.3 (two-leg construction; margin wedge; gross EV).
- [research_data-availability_2026-06-16.md](../research/research_data-availability_2026-06-16.md) §2.1, §2.3 (open/close prices on Main; Betfair commission 2-5%).
- [research_edge-flb-empirics_2026-06-16.md](../research/research_edge-flb-empirics_2026-06-16.md) §5.3 (gross synthetic-DNB EV ~−5% under Shin).
