---
title: Survivorship-bias treatment + capacity report-card inputs — H001-wc-underdog-dnb
date: 2026-06-16
hypothesis_id: H001-wc-underdog-dnb
type: report_card_input
plan_task: "Phase 1 task 12 (the two mandated report-card fields carry content, not labels)"
---

# Survivorship-bias treatment and capacity — report-card inputs

**Phase-1 task 12 ([plan_phased-workplan_2026-06-16.md](plan_phased-workplan_2026-06-16.md) Phase 1; §B.3).** The quant reporting rule ([rules/quant-project.md](../../../.claude/rules/quant-project.md)) mandates a *survivorship-bias treatment* field and a *capacity / liquidity estimate* field on the report card, each populated with content rather than a bare label. This note supplies both, sourced from the assembled panel and the genuine acquisition attempts of this Phase, so the Phase-5 report card prints content, not placeholders.

## 1. Survivorship-bias treatment (populated)

**Statement for the report card (verbatim):**

> **No entity-survivorship correction is required for the headline settlement.** Settlement is per-match on realized **90-minute results**, not on surviving entities: each match's DNB outcome is fixed by that match's 90-minute score regardless of whether either club/nation survives to a later round, season, or competition. The domestic-league estimation universe is the **full match panel** including relegated, promoted, and folded clubs across all seasons (football-data.co.uk season files are complete match lists per division-season, not a survivors-only subset). There is therefore no look-ahead "winners-only" filter in the estimation universe.
>
> **The one survivorship channel that IS present is World-Cup qualification-survivorship.** The World-Cup hold-out contains only the 32 teams that *qualified* for each finals; non-qualifiers are absent by construction. This interacts with the price-based underdog definition — the field of finalists is a pre-selected, higher-quality population than the full set of FIFA members, so the underdog/favourite price gap distribution at the finals is narrower than it would be across all would-be entrants. This is disclosed as the single survivorship channel present in the analysis and is an inherent property of the held-out tournament, not a correctable data artifact.

**Verification against the Phase-1 dropped-row log (sibling to task 1 / the gate).** The plan requires confirming that football-data season files do not *silently* drop abandoned/expunged fixtures. Cross-check of the landed ingest:

- League ingest: **49,687** panel rows from 147 (season × division) files; **1** dropped row total, reason `nonnumeric_or_missing_goals` (a single unplayed/void fixture row with no score), logged with its reason in `logs/dropped_rows_ingest-<run_id>.json` (no silent drops — every drop carries a reason).
- The drop rate is **0.002%**, i.e. football-data files are complete match lists, not survivors-only; an abandoned/void fixture surfaces as a logged drop (score absent), never a silent omission. The settlement module excludes void/abandoned matches from the win-ratio denominator with a refund ([design.md](design.md) §4), which is the correct handling and does not introduce survivorship.
- World-Cup block: **384** matches (6 editions × 64), all settled on the reconstructed 90-minute FTR and 100% cross-reconciled against an independent results source (martj42); no fixtures dropped.

**Conclusion:** the survivorship-bias treatment field is *populated* — no entity correction for per-match 90-minute settlement; WC qualification-survivorship disclosed as the one present channel; football-data completeness confirmed against the dropped-row log.

## 2. Capacity / liquidity estimate (resolved to an explicit downgrade)

**Acquisition attempt (genuine, this Phase).** The plan mandates an attempt to source a posted-bet-limit series for World-Cup DNB / AH-0.0 markets (Pinnacle live-market limits are public when a market is open) and, if obtained, to archive a checksummed snapshot to `data/raw/provenance/`.

| Source attempted | Result | Verdict |
|---|---|---|
| Pinnacle posted betting-limits page (`pinnacle.com/en/betting-limits/`) | HTTP **404** | Not obtainable headlessly. |
| Pinnacle help-centre limits article (`help.pinnacle.com/...`) | Connection **refused** | Not obtainable headlessly. |
| Live Pinnacle market limits | Require an open, logged-in market session (no headless, point-in-time-for-2002-2022 series exists; limits are live values, not a historical archive) | Not a reproducible historical series. |

No posted-limit data for the historical WC DNB / AH-0.0 markets is obtainable in this environment, and **no number was fabricated** (data-integrity rule).

**Statement for the report card (verbatim), per the honest-prior discipline (A.2):**

> **Capacity — not estimable from available data; reported as a qualitative ceiling.** No posted-bet-limit series for World-Cup Draw-No-Bet / Asian-Handicap-0.0 markets was obtainable (Pinnacle's public limit pages returned 404 / connection-refused, and live limits are not a reproducible point-in-time historical series for the 2002–2022 editions). Capacity is therefore **explicitly downgraded to "not estimable from available data — reported as a qualitative ceiling"** rather than asserted as an unfounded number. The qualitative ceiling: AH-0.0 / DNB on a major-event match at a sharp book is among the *highest-limit* football markets (it is a two-way, low-margin, syndicate-traded line), so the binding constraint on a real deployment is far more likely to be the **two-leg synthetic-DNB execution cost** (the leg-out / slippage model, [ADR-0004](../decisions/0004-transaction-cost-execution-model.md), calibrated in Phase 3) than posted stake limits — but this is a qualitative ordering, not a capacity figure.

**Conclusion:** the capacity field is *populated* with the explicit downgrade and its justification, exactly as the plan's honest-prior discipline requires; the downgrade (not a number) is what the report card prints.

## 3. Provenance

- Dropped-row log: `logs/dropped_rows_ingest-<run_id>.json` (1 dropped league row, reason recorded).
- Panel counts: `data/processed/matches.parquet` (49,687 league + 384 WC = 50,071 rows).
- WC cross-reconciliation: 384/384 vs martj42 (`build_wc_panel.reconcile_settlement`).
- Capacity acquisition attempts: Pinnacle limit pages (404 / connection-refused), 2026-06-16.
