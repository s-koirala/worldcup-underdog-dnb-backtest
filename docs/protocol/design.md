---
name: H001-wc-underdog-dnb — World-Cup underdog Draw-No-Bet edge
description: Frozen pre-registration record for the underdog Draw-No-Bet World-Cup backtest
type: project
hypothesis_id: H001-wc-underdog-dnb
tier: primary
status: designed  # designed | running | evaluated | archived(positive|null|negative)
owner: SKIE
created: 2026-06-16
citations:
  - "10.1016/j.ijforecast.2024.06.013"   # Hegarty & Whelan 2025, Tale of Two Markets (IJF)
  - "10.1108/RBF-11-2023-0314"            # Whelan & Hegarty 2024, Returns on complex bets (RBF)
  - "10.1080/00036846.2025.2507979"       # Hegarty & Whelan 2025, Estimating Expected Loss Rates (Applied Economics)
  - "10.1016/j.ijforecast.2014.02.008"    # Strumbelj 2014, probability forecasts from odds (Shin primary)
  - "10.2307/2234526"                     # Shin 1992
  - "10.2307/2234240"                     # Shin 1993
  - "10.1086/655844"                      # Snowberg & Wolfers 2010 (FLB mechanism)
  - "10.1111/1467-9485.00151"             # Cain, Law & Peel 2000 (1X2 FLB)
  - "10.1198/000313001300339897"          # Hoenig & Heisey 2001 (post-hoc power prohibition)
external_doi: null  # set on later OSF upload; internal-only for now
frozen_sha256: null  # see footer + design.md.sha256; recorded in the freeze ReproLog config_resolved_sha256
immutable: true
---

# H001-wc-underdog-dnb — World-Cup underdog Draw-No-Bet edge

This document is the pre-registration record for hypothesis `H001-wc-underdog-dnb`. **It is
frozen at `designed` status and is IMMUTABLE once frozen: any change after the freeze SHA-256
is recorded requires a new hypothesis ID, not an edit here.** The freeze SHA is the
tamper-evident anchor (footer + sidecar [design.md.sha256](design.md.sha256), and the
`config_resolved_sha256` field of the freeze ReproLog). Built per the Phase 0 task 5 spec of
[plan_phased-workplan_2026-06-16.md](plan_phased-workplan_2026-06-16.md) and the SKIE 11-section
pre-registration template; the field content is specialised to the Draw-No-Bet betting
instrument (the generic triple-barrier ML fields are replaced by the betting analogues below).

Quant-project rules apply ([rules/quant-project.md](../../../.claude/rules/quant-project.md)):
no look-ahead, walk-forward CV, HAC inference, bootstrap CIs on Sharpe, White/Hansen
multiple-testing, no magic numbers.

## 1. Hypothesis

- **H0:** the population mean per-bet net-of-cost ROI of the closing-line underdog Draw-No-Bet
  strategy at the FIFA men's World Cup is `μ_R = 0` (no edge).
- **H1:** `μ_R = δ > 0` — a small positive per-bet edge of the smallest scientifically-meaningful
  size `δ`, anchored to the literature-derived transportable reverse-FLB gradient (the pre-data
  effect of interest is fixed in [power_H001-wc-underdog-dnb.md](power_H001-wc-underdog-dnb.md),
  not here, and is never re-derived from the assembled panel — Hoenig & Heisey 2001).
- **Mechanism.** In the 1X2 (retail) market the favourite-longshot bias makes the underdog the
  *dearer* side (longshot loss ~9-10% vs favourite ~6%; Snowberg & Wolfers 2010; Cain-Law-Peel
  2000; EDGE §1.3). In the Asian-Handicap / Draw-No-Bet family the bias is absent-to-weakly-reverse
  and the underdog is the *cheaper* side (RBF 2024 integer/full-refund loss 3.24%; the
  zero-handicap-excluded weak/strong cross-sectional gradient ~0.9 pp; EDGE §3.2-§3.5). The
  candidate edge is whether that within-AH-market reverse gradient, plus any World-Cup-specific
  dislocation (neutral-venue compression, dead-rubber motivation, public over-backing of glamour
  favourites; EDGE §4, §5.4), is large enough to cross zero net of margin and execution cost.
- **Honest prior (load-bearing).** A wide CI around zero, most plausibly net-negative EV: the
  transportable favourable gradient (~0.9 pp) is smaller than the DNB margin itself (~3.2-4.2%
  market-average; lower at Pinnacle), and neutral-venue compression is expected to shrink it
  further (EDGE §3.5, §7). The most likely honest verdict is `λ* = 0` (do not bet). This
  pre-registration exists to prevent reverse-engineering a surviving cell.
- **Primary citations:** Hegarty & Whelan 2025 (IJF, [10.1016/j.ijforecast.2024.06.013](https://doi.org/10.1016/j.ijforecast.2024.06.013));
  Whelan & Hegarty 2024 (RBF, [10.1108/RBF-11-2023-0314](https://doi.org/10.1108/RBF-11-2023-0314));
  Štrumbelj 2014 ([10.1016/j.ijforecast.2014.02.008](https://doi.org/10.1016/j.ijforecast.2014.02.008));
  Shin 1992/1993 ([10.2307/2234526](https://doi.org/10.2307/2234526), [10.2307/2234240](https://doi.org/10.2307/2234240)).

## 2. Universe and sample period

Bounded at pre-registration; no discretion later. Walk-forward only — never k-fold
(methodology.md §2).

- **Instruments.** Draw-No-Bet (= Asian Handicap 0.0) on the **underdog** side, settled on the
  90-minute result. The DNB price is the **quoted AH-0 closing price where present**, otherwise
  the **synthetic** price `o_DNB = W·(D−1)/D` from the closing 1X2 book (CALC §3.1-§3.4; §3 below).
- **Frequency.** Per-match (one bet per eligible match); the inferential unit is the **bet**
  (pre-registered; the block bootstrap must match — STAT Open Question 4).
- **Session / decision line.** The **closing** line only (most efficient pre-match price,
  computable at kickoff; Štrumbelj 2014; CALC §2.1). No opening-line entry in the headline.
- **Estimation universe (train + validation).** Domestic European leagues, football-data.co.uk
  Main + Extra, Pinnacle closing 1X2 + Asian-Handicap with the **season-conditional reference
  price** (`PSC*` for seasons ≤ 2024/25; `AvgC*`/`MaxC*`/`BFEC*` for ≥ 2025/26 per the
  2025-07-23 Pinnacle-feed degradation — DATA §2.1; [ADR-0002](../decisions/0002-reference-price-cutover.md)).
  First season is fixed empirically by the ≥95% `refC_*` coverage gate (Phase 1).
- **Test window (held out, never touched).** The **FIFA men's World Cup** — the 2002-2022 editions
  (~384 clean-odds matches) as the Pinnacle-comparable held-out block, and the 2026 edition
  (post-cutover, non-Pinnacle reference) as a regime-confounded edition demoted per the Phase-1
  common-basis-overlap rule. Scored **exactly once**, after the design and the multiple-testing
  family are frozen.
- **Roll-handling.** Expanding-window walk-forward, folds cut on league **season boundaries**;
  the World Cup is the final fold (methodology.md §2).

## 3. DNB construction (replaces generic "features")

- **Underdog side definition (frozen).** The side with the **higher decimal win price**
  (equivalently the lower raw implied win probability `1/o`); `argmax(refC_H, refC_A)` evaluated at
  kickoff on the season-conditional reference price (CALC §2.1; DATA §5.3). The American +/- sign
  is unreliable in a three-way book and is not used (CALC §2.2).
- **DNB price (frozen).** Quoted AH-0 closing price (`AHCh = 0` / `PCAHH`/`PCAHA`, exact code pinned
  in Phase 1 task 2.1) when present; otherwise the synthetic identity
  `o_DNB = W·(D−1)/D = W·(1 − r_D)` (CALC §3, no-arbitrage replication proof §3.3). The quoted
  (tradable) line is preferred; the synthetic is a fallback/cross-check and the
  `M_1X2 − M_AH` margin wedge is logged (CALC §3.5).
- **De-vig to fair `(p_W, p_D, p_fav)` (frozen a priori — NOT a per-fold selected dimension).**
  Primary = **Shin (1992/1993)** run on the **three-way** 1X2 book (best soccer-odds calibration,
  Štrumbelj 2014; not on the under-round draw-dropped residual — CALC §4.2), forming the
  conditional `q_W = p_W/(1 − p_D)`. **Power** and **basic** are pre-registered **sensitivity
  branches**, registered in the family but never selected by the walk-forward (CALC §4.6). The
  Phase-2 per-training-fold calibration diagram (reliability + Brier + RPS, World Cup and post-fold
  seasons excluded) is the recorded justification for the Shin freeze, not a re-selection step.
- **Underdog near-tie rule (frozen branch — Phase 0 task 4.2).** **Chosen branch: the searched
  coin-flip exclusion band.** A `min_price_gap` parameter `τ_tie` (a coin-flip exclusion band on
  `|refC_H − refC_A|`) is **swept on the same walk-forward CV as the underdog-strength threshold
  `τ`**, not hand-set (selected by the §D.3 sensitivity sweep, reported with bettable-`n`
  sensitivity; DATA Open Question 6, EDGE Open Question 6). Because it is searched, `τ_tie` is
  **registered as a family dimension** in [config/multipletest_family.yaml](../../config/multipletest_family.yaml)
  and counted in `K` (the strict-tie-only `require_strict_underdog` branch is **not** taken). The
  config and this design agree: the strict-tie-only flag is superseded by the swept band.

## 4. Settlement (replaces generic "label construction")

- **Settlement convention (frozen).** The **90-minute result** (= normal time + stoppage,
  excluding extra time, penalty shootout, golden goal — Pinnacle/Betfair/William Hill rules;
  CALC §10; [ADR-0003](../decisions/0003-90min-settlement.md)).
- **Three-way DNB map.** Underdog wins in 90' → `o_DNB`; 90-minute draw → `1.0` (push / refund);
  favourite wins in 90' → `0`. A penalty-decided `1–1` is a **push**, never an underdog win/loss.
- **Knockout handling.** Use the 90-minute score; ET/penalties affect progression only, never
  settlement. Void/abandoned → refund and excluded from the win-ratio denominator.

## 5. Estimator and selected parameters (replaces generic ML estimator)

- **Strategy class.** Stake the underdog DNB at the closing line; staking scheme drawn from the
  five-scheme menu `{flat, fixed_fraction (φ), level-stake-to-odds (c ∝ 1/(d−1)), kelly (f*),
  fractional_kelly (λ·f*)}` (methodology.md §1.2; STAKE §2, §7.1; Phase 0 task 4.1). The
  three-outcome push-Kelly is `f* = (p_W·b − p_fav)/[b(p_W + p_fav)]`, `b = o_DNB − 1`; negative
  edge → `f* = 0` (no short side; CALC §7, STAKE §3).
- **Out-of-fold selection set (frozen): `{τ, φ, c, λ, τ_tie}`.** Selected purely out-of-fold on
  the league universe by walk-forward CV; objective = out-of-fold drawdown-constrained log-growth
  (methodology.md §2). **De-vig is NOT in this set** (frozen a priori, §3). `λ` is data-derived
  (Bayesian shrinkage `λ ≈ 1/(1+CV²)` and/or the binding Busseti-Ryu-Boyd drawdown constraint;
  STAKE §4, §6.2), not hand-set.
- **No magic numbers.** Every tunable above is grid/CV/bootstrap selected with a documented
  rationale; values are left `null` placeholders in `config/baseline.yaml` until the empirical
  search fills them. The single exemption is the RNG root seed (arbitrary-but-fixed, recorded,
  never tuned; Phase 0 task 9.1).

## 6. Splitter

- **Splitter.** Expanding-window walk-forward, time-ordered, disjoint, season-boundary folds; the
  World Cup is the final never-touched fold (methodology.md §2).
- **Purge / embargo.** Folds are cut on season boundaries, so a single competition is never split
  across train/test; any residual embargo is data-driven (residual PACF vs Politis-White block
  length, max). No look-ahead: every feature computable at kickoff from closing odds only.
- **Fold count.** = number of complete estimation seasons minus the seed season; the exact season
  list and fold count are fixed in [config/multipletest_family.yaml](../../config/multipletest_family.yaml)
  so the CV design is part of the pre-registered family.

## 7. Cost model

The transaction-cost / execution model is **mandated** (quant reporting rule) and specified in
[ADR-0004](../decisions/0004-transaction-cost-execution-model.md) (stub; calibrated in Phase 3).
**No ROI / Sharpe / growth number is reported as net until the `costs` block is applied.**

- **`cost_model_id`:** `costs.dnb_two_leg.v0` (to be versioned on Phase-3 calibration).
- **Components (three, per ADR-0004):** (i) per-leg slippage calibrated from the open→close move
  distribution (Phase 1 task 9.1), magnitude a data-selected quantile (§D.3), not a literal; (ii)
  the two-leg leg-out idealization (atomic two-leg fill at the closing line) stress-tested by a
  one-tick adverse-move sensitivity; (iii) the Betfair-exchange commission (2-5%, DATA §2.3)
  converted to an effective overround and reconciled with the `M_1X2 − M_AH` wedge (CALC §3.5).
- **Slippage model version / commission schedule source:** `null` placeholders frozen here; filled
  by Phase 3 from the Phase-1 distribution and the DATA §2.3 commission range.

## 8. Gate thresholds

Pre-registered; deviations require a `# justify:` note and citation.

- **`alpha`:** `0.05` (two-sided), the conventional Type-I error for the headline mean/ROI test
  (STAT §6.2). The headline edge null is screened with White Reality Check / Hansen SPA over the
  family `K` (STAT §7).
- **`bh_threshold` (BH-FDR, exploratory layer):** `0.10` for the World-Cup stratified sub-analyses
  (the `K_WC` cells), which **cannot upgrade the headline verdict** (STAT §7; Phase 0 task 6).
- **`dsr_activation` (Deflated Sharpe):** the binding significance gate; `SR₀ = E[max SR]` over the
  **pre-registered conservative raw-`N`** effective-trial count (Phase 0 task 6.2 — DSR is reported
  as a lower bound on significance), HAC-inflated denominator (STAT §8; ARCH §6.3).
- **Power target:** `0.80` (`1 − β`), fixed pre-data; the required-`n` calculation is frozen in
  [power_H001-wc-underdog-dnb.md](power_H001-wc-underdog-dnb.md) with `δ` and `Var_DNB` from the
  EDGE §5.2 analytic three-point form, never the panel.

## 9. Stopping rule

- **Stop criterion.** Fixed walk-forward fold count (no "train until Sharpe crosses X"; Sharpe is
  reporting-only, never an optimisation target). The World Cup is scored once after the design and
  family are frozen.
- **Max folds.** = the season-boundary fold count fixed in the register (§6).
- **Futility.** If realized `n < n_required_for_power_80` at the registered `δ`
  ([power_H001-wc-underdog-dnb.md](power_H001-wc-underdog-dnb.md)), the disposition is
  archive(null, underpowered) per §10.

## 10. Decision rule

Mapping from gate outcome to archival label; null results stay in the register (non-loss policy).

- **If the White/Hansen-corrected, HAC-inflated DSR rejects the no-edge null (`passed=True`):**
  archive(positive); report `λ*` and the bankroll required, net-of-cost, under both the atomic-fill
  idealization and the one-tick adverse stress.
- **If `passed=False` and the CI excludes zero but SPA fails:** archive(null) with a
  multiple-testing note.
- **If `passed=False` and the CI covers zero:** archive(null); the honest verdict is `λ* = 0` (do
  not bet) — the pre-committed most-likely outcome (A.2.4).
- **If realized `n < n_required_for_power_80`:** archive(null, underpowered).

## 11. Reproducibility commitments

Per [CLAUDE.md](../../CLAUDE.md) and the 13-named-key ReproLog schema (Phase 0 Methods).

- **git HEAD (at run):** auto-populated (`git_head`; null / "UNCOMMITTED" while the repo has zero
  commits — the emitter handles the pre-first-commit state, with `git_dirty=true`).
- **`pip freeze` SHA-256 (at run, 64-hex):** auto-populated (`pip_freeze_sha256`).
- **RNG seed:** the root seed in `config/baseline.yaml` (`rng_seed`)  # justify: arbitrary-but-fixed,
  recorded, never tuned; exempt from no-magic-number per Phase 0 task 9.1.
- **Dataset checksums:** frozen at validation from normalized (LF) bytes / canonicalized parquet
  (`dataset_checksums`); the WC raw pull is reproducible-from-snapshot (pinned checksum), not
  reproducible-from-source.
- **Reproducibility log path:** `logs/reprolog_<run_id>.json`.
- **Design.md SHA at freeze:** recorded in the footer below, in the sidecar
  [design.md.sha256](design.md.sha256), and as the freeze ReproLog `config_resolved_sha256`.

---

## Freeze record (immutable once set)

- **HID:** `H001-wc-underdog-dnb`
- **Freeze date:** 2026-06-16
- **design.md SHA-256:** see sidecar [design.md.sha256](design.md.sha256). This file is immutable
  once the SHA is recorded; the SHA is the `config_resolved_sha256` of the freeze ReproLog. Any
  substantive change requires a new HID.
