# Audit trail — Phase 1 World-Cup hold-out slice (tasks 4, 5, 10)

Date: 2026-06-16. Author dimension: SKIE. Loop: `audit-remediate-loop` (3-round cap; CLAUDE.md).
Artifacts audited: [src/wc_holdout.py](../../src/wc_holdout.py), [src/build_wc_panel.py](../../src/build_wc_panel.py), [src/provenance.py](../../src/provenance.py), [src/scrape_wc_odds.py](../../src/scrape_wc_odds.py), [tests/test_wc_holdout.py](../../tests/test_wc_holdout.py), [config/baseline.yaml](../../config/baseline.yaml) `wc_holdout` block, [docs/protocol/note_wc-odds-gap_2026-06-16.md](../protocol/note_wc-odds-gap_2026-06-16.md).

**Audit mode.** No subagent-spawning tool was available in this workflow context, so the six specialist concerns (code quality, quant-method fidelity, citations, reproducibility, data-integrity, format/magic-numbers) were audited inline by the lead, each with an explicit empirical probe rather than assertion. Per the skill's fallback, residuals are surfaced here, not continued silently.

## Round 1 findings + disposition

| # | Severity | Concern | Issue / probe | Disposition |
|---|---|---|---|---|
| R1-1 | major | quant-method | Own-goal credit: does jfjelstul `goals.csv` `home_team`/`away_team` flag credit the BENEFITING side or the conceding player's side? A wrong sign would mis-score 79 own goals in the 90-min reconstruction. | **PASS (verified).** For all 79 own goals `team_code != player_team_code`; `team_*`/`home_team`/`away_team` = credited (benefiting) side, `player_team_*` = conceding player. The count-by-side reconstruction is correct. No fix. |
| R1-2 | major | quant-method | Golden-goal era (2002–): is an ET golden goal correctly excluded from the 90-min score? | **PASS.** 2002 Sweden–Senegal: 1-1 at 90, Senegal's 104' golden goal tagged `extra time, first half` → excluded → 90-min draw → DNB push; `decided_in_et=True`. No fix. |
| R1-3 | major | quant-method | Group-matchday inference via `index//2`: does every 32-team group actually have 6 date-ordered matches (else matchday tags wrong → qual-state wrong)? | **PASS.** All 48 groups (8/yr × 6) have exactly 6 matches; no 3-team groups. No fix. |
| R1-4 | critical | quant-method | Clinch/elimination arithmetic correctness (no-look-ahead qual-state). | **FIXED in-session before audit.** Initial logic used strict `>` and falsely clinched South Africa 2002 (4 pts at MD3, did not qualify). Replaced with tiebreak-safe `>=` test (a rival able to finish level blocks a clinch). Validated: SA 2002 → live; Spain 2002 → qualified; Belgium–England 2018 → dead rubber. |
| R1-5 | major | reproducibility | `--no-fetch` rebuild dropped the 5 raw-source checksums from the ReproLog. | **FIXED.** `build()` now recomputes raw-source SHA-256 from disk regardless of `fetch`, so all 7 checksums are always pinned (reproducible-from-snapshot). |
| R1-6 | minor | reproducibility | Panel determinism across runs. | **PASS.** Two same-input builds produce a byte-identical `wc_holdout_panel.csv`; CSV (LF) is checksummed, not non-deterministic parquet bytes (plan §D.7c). |
| R1-7 | minor | data-integrity | Any synthesized/hand-written odds presented as real? | **PASS.** No odds obtained or fabricated; only real downloaded results sources, each with a provenance JSON (URL + fetch timestamp + LF SHA-256). The WC-odds gap is recorded in the protocol note + config `odds_status: pending`. |
| R1-8 | minor | format/magic-numbers | Any unjustified numeric literal? | **PASS.** Only `CLV_NATIVE_AH_FIRST_SEASON_YEAR = 2019` — a documented factual boundary (football-data `notes.txt`: native AH since 2019/20), not a tunable threshold. Root seed read from `config/baseline.yaml`, not a literal. |
| R1-9 | minor | citations | Source-of-record attribution. | **PASS.** jfjelstul, martj42, football-data notes.txt, Hegarty–Whelan IJF + Zenodo, OddsPortal — all listed with access date in the protocol note. |

**Exit check.** R1-4 (critical) and R1-5 (major) were remediated; R1-1/2/3 passed on probe; remaining are minor and passed. No critical or major findings survive Round 1 → **loop exits at Round 1** (no Round 2/3 needed).

## Residual risk

- **WC transfer test is PENDING-ODDS.** The hold-out is results-only; the underdog-DNB edge cannot be scored on the World Cup until a ToS-cleared, checksum-frozen odds snapshot exists. This is an honest data gap, not a code defect; Phases 2–4 proceed on the league universe (plan A.1). **Formally dispositioned (2026-06-16):** the Phase-1 acceptance criterion was amended to scope `refC_*`/underdog/`o_dnb` completeness to the league block and to record the WC transfer verdict as an explicitly DEFERRED, GATE-BLOCKED deliverable (plan Phase-1 "Amendment A1"; gaps-register P1 row "World-Cup odds acquisition / transfer-test gate-block"; note_wc-odds-gap §5.1). The estimation universe is complete; the OOS transfer verdict is gate-blocked, not failed.
- **2026 edition not built.** Out of the 384-match 32-team block by design (descriptive-only, plan task 7.1); its third-place-comparison qual-state is deferred.
- **Qual-state conservatism.** The tiebreak-safe clinch test yields only mathematically-certain `qualified`/`eliminated` states; near-certain-but-not-mathematical dead rubbers are tagged `live`. This is the correct point-in-time, no-look-ahead choice and is conservative for the dead-rubber stratum (under-counts rather than over-claims).
