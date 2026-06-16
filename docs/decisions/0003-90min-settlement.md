---
name: ADR-0003 — 90-minute settlement convention for Draw-No-Bet
description: Settle DNB / AH-0.0 on the 90-minute result; extra time and penalties never change the outcome
type: methodology
status: accepted
date: 2026-06-16
supersedes:
superseded_by: ""
---

# ADR-0003 — 90-minute settlement convention for Draw-No-Bet

## Context

Draw-No-Bet (= Asian Handicap 0.0) settles on the **result at the end of normal time** (90 minutes +
injury/stoppage), excluding extra time, penalty shootout, and golden goal, unless a market is
explicitly labelled "to qualify" / "to lift the trophy" (Pinnacle betting rules; Betfair 90-Minute
Rule; William Hill settlement guide; CALC §10). A 90-minute draw triggers the **push** (stake
refund), regardless of who advances after ET/penalties.

This is non-trivial for the World Cup because the **knockout phase** resolves ties by ET/penalties:
~38% of knockout matches (1998-2022) go to extra time and ~22% to penalties (EDGE §4.6). A backtest
that settled DNB on the post-ET result would be a **look-ahead / settlement bug** — a penalty-decided
`1–1` would be mislabelled as an underdog win or loss instead of a push. ARCH Open Question 1 also
notes that some operators settle a product they call "DNB" on the full ET result, so the convention
must be explicit and config-switchable, with the default justified against a specific rulebook.

## Decision

- **Settlement is on the 90-minute result.** The DNB outcome is one of
  `{underdog wins in 90' → o_DNB / 90-minute draw → 1.0 (push) / favourite wins in 90' → 0}`.
- A match level `1–1` (or any draw) after 90 minutes and decided on ET/penalties is a **push**, even
  though the tournament records a "winner." ET and penalty results **never** change the bet outcome.
- The match-result field used for settlement is the **90-minute** score (`FTHG`/`FTAG`/`FTR` in
  football-data.co.uk are full-time = 90' + stoppage, which is correct; ET/penalty results live in
  separate fields and are excluded). For World-Cup knockout matches the 90-minute `FTR` is
  reconstructed explicitly (Phase 1 task 5).
- Void / abandoned matches → refund and **excluded from the win-ratio denominator** (ARCH §4.1).
- The convention is **config-switchable** (a `settlement` block); the **90-minute default** is the
  registered choice, justified against the Pinnacle/Betfair rulebooks above. The 2026 expansion to
  48 teams / 104 matches changes the count and group structure but **not** the 90-minute settlement
  convention (CALC §10.4).

## Consequences

- **Positive.** Eliminates the most dangerous settlement bug class (post-ET look-ahead); the
  penalty-decided-`1–1`-is-a-push case is unit-tested (Phase 2 task 5) and flagged for the
  point-in-time canary (Phase 4 task 2).
- **New obligation.** The 90-minute `FTR` must be reconstructed for every knockout match before the
  draw-push frequency `q` is trusted; the recorded draw rate must be the regulation-time rate, not
  an all-time anchor inflated/deflated by ET resolution (Phase 1 tasks 5, 7; DATA §6).
- **Interpretation note.** The folk intuition "underdogs hang on in knockouts" must be tested at the
  90-minute mark, not the final result — ~22-27% of knockout matches level at 90' become refunds,
  not away-team losses (EDGE §4.1, §4.6).

## Alternatives considered

- **Settle on the full result (post-ET / penalties).** Rejected: contradicts the Pinnacle/Betfair
  DNB rulebook, injects look-ahead-style settlement error, and biases the push frequency and the
  edge estimate. Retained only as a config-switchable sensitivity, never the default.
- **Drop knockout matches.** Rejected: discards a large, edge-relevant fraction of the held-out WC
  block (the dead-rubber and stage strata depend on it) for a problem solved correctly by
  90-minute reconstruction.

## References

- [research_dnb-odds-calculations_2026-06-16.md](../research/research_dnb-odds-calculations_2026-06-16.md) §10 (90-minute settlement convention; knockout labelling).
- [research_edge-flb-empirics_2026-06-16.md](../research/research_edge-flb-empirics_2026-06-16.md) §4.6 (ET/penalties vs 90-minute settlement), §4.1 (knockout 90' draws as refunds).
- [research_backtest-architecture-deliverables_2026-06-16.md](../research/research_backtest-architecture-deliverables_2026-06-16.md) §4.1, Open Question 1 (settlement contract; config-switchable convention).
- Pinnacle betting rules: [pinnacle.com/en/future/betting-rules](https://www.pinnacle.com/en/future/betting-rules); Betfair Football 90-Minute Rule: [support.betfair.com](https://support.betfair.com/app/answers/detail/10264-football---90-minute-rule/).
