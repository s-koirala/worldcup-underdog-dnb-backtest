# Methodology: Decision Inputs, Validation Design, and the Multiple-Testing Register

Protocol document. Project: backtest of an underdog Draw-No-Bet (DNB) strategy on the FIFA men's World Cup, estimation universe expanded to domestic leagues (football-data.co.uk), World Cup held out as a subsample. Author dimension: SKIE. Date: 2026-06-16.

This document is the canonical home of the project's **decision inputs** — the quantities that are *chosen* (risk preferences, design parameters) rather than *estimated from data* — together with pointers to where the *estimated* and *registered* objects live. It exists so that the most consequential tunable in the project, the deployed fractional-Kelly multiplier `λ`, is anchored to declared inputs rather than to a broken cross-reference (see [research_staking-bankroll_2026-06-16.md](../research/research_staking-bankroll_2026-06-16.md) §6.2, §7.3, §8). Per the project [CLAUDE.md](../../CLAUDE.md) no-magic-number mandate, every value below is either (a) declared as a swept *range* with the operating point read off a reported frontier, or (b) tied to an empirical-selection rule, with a citation for the rationale of the range bounds. No single value is asserted as "the" answer.

The division of labour across the three project documents is:

| Object | Declared / derived in | Pointer |
|---|---|---|
| Ruin floor `ρ`, drawdown target `(α, β)` (the inputs that select `λ`) | **here**, §1 | this document |
| Walk-forward CV fold structure | **here**, §2 | this document |
| Multiple-testing register (family count `K`, menu) | `config/multipletest_family.yaml` | [config/multipletest_family.yaml](../../config/multipletest_family.yaml) |
| Correction methods (White / Hansen / Romano–Wolf / BH), Deflated/Probabilistic Sharpe, MinTRL, HAC, power | sibling research doc §7–§8 | [research_statistical-methodology_2026-06-16.md](../research/research_statistical-methodology_2026-06-16.md) |
| Staking economics, Kelly derivation, risk-of-ruin Monte-Carlo | sibling research doc | [research_staking-bankroll_2026-06-16.md](../research/research_staking-bankroll_2026-06-16.md) |

---

## 1. Risk decision inputs: ruin floor `ρ` and drawdown target `(α, β)`

These are **risk preferences**, not data. They cannot be estimated; they must be *declared* and then *swept*, with the operating point chosen transparently on the reported growth–drawdown frontier. The Busseti–Ryu–Boyd (2016) constraint `E[(rᵀb)^{−θ}] ≤ 1` with bound exponent `θ = log β / log α` is the mechanism that maps a declared `(α, β)` to the deployed multiplier `λ < 1` (see staking doc §6.2). Because `λ` is a *monotone* function of `(α, β)` through this binding constraint, declaring a single `(α, β)` would silently fix `λ` to one number; instead the project reports `λ(α, β)` across a grid and selects the operating point at the frontier.

### 1.1 Definitions

- **Ruin floor `ρ`** (staking doc §6, eq. for the ruin indicator `1{min_t W_t ≤ ρ W_0}`): the fraction of initial bankroll at or below which the bettor is declared "ruined". Two values are reported, not one:
  - `ρ = 0` — literal bankruptcy. Only reachable under flat-*cash* (additive) staking; under fixed-fraction/Kelly (multiplicative) staking `W_t > 0` a.s. and this is unreachable, so it functions as the additive-case sanity benchmark only (staking doc §6.1).
  - `ρ ∈ (0, 1)` — "effective ruin" / behavioural stop-out: the level below which a real bettor stops playing. This is a behavioural quantity, justified below.
- **Drawdown target `(α, β)`** (staking doc §6.2): the pair "no more than a `β` probability of the running-minimum wealth ever falling below an `α` fraction of its running maximum (or of `W_0`)". `α ∈ (0,1)` is the drawdown floor; `β ∈ (0,1)` is the tolerated probability of breaching it.

> **Disambiguation (resolves the audit's same-symbol collision).** The `(α, β)` *here* are a **drawdown floor and breach probability** — a risk preference on the wealth path. They are a *different object* from the `(α, β)` in the sibling [research_statistical-methodology_2026-06-16.md](../research/research_statistical-methodology_2026-06-16.md) §6.2, where `α` is the hypothesis-test **size** (Type-I error) and `β` the test **Type-II error** (`1−β` = power). The two pairs are never interchanged. Where ambiguity is possible, this document writes the drawdown pair as `(α_dd, β_dd)`.

### 1.2 Declared grid and rationale (no magic single value)

The drawdown floor `α_dd` and breach tolerance `β_dd` are swept over a grid; the frontier is reported across the whole grid (staking doc §7.3) and the operating point is read off it.

| Input | Declared grid | Rationale / citation for the range |
|---|---|---|
| `α_dd` (drawdown floor) | `{0.5, 0.6, 0.7, 0.8}` | Lower end `0.5` (a 50% drawdown) is the BRB worked-example value (staking doc §6.2). The range brackets the **prospect-theory threshold-type stop-loss** region: prospect-theory bettors set a stop-loss at a loss threshold rather than holding indefinitely ([Henderson 2012](https://doi.org/10.1287/mnsc.1110.1468); [Barberis 2012](https://doi.org/10.1287/mnsc.1110.1435)), and the disposition-effect literature documents that real losers are realised in a threshold band rather than at `0` ([Odean 1998](https://doi.org/10.1111/0022-1082.00072); [Barberis & Xiong 2009](https://doi.org/10.1111/j.1540-6261.2009.01448.x)). `0.7` matches the BRB experiments' threshold `α = 0.7` (staking doc §6.2, Tables 1/3) for comparability with the cited drawdown probabilities. |
| `β_dd` (breach probability) | `{0.05, 0.10, 0.20}` | Centred on `0.10`, the BRB worked-example tolerance (staking doc §6.2, the `θ = log 0.10/log 0.50 = 3.32` worked exponent), and bracketed by the conventional `0.05` and a looser `0.20`. These are *risk preferences*; the grid makes the sensitivity of `λ` to the choice explicit rather than hiding it in one number. |
| `ρ` (effective-ruin floor) | `{0.0, 0.5}` | `0.0` = literal-bankruptcy benchmark (additive case only). `0.5` = behavioural stop-out: a 50%-of-bankroll loss is a defensible "I stop" level consistent with the threshold-type stop-loss evidence above; reported alongside the path's full max-drawdown distribution so the choice is descriptive, not load-bearing. |

The deliverable is `λ(α_dd, β_dd)` over this grid plus the growth–drawdown frontier (staking doc §7.3); the operating point is the `(α_dd, β_dd)` cell whose BRB constraint binds at the chosen frontier location, reported with its CV-selected `λ` and a bootstrap CI (staking doc Open Question 4). If the World-Cup-only frontier sits below the zero-growth axis for every cell, the honest output is `λ* = 0` (do not bet), per staking doc §7.3 and Open Question 6.

### 1.3 Why these are inputs, not estimates

`(α_dd, β_dd, ρ)` quantify *how much drawdown the operator will tolerate* — a utility/behavioural statement, not a property of the data-generating process. Estimating them from the backtest would be circular (the backtest's realised drawdowns would set the tolerance they are then judged against). They are therefore declared here, swept, and reported transparently, which is the no-magic-number-compliant treatment of a genuine risk-preference parameter.

---

## 2. Walk-forward cross-validation fold structure

Per the project time-series-integrity rules ([rules/quant-project.md](../../CLAUDE.md), quant-project section: "Walk-forward CV, never k-fold") and the sibling doc §9, validation is **walk-forward**, time-ordered, expanding-window, with disjoint folds:

- **Estimation universe** = domestic leagues (football-data.co.uk Pinnacle closing 1X2 + Asian-Handicap), ordered by match kickoff time.
- **Expanding-window walk-forward.** Fit calibration / `λ` selection on all data up to the end of fold `k`; evaluate on fold `k+1`; roll forward. Splits are time-ordered and disjoint; no fold uses information dated after its own evaluation window (no look-ahead).
- **Fold boundary.** Folds are cut on **season boundaries** of the league panel (a season is the natural disjoint time block and avoids splitting a single competition across train/test); the number of folds equals the number of complete estimation seasons minus the first (which seeds the initial training window). The exact season list and fold count are fixed in `config/multipletest_family.yaml` alongside the strategy menu so the CV design is part of the pre-registered family.
- **Held-out test block.** The **FIFA World Cup** is the final, never-touched test fold. `λ`, `φ`, `c`, and any calibration parameter are selected purely out-of-fold on the league universe; the World Cup is scored once, after the design is frozen.
- **Selection objective.** The parameter chosen on each fold is the one maximising *out-of-fold* drawdown-constrained growth (staking doc §7.3), so the parameter choice is itself out-of-sample and the White/Hansen and Deflated-Sharpe corrections (sibling doc §7–§8) are applied to the *out-of-sample* path.
- **Leakage canary.** Before any performance number is trusted, the point-in-time canary of sibling doc §9.2 is run (inject a future-knowing feature; if it does not dominate, the pipeline already leaks).

---

## 3. Multiple-testing register (pointer)

The register itself — the family count `K`, the enumerated menu of (side definition × staking scheme × underdog threshold × odds source) cells, and the registered correction method — lives in [config/multipletest_family.yaml](../../config/multipletest_family.yaml) and is maintained by the project's `multipletest-gate` skill. It must be frozen *before* fitting so the correction denominator and the Deflated-Sharpe inputs (`K`, `V[ŜR_n]`) are honest. The statistical apparatus that consumes the register — White (2000) Reality Check, Hansen (2005) SPA, Romano–Wolf (2005) stepdown, Benjamini–Hochberg FDR, and the Probabilistic/Deflated Sharpe Ratio and Minimum Track Record Length — is specified and derived in [research_statistical-methodology_2026-06-16.md](../research/research_statistical-methodology_2026-06-16.md) §7–§8. This document does not duplicate that derivation; it only fixes the decision inputs (§1) and the CV design (§2) that the register's evaluation runs against.

---

## Citations

1. Busseti, E., Ryu, E. K., & Boyd, S. (2016). Risk-Constrained Kelly Gambling. *The Journal of Investing* 25(3): 118–134; arXiv:1603.06183. DOI: [10.3905/joi.2016.25.3.118](https://doi.org/10.3905/joi.2016.25.3.118). (Drawdown constraint `E[(rᵀb)^{−θ}] ≤ 1`, `θ = log β/log α`; mapping from `(α, β)` to fractional multiplier `λ < 1`. Worked-example values `α = 0.5`, `β = 0.1`. Verified by text extraction of the Stanford author PDF, see staking doc Citation 7.)
2. Odean, T. (1998). Are Investors Reluctant to Realize Their Losses? *The Journal of Finance* 53(5): 1775–1798. DOI: [10.1111/0022-1082.00072](https://doi.org/10.1111/0022-1082.00072). (Disposition effect: losers realised in a threshold band, not at zero.)
3. Barberis, N., & Xiong, W. (2009). What Drives the Disposition Effect? An Analysis of a Long-Standing Preference-Based Explanation. *The Journal of Finance* 64(2): 751–784. DOI: [10.1111/j.1540-6261.2009.01448.x](https://doi.org/10.1111/j.1540-6261.2009.01448.x). (Preference-based account of threshold-type loss realisation.)
4. Henderson, V. (2012). Prospect Theory, Liquidation, and the Disposition Effect. *Management Science* 58(2): 445–460. DOI: [10.1287/mnsc.1110.1468](https://doi.org/10.1287/mnsc.1110.1468). (Prospect-theory traders use threshold-type stop-loss on losses; DOI CrossRef-verified 2026-06-16.)
5. Barberis, N. (2012). A Model of Casino Gambling. *Management Science* 58(1): 35–51. DOI: [10.1287/mnsc.1110.1435](https://doi.org/10.1287/mnsc.1110.1435). (Prospect-theory gambler sets a loss-exit threshold; DOI CrossRef-verified 2026-06-16.)
