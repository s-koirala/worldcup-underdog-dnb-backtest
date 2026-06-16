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
2. **Leg-out assumption.** Default: **atomic two-leg fill at the closing line**, stated explicitly
   as an **idealization**, and **stress-tested by a one-tick adverse-move sensitivity** — re-price
   with the win leg (or draw leg) filling one tick worse after the other fills, bounding the cost
   of non-simultaneous (leg-out) execution. Net metrics are reported under **both** the atomic-fill
   idealization and the one-tick adverse stress.
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
