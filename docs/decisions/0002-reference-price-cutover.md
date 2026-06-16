---
name: ADR-0002 — Season-conditional reference price cutover
description: Switch the closing reference price from Pinnacle to consensus at the 2025/26 season boundary
type: scope
status: accepted
date: 2026-06-16
supersedes:
superseded_by: ""
---

# ADR-0002 — Season-conditional reference price cutover

## Context

The strategy labels the underdog and prices the DNB off a single **closing reference price**
`refC_*` per match (design.md §2-§3). The project's efficient-market benchmark of record is the
**Pinnacle closing line** (`PSC*` for 1X2; `PCAHH`/`PCAHA` for AH) — a low-margin sharp book whose
closing line is the standard benchmark, and the source on which the load-bearing Hegarty-Whelan
evidence is built (DATA §2.1).

football-data.co.uk's own data index carries a notice, quoted verbatim (DATA §2.1 caveat;
[data.php](https://www.football-data.co.uk/data.php), accessed 2026-06-16): *"Since 23/07/2025
Pinnacle's public API for odds delivery has become unreliable meaning their odds are systematically
out of date relative to odds for other bookmakers, including both the pre-closing and closing odds.
Consequently they should be used with caution when undertaking any betting analyses, and are no
longer being included for the calculation of market average and maximum odds."*

This is load-bearing for the headline 2026 verdict: the 2026 World Cup hold-out (the block the
out-of-sample verdict rests on) is **post-cutover**, while the bulk of the estimation universe is
pre-cutover Pinnacle-referenced. A mis-dated or mis-transcribed notice — or a degradation that does
not actually null `PSC*` — would invert the 2026 verdict, so the notice provenance is a **hard
Phase-1 gate** (plan task 3.1): round-trip the exact text + date into the verification register,
archive a checksummed copy under `data/raw/provenance/`, and empirically confirm `PSC*` is
stale/missing in a downloaded 2025/26 file. This ADR records the decision the gate protects.

## Decision

The closing reference price is **season-conditional**, carried in a `refC_*` column plus a
`ref_book` provenance column:

- **Seasons ≤ 2024/25:** `refC_* = PSC*` (Pinnacle closing) — the efficient-market benchmark.
- **Seasons ≥ 2025/26** (including the 2025/26 domestic data and the 2026 World Cup window):
  `refC_* = AvgC*` (market-average closing; `MaxC*` or `BFEC*` as registered alternatives),
  which now **exclude** the stale Pinnacle leg per the notice. `PSC*` must **not** be used as the
  closing benchmark on or after 2025/26.
- **Cutover season:** 2025/26 = first season on the non-Pinnacle closing reference.
- **Late-domestic harmonization.** The late-league walk-forward window is also reported on the
  non-Pinnacle reference (`AvgC*`) so the train/test price basis is comparable for the 2026 transfer
  test (DATA §4.1). The Phase-1 common-basis-overlap decision rule (plan task 8 / acceptance)
  pre-commits — before scoring — to demote the 2026 transfer estimate to descriptive and let the
  2002-2022 Pinnacle-comparable WC block carry the primary transfer inference if the overlap fails
  its pre-registered adequacy criterion.

The reference choice is **not** a tunable selected on data; it is fixed by the vendor notice and the
season boundary. It is therefore not a multiple-testing family dimension.

## Consequences

- **Positive.** The reference is always the best available efficient price for its era; the 2026
  hold-out is not silently scored on a stale Pinnacle leg.
- **Negative / new obligations.** The train (predominantly Pinnacle `PSC*`) and 2026-test
  (consensus `AvgC*`) price bases differ in **level**, not just noise — Pinnacle's loss level is
  documented strictly below the market average (EDGE §2.3). A null/negative 2026 transfer could be a
  reference-basis artifact; this is de-confounded by the Phase-4 task-9 dual-reference re-scoring
  (native + harmonized) and the frozen Phase-1 common-basis-overlap rule.
- `AvgC*`/`MaxC*` are **consensus** prices, not a single sharp book; a max-odds column understates
  margin and is not a fair-price proxy, so the de-vig and FLB treatment is re-checked on the
  post-cutover segment (DATA §2.1).
- The downstream schema, push-frequency base rates, and PIT closing-price field all carry the
  season-conditional `refC_*` rather than always `PSC*` (DATA §5, §6, §7).

## Alternatives considered

- **Always `PSC*`.** Rejected: post-2025-07-23 Pinnacle closing odds are systematically stale per
  the vendor notice, so the 2026 hold-out would be scored on a degraded benchmark.
- **Always `AvgC*` (consensus) for all seasons.** Rejected: discards the sharp Pinnacle benchmark
  for the 20+ pre-cutover seasons where it is valid and is the basis of the cited evidence; would
  weaken the estimation universe's efficiency benchmark for no gain.
- **Drop 2025/26+ entirely.** Rejected: that would drop the 2026 World Cup, which is the held-out
  target of the whole project.

## References

- [research_data-availability_2026-06-16.md](../research/research_data-availability_2026-06-16.md) §2.1, §4.1, §5, §7 (season-conditional reference; cutover; Pinnacle degradation notice).
- [research_edge-flb-empirics_2026-06-16.md](../research/research_edge-flb-empirics_2026-06-16.md) §2.3 (Pinnacle loss level below market average).
- [plan_phased-workplan_2026-06-16.md](../protocol/plan_phased-workplan_2026-06-16.md) Phase 1 task 3.1 (provenance gate), task 8 (common-basis overlap), Phase 4 task 9 (reference-basis control).
- football-data.co.uk data index notice: [data.php](https://www.football-data.co.uk/data.php) (accessed 2026-06-16).
- Hegarty & Whelan 2025, Applied Economics, [10.1080/00036846.2025.2507979](https://doi.org/10.1080/00036846.2025.2507979) (Pinnacle below market average).
