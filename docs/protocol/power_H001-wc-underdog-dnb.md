---
title: Power analysis — H001-wc-underdog-dnb
date: 2026-06-16
hypothesis_id: H001-wc-underdog-dnb
type: power_analysis
status: frozen  # frozen pre-data, BEFORE any Phase 1 download
design_sha256: see ../protocol/design.md.sha256  # the design this record powers
frozen_sha256: null  # this file's SHA; see footer + power_H001-wc-underdog-dnb.md.sha256
---

# Power analysis for H001-wc-underdog-dnb

**Pre-data power record, frozen in Phase 0 BEFORE any Phase 1 download** (plan task 8;
[plan_phased-workplan_2026-06-16.md](plan_phased-workplan_2026-06-16.md)). Phase 4 only **re-runs**
this frozen calculation against the assembled `n`; it never re-derives `δ` or `Var_DNB`.

**Hoenig-Heisey 2001 compliance ([10.1198/000313001300339897](https://doi.org/10.1198/000313001300339897);
STAT §6.1).** Post-hoc / observed power is forbidden. The effect size `δ` and the per-bet variance
`Var_DNB` are sourced **exclusively** from the literature-anchored EDGE §5.2 analytic three-point
form evaluated at the prior-implied `(p_W, p_D, p_fav)` — **not** from the assembled panel's
realized overround, draw rate `q`, or DNB-variance distribution. Sequencing the freeze after data
assembly would let `δ`/`Var_DNB` be calibrated to what the data can deliver, which is the exact
contamination the prohibition targets.

## Pre-registered parameters

| Param | Value | Source |
|---|---|---|
| Effect of interest `δ` | **0.0089** (0.89 pp per-bet ROI)  # justify: smallest scientifically-meaningful POSITIVE edge = the only candidate-transferable favourable component, the price-based reverse-FLB cross-sectional gradient | EDGE §3.2/§3.5/§5.4/§7; design.md §1 H1 |
| Per-bet variance `Var_DNB` | **2.1764** (SD `σ_R` = 1.4753) | EDGE §5.2 three-point form; CALC §6.1 |
| `α` (two-sided) | 0.05  # justify: design.md §8 | design.md §8; STAT §6.2 |
| Power target `1 − β` | 0.80  # justify: design.md §8 | design.md §8 |
| Serial-dependence design effect `κ` | 1.0 (Gaussian lower bound); 1.22 illustrative (AR(1) ρ=0.1) | STAT §6.2 (LRV `κ = Ĵ/γ̂₀`, Newey-West 1994) |
| Test type | one-sample mean test on per-bet ROI, `H0: μ_R = 0` | design.md §5; STAT §6.2 |

## Effect size `δ` — provenance

The honest prior is null-to-small-negative (design.md §1; EDGE §7). Power is the ability to detect
a departure from `H0: μ_R = 0`, so the registered `δ` is the **smallest scientifically-meaningful
positive per-bet edge**. The only candidate-transferable favourable component in the corpus is the
**price-based reverse-FLB cross-sectional gradient** within the Asian-Handicap / DNB family:

`δ = 4.17% − 3.28% = 0.89 pp` (RBF/MPRA Table 7 weak* 3.28% vs strong* 4.17%; EDGE §3.2),

retained as the **sign/magnitude of within-market underdog favourability** (the 3.28% cell excludes
the zero handicap, so it indexes the gradient's size, not the AH-0.0 loss level — EDGE §3.2 caveat).
Two literature facts make even this an optimistic ceiling: (i) the gradient is **smaller than the
DNB margin itself** (~3.2-4.2% market-average; EDGE §3.5(ii)), so the strategy is net-negative in
expectation on domestic evidence; (ii) neutral-venue probability compression is expected to
**shrink** it at the World Cup (EDGE §4.2, §7). Larger literature-anchored edges (`+2/+5/+10/+15.5%`,
STAT §6.3 / DATA §3.3) are carried in the sensitivity grid below as the upper, less-plausible end.

## Per-bet variance `Var_DNB` — provenance and computation

`Var_DNB` is the EDGE §5.2 / CALC §6.1 **analytic three-point closed form**, evaluated at the
**prior-implied** probability triple — the EDGE §5.3 worked typical-WC-underdog example under the
designated-primary **Shin** de-vig (not a panel quantity):

- Prior 1X2 closing odds: `H = 1.70, D = 3.80, A = 5.50` (favourite ~59% raw, underdog ~18% raw).
- Synthetic DNB price (underdog = away): `o_DNB = A·(D−1)/D = 5.50·2.80/3.80 = 4.0526`, so
  `b = o_DNB − 1 = 3.0526`.
- Shin de-vig three-way fair probabilities (EDGE §5.3 primary row): `p_W = 0.1721`,
  `p_D = 0.2527`, `p_fav = 0.5752` (Σ = 1).
- Mean (prior EV per stake): `μ = p_W·b − p_fav = p_W·o_DNB − (1 − p_D) = −0.0498` (−4.98%;
  consistent with EDGE §5.3 Shin unconditional −5.0%; confirms the net-negative prior).

> `Var_DNB = p_W·b² + p_fav − μ² = 0.1721·3.0526² + 0.5752 − (−0.0498)² = 2.1764`,  `σ_R = 1.4753`.

This reconciles with the EDGE §5.2 cross-check (which reports `Var_DNB ≈ 2.21`, `SD ≈ 1.49` for the
same example under basic de-vig). The naive straight-win-bet identity `√(o_DNB − 1) = 1.747`
**overstates** the true unconditional DNB SD by ~18% — it is an upper bound only and is **not** used
here (CALC §6.2; EDGE §5.2). The refund mass `q = p_D` enters **inside** the three-point form (as
`p_D`), not as an external multiplier (EDGE §5.2).

## Required `n` (point estimate)

`n_required = κ · (z_{1−α/2} + z_{1−β})² · σ_R² / δ²`, with `(z_{1−α/2} + z_{1−β})² = (1.960 + 0.8416)² = 7.849`.

At the registered `δ = 0.89 pp`, `σ_R² = 2.1764`, `α = 0.05`, power = 0.80:

| `κ` | Source | Required `n` |
|---|---|---|
| 1.00 | Gaussian lower bound | **215,662 bets** |
| 1.22 | AR(1) ρ=0.1 illustrative inflation (STAT §6.2) | **263,108 bets** |

The Gaussian `n` is a **lower bound**; positive serial dependence (the expected sign under
tournament/round clustering) gives `κ > 1` and correctly enlarges it. The realized `κ` is the
HAC long-run-variance design effect computed in Phase 4 — it is the **only** quantity in this
record permitted to be estimated from the assembled panel; `δ` and `Var_DNB` are not.

## Sensitivity grid

Required `n` (κ = 1, three-point `Var_DNB = 2.1764`, α = 0.05, power = 0.80):

| `δ` (per-bet ROI) | Required `n` | Notes |
|---|---|---|
| 0.445 pp (50% of registered) | 862,649 | under-power case |
| 0.667 pp (75%) | 383,400 | |
| **0.890 pp (registered)** | **215,662** | transportable reverse-FLB gradient (EDGE §3.5) |
| 1.112 pp (125%) | 138,024 | |
| 1.335 pp (150%) | 95,850 | |
| 1.780 pp (200%) | 53,916 | over-power case |
| 2.00 pp | 42,707 | STAT §6.3 lower literature anchor |
| 5.00 pp | 6,833 | feasible only in the expanded league universe (10³-10⁴) |
| 10.00 pp | 1,708 | still > WC-only 384 |
| 15.50 pp | 711 | DATA §3.3 "smallest detectable on 384" anchor (computed there on the inflated `o−1` SD) |

**Minimum detectable `δ` on the World-Cup-only block** (`n = 384`, κ = 1, three-point `Var_DNB`):
`δ_min = √(7.849 · 2.1764 / 384) = 21.1 pp`. The WC-only sample is powered only to detect
implausibly large edges — the quantitative justification for expanding to the domestic-league
universe and holding the World Cup out (design.md §2; STAT §6.3; DATA §3.3).

## World-Cup stratification count `K_WC`

Restated from [config/multipletest_family.yaml](../../config/multipletest_family.yaml) (Phase 0
task 6) so the exploratory-layer effective-trials denominator is auditable here. The register is the
authoritative source; this record mirrors its **symbolic** form and pins no concrete integer:

> `K_WC = (stage cells) × (host cells) × (dead-rubber cells) × (odds-bucket cells)`
> `     = 2 × 2 × 2 × n_odds_buckets = 8 × n_odds_buckets`  (EDGE §4.3-§4.4 strata).

**No-magic-number provenance.** The stage (2: group/knockout), host (2: host/neutral), and
dead-rubber (2: live/dead) factors are fixed by the EDGE §4.3-§4.4 stratum definitions, giving the
resolved-cardinality base multiplier `8`. The **odds-bucket count `n_odds_buckets` is left
symbolic**: odds bucketing is an **empirical-quantile cut per division-season × reference regime**
(DATA §8; register `odds_bucket.grid: null`), so its cardinality cannot be fixed pre-data and has no
CV/quantile justification yet. `K_WC` is therefore pinned to a concrete integer only by the
register ([config/multipletest_family.yaml](../../config/multipletest_family.yaml),
`K_WC: null` until resolution) once `n_odds_buckets` resolves in Phase 1, before any WC number is
computed. The `K_WC` strata run as a **pre-registered BH-FDR-controlled exploratory layer**
(design.md §8, `bh_threshold = 0.10`) that **cannot upgrade the headline verdict** — they describe
*where* a candidate edge sits, not *that* it exists (STAT §7; Phase 0 task 6).

## Disposition

- **If realized `n` ≥ required `n` at the registered `δ`:** proceed (validate-data → inference).
- **If realized `n` < required `n` at the registered `δ`:** archive(null, underpowered) per
  design.md §10. The expanded league universe must reach the ~10³-10⁴ scale to have 80% power
  against a plausible single-digit-percent edge; even then the 0.89 pp transportable gradient
  (requiring ~2×10⁵ bets) is below the detection floor of any realistic universe, which is itself
  the honest finding (design.md §1; EDGE §7).

## References

- Hoenig, J. M., & Heisey, D. M. (2001). The Abuse of Power. *Am. Stat.* 55(1):19-24.
  [10.1198/000313001300339897](https://doi.org/10.1198/000313001300339897) — post-hoc power is
  uninformative; do not report it.
- Hegarty, T., & Whelan, K. (2025). Forecasting Soccer Matches with Betting Odds: A Tale of Two
  Markets. *Int. J. Forecasting* 41(2):803-820. [10.1016/j.ijforecast.2024.06.013](https://doi.org/10.1016/j.ijforecast.2024.06.013).
- Whelan, K., & Hegarty, T. (2024). Returns on Complex Bets: Evidence from Asian Handicap Betting
  on Soccer. *Rev. Behav. Finance* 16(5):904-924. [10.1108/RBF-11-2023-0314](https://doi.org/10.1108/RBF-11-2023-0314).
- Štrumbelj, E. (2014). On Determining Probability Forecasts from Betting Odds. *Int. J.
  Forecasting* 30(4):934-943. [10.1016/j.ijforecast.2014.02.008](https://doi.org/10.1016/j.ijforecast.2014.02.008).
- Newey, W. K., & West, K. D. (1994). Automatic Lag Selection in Covariance Matrix Estimation.
  *Rev. Econ. Stud.* 61(4):631-653. [10.2307/2297912](https://doi.org/10.2307/2297912).

## Reproducibility

Frozen pre-data; its SHA-256 (footer + sidecar
[power_H001-wc-underdog-dnb.md.sha256](power_H001-wc-underdog-dnb.md.sha256)) is recorded in the
freeze ReproLog `config_resolved_sha256` **before** Phase 1 begins. ReproLog path:
`logs/reprolog_<run_id>.json` (phase = validation; hypothesis_id = H001-wc-underdog-dnb;
`rng_seed` = the root seed from `config/baseline.yaml`). git HEAD is null / "UNCOMMITTED" with
`git_dirty=true` while the repo has zero commits (the emitter handles this state).

---

## Freeze record (immutable once set)

- **HID:** `H001-wc-underdog-dnb`
- **`δ` = 0.0089 (0.89 pp);  `Var_DNB` = 2.1764 (σ_R = 1.4753);  α = 0.05;  power = 0.80**
- **Required `n` = 215,662 (κ=1) / 263,108 (κ=1.22);  K_WC = 8 × n_odds_buckets, pinned in config/multipletest_family.yaml when n_odds_buckets resolves in Phase 1**
- **power record SHA-256:** see sidecar [power_H001-wc-underdog-dnb.md.sha256](power_H001-wc-underdog-dnb.md.sha256);
  recorded in the freeze ReproLog `config_resolved_sha256`.
