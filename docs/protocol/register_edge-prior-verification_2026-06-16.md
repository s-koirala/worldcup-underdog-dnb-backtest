---
title: Edge-prior primary-source verification register — H001-wc-underdog-dnb
date: 2026-06-16
hypothesis_id: H001-wc-underdog-dnb
type: verification_register
status: phase1_gate_satisfied  # working-paper cells confirmed; RBF published-version round-tripped
plan_task: "Phase 1 task 11 (gate; promoted from Phase 5)"
frozen_sha256: null  # this file's SHA; recorded in the validate-stage ReproLog config_resolved_sha256
---

# Edge-prior primary-source verification register

**Phase-1 GATE (plan task 11; [plan_phased-workplan_2026-06-16.md](plan_phased-workplan_2026-06-16.md) Phase 1 Methods, "Edge-prior primary-source verification").** The entire edge-sign hypothesis (whether underdog DNB carries the lowest AH-loss cell / a weak reverse-FLB) and the upstream quantities frozen before Phase 1 — the worked EV prior ([design.md](design.md) §1; EDGE §5) and the pre-data power `δ`/`Var_DNB` ([power_H001-wc-underdog-dnb.md](power_H001-wc-underdog-dnb.md); Phase 0 task 8) — rest on three Hegarty–Whelan magnitudes. A single transcription error in the **3.24% vs 3.28%** pair inverts the edge prior (3.24% = RBF 2024 integer-handicap, the DNB-family anchor; 3.28% = the MPRA/IJF weak-team cell, which **excludes** the zero handicap). These cells are therefore round-tripped against the source of record **before any World-Cup number is computed and before the EV prior / power `δ` are relied on downstream**.

This register's SHA-256 is recorded in the validate-stage ReproLog (`config_resolved_sha256` reference), per the plan acceptance criterion: "the edge-prior verification register (task 11) is complete and SHA-referenced in the ReproLog before any World-Cup number is computed." Note the World-Cup transfer test is additionally PENDING-ODDS (no headless WC-odds source; [note_wc-odds-gap_2026-06-16.md](note_wc-odds-gap_2026-06-16.md)), so no WC number has been computed; this gate is satisfied prospectively, as the plan requires.

## Cell 1 — RBF 2024 integer-handicap loss (the DNB-family anchor)

- **Citation 5.** Hegarty, T., & Whelan, K. (2024). *Returns on complex bets: evidence from Asian Handicap betting on soccer.* **Review of Behavioral Finance** 16(5):904–924. DOI [10.1108/RBF-11-2023-0314](https://doi.org/10.1108/RBF-11-2023-0314).
- **Table of record:** Table 2, "Average loss rates from placing an equal amount on all bets, by Asian Handicap type" (market-average closing odds across the football-data.co.uk surveyed books).
- **Cell values (verbatim):**

  | Handicap type | Integer (full-refund possible — includes AH 0.0) | Ends .25 | Ends .5 (no refund) | Ends .75 |
  |---|---|---|---|---|
  | Mean loss rate | **0.0324** (3.24%) | 0.0361 | 0.0416 | 0.0357 |
  | N (matches) | 23,730 | 29,250 | 20,762 | 10,488 |

- **Table 3:** the Integer-vs-.5 difference is **−0.0093, p = 0.0000** (the integer/full-refund line is the low-loss end).
- **The 3.24% integer/full-refund cell is the DNB-family loss prior** (the AH-0.0-relevant cell), carried into the EV prior and the power `Var_DNB` provenance.
- **Round-trip status — CONFIRMED at the working-paper PDF AND the published version of record.**
  - Working-paper PDF (karlwhelan.com), 2026-06-16: Integer 0.0324, .25 0.0361, .5 0.0416, .75 0.0357; Table 3 Integer-vs-.5 −0.0093 (p=0.0000). CONFIRMED verbatim.
  - **Published-version journal page (emerald.com/rbf/article/16/5/904-924), re-confirmed 2026-06-16 via WebFetch:** the article is **Open Access (CC BY 4.0)**; **Table 2 reads Integer 3.24%, Ending 0.25 3.61%, Ending 0.5 4.16%, Ending 0.75 3.57%** — the published-version **table number (Table 2) and cell values match the working paper exactly.** The abstract verbatim: "bettors systematically lose more money on Asian Handicap bets where refunds are not possible than when it is possible to obtain a half refund." **Residual journal-version gap for this cell: CLOSED** (published-version table numbering confirmed; the working-paper Table 2 == published Table 2).

## Cell 2 — MPRA 116925 / IJF Table 7 strong*/weak* gradient (zero-handicap-excluded)

- **Citation 4.** Hegarty, T., & Whelan, K. (2025). *Forecasting Soccer Matches With Betting Odds: A Tale of Two Markets.* **International Journal of Forecasting** 41(2):803–820. DOI [10.1016/j.ijforecast.2024.06.013](https://doi.org/10.1016/j.ijforecast.2024.06.013). Working paper MPRA 116925.
- **Table of record:** Table 7, "Mean Expected Ex Ante Loss Rates … in the Asian Handicap Market."
- **Cell values (verbatim):**

  | AH bet subset | Loss rate | N |
  |---|---|---|
  | All home + away | 0.0363 | 168,460 |
  | All bets on the strong/favourite team* | **0.0417** (4.17%) | 69,910 |
  | All bets on the weak/underdog team* | **0.0328** (3.28%) | 69,910 |
  | All bets on home | 0.0411 | 84,230 |
  | All bets on away | 0.0316 | 84,230 |

- **`*` footnote (verbatim):** "**Zero handicap is not considered for strong and weak bets.**" The strong/weak N (69,910 per side) is **below** the home/away N (84,230 per side), confirming the zero-handicap matches were dropped from the strong/weak decomposition.
- **Consequence (the 3.24% vs 3.28% distinction, AFFIRMED):** the 3.28% weak-team cell **excludes the exact AH-0.0 instrument the backtest trades**, so it is NOT the DNB loss level — it is retained only as cross-sectional evidence that the underdog side is the cheaper side *within* the AH market (the ~0.9 pp reverse gradient = 4.17% − 3.28%, the registered power-`δ` sign/magnitude). The DNB loss *level* is the 3.24% integer cell (Cell 1). **The 3.24%/3.28% distinction holds; the two numbers index different objects and must not be conflated.**
- **Companion magnitudes (Table-of-record, verbatim):** 1X2 longshot decile loses **9.4%** vs favourite **6.1%** (standard FLB); AH longshot **3.5%** vs favourite **4.1%** (weak reverse FLB — underdog loses less).
- **Round-trip status — CONFIRMED at the working-paper PDF (MPRA 116925).** Published-version (ScienceDirect/Elsevier) round-trip 2026-06-16: the DOI landing page redirects to a JS-rendered Elsevier shell (`linkinghub.elsevier.com/retrieve/pii/S0169207024000670`) returning only a "Redirecting" stub with **no extractable table content (paywalled)**. **Residual journal-version gap for this cell: CARRIED** — the published-version Table 7 *numbering* could not be confirmed headlessly. The *cell values* the EV prior and power `δ` depend on are confirmed against the working paper; the journal-PDF table-number confirmation is the one open item, retained for the manuscript stage (Phase 5 task 5), and does not block computing World-Cup numbers (no transcription of the value is in question, only the published table label).

## Cell 3 — Applied Economics 2025 "Overround" (Pinnacle below market-average)

- **Citation 6.** Hegarty, T., & Whelan, K. (2025). *Estimating Expected Loss Rates in Betting Markets: Theory and Evidence.* **Applied Economics.** DOI [10.1080/00036846.2025.2507979](https://doi.org/10.1080/00036846.2025.2507979).
- **Values (verbatim from the karlwhelan.com working-paper PDF):** soccer overround-implied loss **7.1%** vs realized **8.7%** (N = 151,683); verbatim "*loss rates at Pinnacle … are significantly lower than for the other bookmakers*" AND "*realized loss rates at Pinnacle are significantly larger than predicted rates*." → **Pinnacle is below market-average but still prices the favourite-longshot bias.**
- **Consequence:** every AH/DNB loss magnitude in Cells 1–2 is a **market-average** figure; the Pinnacle-specific AH-0.0 loss level is **lower still** but non-zero. The strategy's reference price is season-conditional Pinnacle closing (≤ 2024/25), so the operative loss baseline is the lower, Pinnacle-specific one — re-derived from the held-out data (EDGE Open Questions 11/12), not asserted here.
- **Round-trip status — CONFIRMED at the working-paper PDF.** Published-version (Taylor & Francis) round-trip: paywall/403 in this environment. **Residual journal-version gap: CARRIED** (manuscript-stage item, Phase 5 task 5); the directional claim (Pinnacle below market-average, still FLB-pricing) does not turn on a single transcribed cell.

## Gate disposition

- **3.24% (RBF 2024 Table 2 integer) ≠ 3.28% (MPRA/IJF Table 7 weak*, zero-handicap-excluded): AFFIRMED.** The DNB loss prior is 3.24%; the 0.89 pp reverse gradient (4.17% − 3.28%) is the registered power-`δ` magnitude, not the DNB loss level.
- **Phase-1 gate SATISFIED for the purpose of computing World-Cup numbers** (all three cell values confirmed against the working papers; the RBF cell additionally confirmed against the open-access published version, table number CLOSED).
- **Residual (carried, not closed):** published-version table *numbering* for Cell 2 (IJF, paywalled) and Cell 3 (Applied Economics, paywalled). These are the sole open items, retained for the manuscript stage (Phase 5 task 5); they do not affect the cell values the EV prior and power `δ` consume.

## Provenance

- Working-paper PDFs: karlwhelan.com (RBF 2024, Applied Economics 2025), MPRA 116925 (IJF 2025), accessed 2026-06-16.
- Published-version re-confirmation 2026-06-16: RBF via emerald.com/rbf/article/16/5/904-924 (Open Access, confirmed); IJF/Applied Economics paywalled (carried).
- This register's SHA-256 is recorded in the validate-stage ReproLog (`logs/reprolog_validate-<run_id>.json`, `config_resolved_sha256` reference).
