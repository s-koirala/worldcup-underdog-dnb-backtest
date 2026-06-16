# Backtest Architecture, Reproducibility, and Deliverable Specification — World Cup Underdog Draw-No-Bet Strategy

Author: SKIE · Date: 2026-06-16 · Project: `worldcup-underdog-dnb-backtest`

## Scope

This document specifies the *engineering and deliverable* dimension of the project: the end-to-end backtest pipeline (module boundaries and data contracts), leakage prevention, the reproducibility envelope, the testing strategy, and the exhaustive list of artifacts the user receives (report card, figures, tables, Excel workbook tabs) with the metrics each must report and explicit acceptance criteria.

It does **not** decide the strategy's economic merit, the staking-parameter values, or the literature on the favourite-longshot bias — those are owned by sibling research dimensions. It *does* fix the interfaces those decisions flow through, the statistical estimators used to report results (with verified citations), and the definition-of-done for every artifact.

Two design facts drive everything below:

1. **The World-Cup-only sample is underpowered.** ~384 men's World Cup matches with clean odds (2002–2022; 64 matches/tournament × 6 tournaments; 2026 expands to 104 matches/tournament). With a per-bet edge near zero and high per-bet variance, a Sharpe-style t-statistic on a few hundred bets has very wide confidence bands. The architecture must therefore treat the World Cup as a **held-out subsample** and estimate on a much larger domestic-league universe (football-data.co.uk), as established in the project priors. This forces a strict train/test boundary and walk-forward evaluation into the *pipeline shape*, not just the analysis.
2. **The bet instrument is synthetic.** Draw-No-Bet (DNB) is reconstructed from 1X2 decimal odds, so the pricing module is a load-bearing, separately-tested component, and football-data.co.uk's native Asian-Handicap-0.0 columns are an independent cross-check, not the primary source.

---

## 1. Instrument definition and odds algebra (the contract every module shares)

All odds are **decimal** (European). For a single outcome priced at decimal odds `o`, a winning unit stake returns `o` (stake + profit `o−1`); a losing stake returns 0.

### 1.1 Implied probability and the over-round

For a 1X2 book with home/draw/away decimal odds `(H, D, A)`:

- Raw implied probabilities: `qH = 1/H`, `qD = 1/D`, `qA = 1/A`.
- Booksum / over-round: `Σ = qH + qD + qA ≥ 1`. The bookmaker margin (vig) is `m = Σ − 1`.
- Normalised (margin-removed) probabilities under the **basic/proportional** method: `pX = qX / Σ`.

The proportional method is the simplest de-vig and is biased in the presence of favourite-longshot effects; **Shin (1993)** and the **odds-ratio / logarithmic** methods are alternatives. The de-vig method is a *config-selected* parameter (see §3.3) — it is not hard-coded — and the choice must be justified empirically (calibration against realised frequencies; §1.5), per the project's no-magic-numbers rule. Štrumbelj (2014) compares four methods — basic normalisation, Shin's model, and two regression-based variants (a logit fitted on an initial data block and a rolling-update logit) — and finds Shin probabilities the most accurate across bookmaker/sport pairs while basic normalisation is biased, with the regression variants intermediate; the Shin advantage shrinks as market size grows.

### 1.2 Underdog selection (point-in-time at time `t`)

The **underdog** of a match is the side with the **higher decimal win price** (equivalently lower implied win probability). For sides home/away with win prices `H` and `A`:

- If `A > H`: away is the underdog.
- If `H > A`: home is the underdog.
- Ties (`H == A`, measure-zero with real prices) are excluded by config (`require_strict_underdog: true`) and logged.

The selection uses **only** the odds vector available at the configured decision timestamp (closing line by default). No realised result, no post-match information.

### 1.3 Synthetic DNB pricing (the key identity)

DNB ("tie no bet") on the **away** side, replicated from 1X2 odds, is the portfolio:

- Stake fraction `1/D` on the **draw** (this exactly refunds the unit stake if the match is a 90-minute draw, since `(1/D)·D = 1`).
- Stake fraction `1 − 1/D` on the **away win**.

Settlement of that portfolio:

| 90-min result | Draw leg pays | Away leg pays | Total return on unit stake |
|---|---|---|---|
| Away win | 0 | `(1 − 1/D)·A` | `A·(D−1)/D` |
| Draw | `(1/D)·D = 1` | 0 | `1` (stake refunded) |
| Home win | 0 | 0 | `0` (stake lost) |

Therefore the **effective DNB decimal odds for the away underdog** are

```
o_DNB(away) = A · (D − 1) / D
```

and symmetrically for a home underdog `o_DNB(home) = H · (D − 1) / D`. This is the KEY IDENTITY in the project brief; it is implemented in `pricing.synthetic_dnb()` and unit-tested against the settlement table above and against football-data.co.uk's native AH-0.0 columns.

**Worked example.** Home favourite vs away underdog, with `(H, D, A) = (1.80, 3.60, 4.50)` — away is the underdog (`A = 4.50 > H = 1.80`), so we back the away underdog priced `A = 4.50`, `D = 3.60`:

```
o_DNB = 4.50 · (3.60 − 1) / 3.60 = 4.50 · 2.60 / 3.60 = 4.50 · 0.72222 = 3.250
```

Interpretation: the synthetic DNB pays 3.25 (profit 2.25 per unit) on an away win, refunds 1.00 on a draw, loses on a home win. The 1X2 away price 4.50 is shortened to 3.25 because draw risk is removed.

### 1.4 Per-bet return distribution and variance (used by the metrics layer)

Let `p` be the (estimated, point-in-time) probability the underdog **wins** in 90 minutes, `d` the probability of a 90-minute draw, and `1 − p − d` the probability it loses. With effective DNB odds `o = o_DNB`, the per-unit-stake return `R` of a flat 1-unit DNB bet is a three-point random variable:

```
R = o − 1   with prob p      (win;   net profit o−1)
R = 0       with prob d      (refund; net 0)
R = −1      with prob 1−p−d  (loss;  lose stake)
```

Expected return (edge) `E[R] = p·(o−1) − (1−p−d)`. Variance:

```
Var[R] = p·(o−1)² + (1−p−d)·1² − (E[R])²
```

The identity `Var[R] = o − 1` holds **only** for a *fair win bet* — no draw leg, no margin, `E[R]=0`, win prob exactly `1/o`. It is the analytic benchmark the variance unit test checks against (§4.1), **not** the dispersion of the actual DNB strategy. The real DNB instrument carries refund mass `d > 0` and a non-zero edge, so its per-bet variance must be computed from the full three-point law `Var[R] = p·(o−1)² + (1−p−d) − (E[R])²` with the estimated `(p, d)`, and **that** SD — not the fair-win-bet `o−1` — is what enters any power/Sharpe-denominator statement.

**Worked example — fair-win-bet benchmark (unit-test target only).** `o = 3.25 ⇒ p = 1/3.25 = 0.3077`, `Var[R] = 3.25 − 1 = 2.25`, `SD = 1.500`. This is the value §4.1 asserts against, *not* the strategy SD.

**Worked example — actual DNB strategy SD (project negative-EV prior).** At the same `o = 3.25`, use the de-vigged probabilities the sibling calc doc derives for this exact instrument (basic three-way de-vig of `(H,D,A)=(1.80,3.60,4.50)`, booksum `Π=1.0556`, home favourite `1.80` / away underdog `4.50`: `p = p_W = 0.2105`, `d = p_D = 0.2632`, loss prob `p_fav = 0.5263`; calc doc §8.1–§8.2). Then `E[R] = 0.2105·2.25 − 0.5263 = 0.4737 − 0.5263 = −0.0526` (i.e. **−5.3% EV**, negative — the favourite-longshot + double-margin prior, *not* a positive edge); `Var[R] = 0.2105·(2.25)² + 0.5263 − (−0.0526)² = 1.0657 + 0.5263 − 0.0028 = 1.589`, so `SD ≈ 1.261` — materially below the fair-win-bet `1.500` (the draw-refund mass compresses the dispersion). A per-bet t-statistic over `n` bets scales as `√n · E[R] / SD`; with a near-zero-to-negative edge this is the channel through which `n ≈ 384` World-Cup bets are **underpowered**, computed from this **strategy** SD (≈ 1.261 here), not the benchmark `1.5`. These figures reconcile exactly with calc doc §8.2 (same instrument, same de-vig, `EV=−5.3%`, `Var=1.589`, `SD=1.261`, `f*=−0.0317 → do not bet`); the two documents therefore present the **same sign** for the same instrument.

**Skew of the per-bet return (sign matters for PSR/DSR).** This three-point law is **positively** skewed: a small-probability large gain at `o−1` sits against a hard `−1` floor and a refund spike at `0`. The third central moment for this exact instrument (`o_DNB=3.25`, `p=0.2105`, `d=0.2632`) is `γ̂₃ = +1.06`; for longer underdogs the per-bet skew rises (e.g. ~`+1.8` at `o≈6`, ~`+2.5` at `o≈9`) and is **never negative** — direct moment computation over realistic de-vigged 1X2 vectors gives `γ̂₃ ∈ [+0.4, +2.4]` (sibling methodology doc §2.7, §8.4). This sign is the moment fed to the PSR/DSR denominator in §6.3, computed on the **per-bet return sequence** (a negatively skewed *compounded equity curve* is a different object and is not what the per-bet DSR uses). See §6.3's deflated-Sharpe treatment.

### 1.5 Calibration (probability sanity)

Whatever de-vig + model produces `p`, calibration is checked with a **reliability diagram** and the **Brier score** (Brier 1950) and its decomposition (Murphy 1973), plus the football-specific **Ranked Probability Score** (Constantinou & Fenton 2012) because RPS respects the ordinal structure home<draw<away. These are diagnostic figures (F-11) and gate the de-vig choice in §3.3.

---

## 2. End-to-end pipeline design

### 2.1 Module DAG and data contracts

The pipeline is a directed acyclic graph of pure-ish stages; each stage reads a typed table and writes a typed table. Stages live in `src/` and never reach across boundaries (no stage reads another stage's internals).

```
                 config/*.yaml  (config-as-data, hashed)
                        │
   ┌───────────────┐    │
   │  ingest        │◄───┘   football-data.co.uk CSVs (leagues) + WC odds CSV
   └──────┬─────────┘
          │  RawMatches  (schema-validated, vendor + snapshot date)
          ▼
   ┌────────────────┐
   │  features_pit   │   point-in-time features/labels AT t  (no look-ahead)
   └──────┬──────────┘
          │  PitFrame  (one row per match; columns computable at decision time t)
          ▼
   ┌────────────────┐
   │  selection      │   underdog side, eligibility filters
   └──────┬──────────┘
          │  Candidates
          ▼
   ┌────────────────┐
   │  pricing        │   synthetic DNB odds o_DNB; de-vig p,d
   └──────┬──────────┘
          │  PricedBets
          ▼
   ┌────────────────┐
   │  staking        │   flat / fixed-fraction / Kelly / fractional-Kelly
   └──────┬──────────┘
          │  StakedBets  (stake sized BEFORE result known)
          ▼
   ┌────────────────┐
   │  settlement     │   90-minute result → DNB outcome (win/refund/loss)
   └──────┬──────────┘
          │  SettledBets
          ▼
   ┌────────────────┐
   │  ledger         │   ordered PnL ledger, equity path, bankroll state
   └──────┬──────────┘
          │  Ledger
          ▼
   ┌────────────────┐     ┌────────────────┐     ┌────────────────┐
   │  metrics        │ ──► │  figures        │     │  tables/excel   │
   └──────┬──────────┘     └─────────────────┘     └────────────────┘
          │  MetricsBundle (+ bootstrap CIs)
          ▼
   ┌────────────────┐
   │  report         │   report card (md/html/pdf)
   └─────────────────┘
```

### 2.2 Stage responsibilities and contracts

| Stage | Module | Input → Output | Invariants enforced |
|---|---|---|---|
| ingest | `src/ingest.py` | vendor CSVs → `RawMatches` | schema validated (pandera/pydantic); records `data_vendor`, `snapshot_date`, source file SHA-256; **no row dropped silently** (dropped rows logged with reason) |
| features_pit | `src/features.py` | `RawMatches` → `PitFrame` | every column carries a `pit_max_timestamp ≤ t`; label columns are tagged `is_label=True` and physically separated from features; canary column injected in test mode (§3.1) |
| selection | `src/selection.py` | `PitFrame` → `Candidates` | underdog = higher win price; strict-tie exclusion; eligibility filters from config (min liquidity proxy, both 1X2 odds present) |
| pricing | `src/pricing.py` | `Candidates` → `PricedBets` | `o_DNB = side · (D−1)/D`; `0 < p,d`, `p+d ≤ 1`; de-vig method from config |
| staking | `src/staking.py` | `PricedBets` → `StakedBets` | stake is a function of `(o_DNB, p, bankroll_{before})` ONLY; stake ≥ 0; staking cannot read result |
| settlement | `src/settlement.py` | `StakedBets` + results → `SettledBets` | DNB three-way map; **knockout 90-minute draw refunds** (extra-time/penalties ignored — DNB settles on 90-min result); idempotent |
| ledger | `src/ledger.py` | `SettledBets` → `Ledger` | bets applied in chronological order; bankroll path monotone in time index; conservation: `equity_t = equity_0 + Σ pnl_{≤t}` |
| metrics | `src/metrics.py` | `Ledger` → `MetricsBundle` | every point estimate paired with a bootstrap CI; estimator + seed recorded |
| figures/tables/excel | `src/report/*` | `MetricsBundle` → artifacts | deterministic given `MetricsBundle` + style config |
| report | `src/report/card.py` | all artifacts → report card | every number in prose traces to a `MetricsBundle` field |

### 2.3 Orchestration

A single entry point `python -m src.run --config config/<exp>.yaml` resolves the config, emits the ReproLog (§3.2), then runs the DAG. The CLI is the only supported way to run an experiment (notebooks call into `src/` but never redefine logic — they import and visualise). Stage outputs are cached by content hash of `(stage_code_hash, input_hash, config_subtree_hash)` so re-runs are incremental and bit-reproducible.

---

## 3. Leakage prevention, reproducibility, tooling

### 3.1 Point-in-time leakage prevention (canary)

Two complementary controls:

1. **Structural PIT contract.** `PitFrame` columns each carry `pit_max_timestamp`; a contract test asserts `pit_max_timestamp ≤ decision_timestamp` for every feature column and that label columns never feed selection/pricing/staking. Closing-line odds are the *latest* admissible information at `t`; using them is intentional and is the only odds input allowed downstream.

2. **Leakage canary (skill `pit-canary`).** Inject a deliberately future-knowing feature (e.g. a noised copy of the realised result). Train/evaluate the selection model with and without it. If the canary does **not** dominate (materially improve) the honest feature set, the pipeline already leaks — an honest pipeline must reward an oracle feature. The canary is the *necessary* direction of the test: failure to detect the oracle is the alarm. This is run in CI on the fixture and on each new feature set. (Inspired by adversarial PIT validation; cross-checked against López de Prado's backtest-overfitting cautions, Bailey et al. 2017.)

The canary asserts a one-sided improvement, not a magnitude threshold, so it introduces no magic number.

### 3.2 Reproducibility envelope (ReproLog, hook-enforced)

Per the project mandate, **every** backtest/bootstrap/inference run emits a 13-field ReproLog JSON record *before* any artifact write (skill `emit-repro-log`). Required fields:

| Field | Source | Purpose |
|---|---|---|
| `git_head` | `git rev-parse HEAD` | code commit |
| `git_dirty` | `git status --porcelain` non-empty | uncommitted-change flag |
| `pip_freeze_sha256` | SHA-256 of `uv pip freeze` output | environment fingerprint |
| `pip_freeze_path` | path to the saved freeze | full env recoverable |
| `dataset_checksums` | SHA-256 per input CSV | data provenance |
| `data_vendor` / `snapshot_date` | from ingest | vendor + snapshot |
| `rng_seed` | config | resampling/Kelly-sim determinism |
| `config_resolved_sha256` | SHA-256 of the fully-resolved config | exact parameterisation |
| `model_hash` | hash of fitted selection-model bytes | model identity |
| `run_id` / `timestamp_utc` | generated | run identity |
| `python_version` / `platform` | runtime | interpreter/OS |

The `SessionStart` hook injects git HEAD, pip-freeze, dataset checksums automatically; `SessionEnd` writes the audit trail. Every figure/table/workbook embeds its `run_id` in a footer so any artifact is traceable to its ReproLog.

**Determinism guarantees.** (i) All randomness flows from one seeded `numpy.random.Generator` passed explicitly (no global `np.random`). (ii) Bootstrap and Kelly Monte-Carlo record the seed in the ReproLog. (iii) DataFrame row order is sorted by `(date, match_id)` before any reduction so floating-point summation order is fixed.

### 3.3 Config-as-data

All tunables live in `config/*.yaml`, never in code:

```yaml
# config/baseline.yaml  (illustrative — values are placeholders to be set by empirical search)
universe:
  estimation: [E0, E1, SP1, I1, D1, F1, ...]   # football-data.co.uk league codes
  holdout: [WC2002, WC2006, WC2010, WC2014, WC2018, WC2022]
odds:
  decision_line: closing            # uses PSCH/PSCD/PSCA (Pinnacle closing)
  devig_method: shin                # {basic, shin, odds_ratio} — selected by calibration (§1.5)
selection:
  require_strict_underdog: true
staking:
  schemes: [flat, fixed_fraction, kelly, fractional_kelly]
  fixed_fraction_grid: [...]        # chosen by CV/drawdown objective, not by hand
  kelly_fraction_grid: [...]        # 0<f<=1; fractional-Kelly grid justified empirically
inference:
  sharpe_se: lo2002                 # {lo2002, opdyke2007}
  bootstrap: {method: stationary, n_resamples: ..., block_len: auto_politis_white}
  multiple_testing: {method: hansen_spa}   # or white_reality_check
seed: 20260616
```

No threshold (fraction grids, block length, bootstrap count, de-vig method) is fixed by fiat. Each is selected by an explicit procedure and that selection is itself logged: fixed-fraction and Kelly-fraction grids by walk-forward CV against a drawdown-penalised objective; bootstrap block length by the Politis–White (2004) automatic data-dependent rule; bootstrap `n_resamples` set so the Monte-Carlo standard error of the CI endpoints is below the reporting precision (documented per run). This satisfies the no-magic-numbers directive.

### 3.4 Tooling

- **uv** for the Python environment and lockfile.
- **ruff** for lint + format; CI fails on lint errors.
- **pytest** (+ **hypothesis** for property tests, §4.3); CI fails on any test failure.
- **nbstripout + nbqa ruff** on notebooks (no committed outputs, no notebook-author metadata — publishing-rule identity hygiene).
- **pandera/pydantic** for schema contracts; **pandas/numpy** for compute; **arch** for HAC/bootstrap utilities; **matplotlib** for figures; **openpyxl/xlsxwriter** for the workbook.

---

## 4. Testing strategy

### 4.1 Unit tests (odds math, staking, settlement edge cases)

| Target | Assertion |
|---|---|
| `implied_probs` | `qH+qD+qA = Σ`; `m = Σ−1 ≥ 0`; basic de-vig sums to 1 |
| `synthetic_dnb` | `o_DNB = side·(D−1)/D`; matches settlement table §1.3 exactly for win/draw/home cases |
| `synthetic_dnb` vs native | `o_DNB` reconciles with football-data.co.uk AH-0.0 (`AHh==0`) Pinnacle/avg columns within rounding/margin tolerance on overlapping league rows |
| `per_bet_variance` | fair win bet at `o`: `E[R]=0`, `Var[R]=o−1` (analytic benchmark, §1.4) |
| `kelly_fraction` | for fair-ish bet `f* = (p·b − q)/b` with `b = o_DNB−1`; `f*=0` when edge ≤ 0; `f*` capped at 1; refund branch handled (three-outcome Kelly, not two) |
| `fractional_kelly` | `f = λ·f*`, `0<λ≤1`; monotone in λ |
| settlement — knockout 90-min draw | a knockout match that is 1–1 at 90' (then decided in ET/pens) settles DNB as **refund**, not loss/win |
| settlement — extra time | ET goals never change a DNB settlement (90-min result only) |
| settlement — void/abandoned | match flagged void → stake refunded, excluded from win-ratio denominator, logged |
| ledger | `equity_t = equity_0 + Σ_{i≤t} pnl_i`; no negative bankroll under flat; ordering by `(date,match_id)` |

The three-outcome Kelly is a genuine edge case: DNB has win / refund / loss, so the optimal fraction maximises `E[log] = p·log(1+f(o−1)) + d·log(1+0) + (1−p−d)·log(1−f)`. The unit test checks the first-order condition numerically and degenerates to the textbook two-outcome formula when `d→0`.

### 4.2 Integration tests (full pipeline on a fixture)

A small committed fixture (`tests/fixtures/mini_league.csv`, a handful of hand-computed matches) is run through the whole DAG. Assertions: golden-file equality on `Ledger` and `MetricsBundle` (regenerated only via an explicit `--update-golden` flag), determinism across two runs with the same seed, and ReproLog presence/shape. The PIT canary (§3.1) is part of the integration suite.

### 4.3 Property-based invariants (Hypothesis)

Using **Hypothesis** (MacIver et al. 2019), generate random valid odds vectors and bet sequences and assert invariants that must hold for *all* inputs:

- **De-vig probabilities** are in `(0,1)` and sum to 1; margin `m ≥ 0`.
- **DNB monotonicity**: `o_DNB` strictly increasing in the side's win price and decreasing in draw probability; `o_DNB ≤` the raw win price.
- **Staking non-anticipation**: permuting *future* results never changes any stake (a structural anti-leakage property; a violation means staking read the result).
- **Ledger associativity/conservation**: total PnL equals the sum of per-bet PnL regardless of chunking; equity reconstruction is order-invariant up to fixed summation order.
- **Settlement totality**: every `(result ∈ {H,D,A,void})` maps to exactly one DNB outcome; no input is unhandled.
- **Flat-stake bound**: under flat staking, per-bet loss ≤ stake; bankruptcy impossible from a single bet.

Hypothesis shrinks any counterexample to a minimal failing case, which is logged into the test report.

---

## 5. Deliverable specification

The user receives four artifact classes: a **report card**, a **figures set**, a **tables set**, and an **Excel workbook**. All are generated from `MetricsBundle` and stamped with the `run_id`/ReproLog reference. Estimators are fixed below with citations; values (grids etc.) come from the empirical procedures in §3.3.

### 5.1 Metric definitions (single source of truth)

| Metric | Definition | Estimator / citation |
|---|---|---|
| Win ratio | wins / (wins + losses); refunds excluded from denominator | binomial; Wilson interval (Wilson 1927) |
| Strike on settled | wins / settled (refunds in denominator) | reported alongside, to avoid denominator ambiguity |
| ROI / yield | total profit / total staked | bootstrap CI (§5.6) |
| Profit (units) | Σ net PnL | — |
| Sharpe (per-bet) | `mean(R)/sd(R)` | SE via Lo (2002); single-strategy CI via Opdyke (2007) or Lo asymptotic |
| Sharpe difference (scheme A vs B) | `SR_A − SR_B` | studentized time-series bootstrap, Ledoit & Wolf (2008) |
| Deflated Sharpe | DSR, §6.3 | Bailey & López de Prado (2014) |
| MaxDD | max peak-to-trough of equity curve | path statistic |
| Drawdown duration | longest underwater interval | survival-style (cf. survival-analysis skill) |
| Turnover | Σ stake / mean bankroll per period | — |
| Risk of ruin | P(bankroll hits ruin barrier) | Kelly/quote: MacLean–Thorp–Ziemba (2010, 2011); Monte-Carlo + analytic gambler's-ruin where applicable |
| Closing-line value | `o_taken / o_closing − 1` (price), or prob-CLV | rationale: closing-odds efficiency (Angelini & De Angelis 2019); prob-CLV scored via Constantinou & Fenton (2012) |
| Capacity | max stake before market impact (proxy via posted limits) | reported as estimate with caveats |

**Estimator-verification gate (pre-implementation).** The citations above are matched to their roles, but the *numeric implementations* are not pinned in this architecture document and several could not be re-verified against source text in the authoring environment. Before any estimator is wired into `src/metrics.py`, each must be reproduced against its primary source and pinned by a unit test that reproduces a **published worked value** from that source:

- **Sharpe SE under non-i.i.d. returns** — Lo (2002), DOI [10.2469/faj.v58.n4.2453](https://doi.org/10.2469/faj.v58.n4.2453): reproduce the autocorrelation-adjusted SE factor against the paper's worked example.
- **Single-strategy Sharpe interval** — Opdyke (2007), DOI [10.1057/palgrave.jam.2250084](https://doi.org/10.1057/palgrave.jam.2250084).
- **Studentised time-series bootstrap for Sharpe differences** — Ledoit & Wolf (2008), DOI [10.1016/j.jempfin.2008.03.002](https://doi.org/10.1016/j.jempfin.2008.03.002): match the algorithm (HAC pre-whitening + studentisation + circular-block resampling) step-for-step.
- **Deflated Sharpe** — Bailey & López de Prado (2014), DOI [10.3905/jpm.2014.40.5.094](https://doi.org/10.3905/jpm.2014.40.5.094): denominator uses the observed `ŜR` (§6.3), cross-checked against the `quantstrat` reference code.
- **Shin de-vig z-solution** — Shin (1993), DOI [10.2307/2234240](https://doi.org/10.2307/2234240): reproduce the insider-trading-incidence `z` root and the implied-probability map.
- **football-data.co.uk column semantics** — confirm `PSCH/PSCD/PSCA` are Pinnacle *closing* 1X2 and that `AHh/AvgAHH/AvgAHA` at `AHh==0` are the AH-0.0 (= DNB) line, then verify the AH-0.0 ↔ synthetic-DNB reconciliation numerically (the §4.1 `synthetic_dnb vs native` test). The independently-verified facts in this document are the DNB identity `o_DNB = A·(D−1)/D` and the 3.25 worked example, the fair-win-bet `Var = o−1`, the three-outcome Kelly first-order condition and its negative-edge solution `f*=−0.0317 → do not bet` at `o=3.25` under the project's de-vigged probabilities (the positive-edge `f*=0.268` figure in §6.2 is an explicitly-flagged counterfactual, not a project result), the per-bet DSR worked value `≈0.46` (§6.3), and the dimensionless extreme-value multiplier `1.665` for `N=12` (which scales by `√V[ŜR]` to per-bet Sharpe units; `E[max SR]≈0.050` here, **not** `1.665`). Treat the above six as **unverified-implementation** until the matching unit tests pass.

### 5.2 Report card contents (acceptance: every section populated, every number traces to a `MetricsBundle` field, ReproLog referenced in footer)

1. **Header**: strategy one-liner; universe (estimation leagues + WC holdout); rebalance/decision line (closing); transaction-cost model; survivorship-bias treatment; data vendor + snapshot date. *(These six are mandated by the quant reporting rule and must appear verbatim.)*
2. **Headline metrics block**: profit, ROI/yield with bootstrap CI, overall win ratio with Wilson CI, per-bet Sharpe with CI, deflated Sharpe, MaxDD, risk-of-ruin at the chosen staking, number of bets, number of refunds/voids.
3. **By-odds-bucket panel**: win ratio + ROI + n per decimal-odds bucket (buckets defined by quantiles of `o_DNB`, not arbitrary cut points — the bucketing is data-driven and documented).
4. **By-stage panel**: group stage vs knockout (and per-round if n permits) win ratio, ROI, n. Flags the knockout-draw-refund volume explicitly.
5. **Staking comparison**: flat vs fixed-fraction vs Kelly vs fractional-Kelly grid — terminal wealth, growth rate, MaxDD, risk of ruin, and pairwise Sharpe-difference tests (Ledoit–Wolf).
6. **Out-of-sample (walk-forward) verdict**: estimation-universe in-sample vs World-Cup held-out OOS; the WC result is the headline OOS claim.
7. **Closing-line value section**: mean CLV, % bets beating close, CLV distribution — the market-efficiency reality check.
8. **Multiple-testing disposition**: how many staking/de-vig configs were tried and the SPA/Reality-Check-adjusted significance (Hansen 2005 / White 2000), plus DSR (Bailey & López de Prado 2014).
9. **Reproducibility footer**: `run_id`, git HEAD, config SHA-256, dataset checksums, seed, ReproLog path; AI-assistance statement (ICMJE 2026) for the publishing track.
10. **Limitations**: small-sample caveat, synthetic-DNB caveat, favourite-longshot prior, vig/de-vig sensitivity.

### 5.3 Figures list (acceptance: each renders deterministically from `MetricsBundle`, axis-labelled, CI bands where applicable, `run_id` in caption)

| # | Figure | Content |
|---|---|---|
| F-01 | Equity curve, per scheme | bankroll vs bet index/date for flat / fixed-fraction / Kelly / fractional-Kelly, overlaid |
| F-02 | Cumulative profit (units) over time | flat-stake profit path; in-sample vs WC OOS shaded |
| F-03 | Drawdown (underwater) curve | per scheme, depth over time |
| F-04 | Win ratio by odds bucket | bar with Wilson CIs; favourite-longshot signature visible |
| F-05 | ROI/yield by odds bucket | bar with bootstrap CIs; zero line |
| F-06 | Win ratio / ROI by stage | group vs knockout (and per-round) |
| F-07 | Staking-grid frontier | terminal growth rate vs MaxDD across fixed-fraction and Kelly-fraction grid (efficient-frontier-style) |
| F-08 | Risk-of-ruin curve | P(ruin) vs staking fraction; ruin barrier annotated |
| F-09 | Minimum-bankroll curve | starting bankroll needed to keep P(ruin) ≤ target, vs target |
| F-10 | CLV distribution | histogram of `o_taken/o_close − 1`; mean and %>0 annotated |
| F-11 | Calibration / reliability diagram | predicted vs realised underdog-win frequency; Brier/RPS in legend |
| F-12 | Bootstrap distribution of Sharpe (and of ROI) | with CI and DSR threshold marked |
| F-13 | Walk-forward OOS bars | per-fold and held-out-WC ROI/Sharpe |
| F-14 | Sensitivity heatmap (supplementary) | ROI/Sharpe across de-vig method × staking scheme × decision line |
| F-15 | Sharpe-difference CIs (supplementary) | Ledoit–Wolf pairwise scheme comparison forest plot |

### 5.4 Tables list (acceptance: numeric, CI columns present, machine-regenerable, units stated)

| # | Table | Columns |
|---|---|---|
| T-01 | Headline summary | metric, point estimate, CI, n |
| T-02 | By-odds-bucket | bucket range, n, wins, win ratio (Wilson CI), ROI (boot CI), mean `o_DNB` |
| T-03 | By-stage | stage, n, win ratio, ROI, refunds (knockout draws) |
| T-04 | Staking comparison | scheme, terminal wealth, growth rate, Sharpe (CI), MaxDD, risk of ruin, turnover |
| T-05 | Staking-grid scan | fraction, growth, MaxDD, P(ruin) — full grid behind F-07 |
| T-06 | Minimum-bankroll table | target P(ruin), required starting bankroll, implied max stake |
| T-07 | CLV table | mean CLV, median, %>0, by stage and odds bucket |
| T-08 | Walk-forward folds | fold, train span, test span, n, ROI, Sharpe |
| T-09 | Deflated-Sharpe worksheet | observed SR, N trials, skew, kurtosis, T, E[max SR], DSR p-value |
| T-10 | Multiple-testing register | configs tried, best statistic, SPA/RC adjusted p, FWER disposition |
| T-11 | Pairwise Sharpe-difference | scheme A, scheme B, ΔSR, Ledoit–Wolf bootstrap CI, contains-zero flag |
| T-12 | Reproducibility ledger | run_id, git HEAD, config SHA, dataset SHAs, seed, ReproLog path |

### 5.5 Excel workbook tabs (`artifacts/tables/backtest_results_<run_id>.xlsx`) — acceptance: opens without repair, formulas where live recompute is useful, one README tab, `run_id` on every sheet footer

| Tab | Contents |
|---|---|
| `README` | strategy description, universe, vendor/snapshot, ReproLog reference, sheet index, AI-assistance statement |
| `Bets` | full settled-bet ledger: date, match, side, `H,D,A`, `o_DNB`, `p`,`d`, stake (per scheme), result, DNB outcome, PnL |
| `Equity` | per-bet bankroll path for each scheme (drives F-01/F-02) |
| `Summary` | T-01 headline metrics with CIs |
| `ByOdds` | T-02 |
| `ByStage` | T-03 |
| `Staking` | T-04 + T-05 grid |
| `MinBankroll` | T-06; live formula `min_bankroll = max_stake / target_fraction` style cells |
| `CLV` | T-07 |
| `WalkForward` | T-08 |
| `DeflatedSharpe` | T-09 with the formula laid out in cells (§6.3) so the user can audit it |
| `MultipleTesting` | T-10 + T-11 |
| `ReproLog` | T-12 plus a copy of the resolved config |

### 5.6 Bootstrap CIs for ROI / yield and Sharpe

Because bets are time-ordered and may exhibit serial dependence (overlapping tournaments, clustered matchdays), CIs use the **stationary bootstrap** (Politis & Romano 1994) with automatic block length (Politis & White 2004); the i.i.d. percentile bootstrap is reported only as a sensitivity. For Sharpe-ratio *differences* between staking schemes, the **studentized time-series bootstrap** of Ledoit & Wolf (2008) is used (it is valid under heavy tails and serial correlation, unlike Jobson–Korkie/Memmel). For a *single* strategy's Sharpe, the asymptotic SE of Lo (2002) and the Opdyke (2007) interval are reported.

---

## 6. Worked numerics for the analysis layer

### 6.1 Single-bet settlement (numbers)

Away underdog, `A=4.50, D=3.60 ⇒ o_DNB=3.25` (§1.3). Flat 1-unit stake outcomes: away win `+2.25`; draw `0`; home win `−1.00`.

### 6.2 Kelly for the synthetic DNB (three-outcome)

The optimal-fraction formula is `g(f)=p·log(1+f(o−1)) + d·log(1) + (1−p−d)·log(1−f)`, with first-order condition `p·(o−1)/(1+f(o−1)) = (1−p−d)/(1−f)`. The point of this subsection is to exercise the **mechanics** of that formula and to demonstrate the MacLean–Thorp–Ziemba (2010) "wagers may be very large" property, which is only visible when the edge is positive. **The illustrative `(p,d)` below is a deliberate counterfactual: it assumes a positive model edge that contradicts the project's own negative-EV prior for this instrument and must not be read as expected strategy behaviour.**

> **Caveat — sign disagreement with the project prior.** Plugging the project's actual de-vigged probabilities for `o=3.25` (`p=0.2105, d=0.2632`; calc doc §8.2, reproduced in §1.4 above) into the same formula gives `f* = (0.2105·2.25 − 0.5263)/[2.25·(0.2105+0.5263)] = −0.0526/1.658 = −0.0317 < 0 ⇒ **do not bet** (stake 0; there is no short side in a DNB market). That is the realistic case. The positive-edge numbers immediately below are a **mechanical formula exercise only** — they presuppose a model that disagrees with the closing line by +14 percentage points on the underdog win probability (`0.36` vs the market-implied `0.2105`), a disagreement the favourite-longshot literature gives no reason to expect (calc doc §5, §8.2; edge-flb doc). Do not interpret the `26.8%`-Kelly stake as a stake that is ever on the table for this strategy.

Counterfactual mechanics. With `o=3.25 (b=2.25)`, **suppose hypothetically** the model said `p=0.36, d=0.27` (so loss prob `0.37`), giving a fictitious edge `E[R]=0.36·2.25 − 0.37 = 0.81 − 0.37 = 0.44 > 0`. Then the first-order condition solves as

```
0.36·2.25/(1+2.25f) − 0.37/(1−f) = 0
0.81(1−f) = 0.37(1+2.25f)
0.81 − 0.81f = 0.37 + 0.8325f
0.44 = 1.6425f  ⇒  f* ≈ 0.268
```

Full Kelly would stake ~26.8% of bankroll — illustrating the "wagers may be very large" bad property (MacLean–Thorp–Ziemba 2010) **for a hypothetical positive edge**; a fractional-Kelly `λ=0.25` gives `f≈0.067`. `λ` is selected on the staking grid against a drawdown-penalised CV objective, not chosen by hand. Under the project's real (negative) edge, the staking module returns `f*=0` for this instrument and Kelly never sizes a position; the large-stake illustration is retained only to document the formula's behaviour, not the strategy's.

### 6.3 Deflated Sharpe (the multiple-testing correction the report card hinges on)

The strategy is selected after trying `N` configurations (de-vig × staking × line). The **expected maximum** Sharpe under `N` independent null trials (Bailey & López de Prado 2014) is

```
E[max SR] ≈ √V[ŜR] · ( (1−γ)·Φ⁻¹(1 − 1/N) + γ·Φ⁻¹(1 − 1/(N·e)) )
```

with `γ ≈ 0.5772` (Euler–Mascheroni) and `Φ⁻¹` the inverse standard normal CDF. The **deflated Sharpe** is

```
DSR = Φ( (ŜR − SR₀)·√(T−1) / √(1 − γ̂₃·ŜR + ((γ̂₄−1)/4)·ŜR²) )
```

where `SR₀ = E[max SR]` is the benchmark, `T` the number of bets, and `γ̂₃, γ̂₄` the skewness and (non-excess) kurtosis of the per-bet returns. **The Sharpe inside the denominator is the observed `ŜR`, not the benchmark `SR₀`.** The denominator is the sampling standard deviation of the Sharpe *estimator* evaluated at the observed point (the Probabilistic-Sharpe-Ratio variance term of Bailey & López de Prado 2014; the DSR is the PSR with threshold `SR₀ = E[max SR]`), so it is a property of the estimator at `ŜR`, not of the benchmark. This matches the reference implementation in `quantstrat` (`braverock/quantstrat`, `R/deflated.Sharpe.R`), whose denominator is `sqrt(1 − skew·SR + (kurt−1)/4·SR²)` with `SR` the observed Sharpe. Putting `SR₀` there is a common transcription error and yields the wrong significance disposition.

**Two distinct variance objects — do not conflate.** The formula uses two different second-moment quantities, in two different places:

- `V[ŜR]` (inside `E[max SR]`, §6.3 below) is the **cross-trial variance of the `N` Sharpe estimates** produced by the config search — Bailey & López de Prado's `V[ŜR_n]`, the spread of the grid's Sharpe ratios. It calibrates *how high a Sharpe the search can manufacture by chance*. (See methodology doc §8.2, which writes this term explicitly as "the variance of the Sharpe ratios across the N trials.")
- The DSR **denominator** above is the **within-strategy sampling standard deviation** of the single selected strategy's Sharpe *estimator* — the PSR/Lo–Mertens non-normality-robust SE evaluated at `ŜR`. It calibrates *how precisely the selected strategy's Sharpe is measured at `T` bets*.

These are different objects on the same per-bet scale and must not be substituted for one another.

**Unit conventions (mandatory).** (i) `ŜR` and `SR₀` must be in identical **per-bet (non-annualised)** units, *and* `V[ŜR]` must be the cross-trial variance of those same per-bet Sharpe estimates — mixing an annualised Sharpe into a `T = per-bet-count` formula produces a meaningless DSR. A per-bet Sharpe of order 2.0 is physically impossible for a betting strategy: it implies a t-statistic `√384·2.0 ≈ 39`. Realistic per-bet Sharpe for this instrument is `O(10⁻²)` (methodology doc §8.4 uses `ŜR = 0.045`), consistent with the near-zero edge of §1.4. (ii) `γ̂₄` is **non-excess** kurtosis (`γ̂₄ = 3` under normality, so `(γ̂₄−1)/4 = 1/2` recovers the Mertens normal-case SR-variance factor `1 + ŜR²/2`).

**Serial-dependence caveat (the DSR denominator is anti-conservative here).** The Bailey & López de Prado denominator is the **IID-non-normal** (Lo/Mertens skew/kurtosis-corrected) Sharpe SE; it carries **no HAC / serial-dependence adjustment**. This document and the sibling methodology doc (§§2.3, 2.8, 5, 10) establish that bet returns are serially dependent through tournament/matchday clustering, which is precisely why single-strategy and pairwise Sharpe inference is routed to Lo's `η(q)`-scaled SE, Opdyke (2007), Ledoit–Wolf (2008), and Newey–West/Andrews HAC. Under positive serial dependence the true long-run variance of `ŜR` exceeds the IID value, so the plain DSR denominator **understates** the estimator variance and makes the deflated-Sharpe test **anti-conservative** — the opposite of its intended role as the binding significance gate. Mitigation: inflate the denominator by the long-run-variance factor `η(q)` (Lo 2002) or the Andrews-QS estimate already specified in the methodology doc, **and** report the DSR alongside an Opdyke (2007) / Ledoit–Wolf (2008) serially-robust significance check, treating the **serially-robust check as binding** when the two disagree. DSR is the probability the true Sharpe exceeds the selection-inflated benchmark; a non-deflated positive Sharpe on ~384 WC bets after a config search is exactly the "statistical mirage" DSR is built to catch — but only the HAC-corrected version of it can be trusted as the gate.

**Worked number (per-bet units throughout).** Trying `N=12` configs, the two normal quantiles are `Φ⁻¹(1−1/12)=Φ⁻¹(0.9167)≈1.383` and `Φ⁻¹(1−1/(12e))=Φ⁻¹(1−0.0307)=Φ⁻¹(0.9693)≈1.871`, so the bracket is `0.4228·1.383 + 0.5772·1.871 ≈ 0.585 + 1.080 = 1.665`. This `1.665` is the **dimensionless multiplier**, *not* a Sharpe; it must be scaled by `√V[ŜR]` (the cross-trial SD of the per-bet Sharpe estimates) to land in per-bet Sharpe units. Take a per-bet cross-trial spread `√V[ŜR] ≈ 0.03` — the grid's per-bet Sharpe estimates scatter on the `O(10⁻²)` scale established in §1.4 and methodology doc §8.4. Then

```
E[max SR] = √V[ŜR] · 1.665 = 0.03 · 1.665 ≈ 0.0499   (per-bet Sharpe units)
```

So `SR₀ ≈ 0.050`. Now deflate an **observed per-bet** `ŜR = 0.045` (methodology doc §8.4 value), with `γ̂₃ = +0.6`, `γ̂₄ = 4.5`, `T = 384`. The skewness here is the moment of the **per-bet DNB return sequence**, which is structurally *positively* skewed (a small-probability large gain at `o−1` against a `−1` floor), so `γ̂₃ > 0`; direct moment computation over realistic de-vigged 1X2 vectors gives skew in `[+0.4, +2.4]`, **never negative** (sibling methodology doc §2.7, §8.4):

```
denominator = √(1 − (+0.6)(0.045) + (4.5−1)/4·0.045²) = √(1 − 0.0270 + 0.00177) = √0.97477 = 0.9873
numerator   = (0.045 − 0.0499)·√(384−1) = (−0.0049)·19.57 = −0.0968
DSR = Φ(−0.0968 / 0.9873) = Φ(−0.0980) ≈ 0.461
```

A `DSR ≈ 0.461` (far below 0.95) is the **correct, internally consistent** disposition: on `T=384` World-Cup bets after a 12-config search, a per-bet Sharpe of `0.045` does **not** clear the selection-inflated noise ceiling `SR₀ ≈ 0.050` — exactly the underpowered-mirage outcome the project prior predicts. For scale calibration, the Lo (2002) IID sampling SD of this `ŜR` at `T=384` is `√((1+ŜR²/2)/T) = √(1.001/384) ≈ 0.051`, the same `O(10⁻²)` order as `SR₀` — confirming the two illustrative pieces now share per-bet units (the earlier `√V[ŜR]≈1` / `ŜR=2.0` figures were annualised-scale values incorrectly fed a per-bet `T`).

*Serial-dependence inflation (per the caveat above).* With a modest matchday-clustering autocorrelation `ρ₁ = 0.10`, the long-run-variance inflation `(1+ρ)/(1−ρ) = 1.222` lifts the denominator to `0.9873·√1.222 = 1.0914`, giving `DSR = Φ(−0.0968/1.0914) = Φ(−0.0887) ≈ 0.465`. Here the sign disposition is unchanged (the strategy fails the gate either way), but in any borderline case the HAC-inflated, serially-robust check is the binding one, never the plain IID DSR.

---

## 7. Acceptance criteria (definition of done, per artifact)

| Artifact | Done when… |
|---|---|
| Pipeline | `python -m src.run --config config/baseline.yaml` runs the full DAG, emits a ReproLog, and produces report+figures+tables+workbook with zero manual steps; two runs at the same seed are byte-identical on `Ledger` and `MetricsBundle`. |
| PIT contract | contract test passes (all features `≤ t`, labels isolated) **and** the canary dominates on the fixture. |
| Unit tests | all §4.1 cases pass, including knockout-90-min-draw refund and the `Var=o−1` analytic benchmark. |
| Integration | golden `Ledger`/`MetricsBundle` match; ReproLog present and shape-valid. |
| Property tests | Hypothesis suite (§4.3) green with no shrunk counterexamples. |
| Report card | all 10 sections populated; the six mandated reporting fields (universe, rebalance/line, cost model, survivorship treatment, vendor, snapshot) present; every prose number traceable; AI-assistance statement present (publishing track). |
| Figures | F-01…F-13 render with labels and CI bands; F-14/F-15 (supplementary) present; each caption carries `run_id`. |
| Tables | T-01…T-12 numeric with CI columns; regenerable via CLI. |
| Workbook | opens without repair in Excel; all listed tabs present; `DeflatedSharpe` tab shows the live formula; `run_id` on every sheet. |
| Metrics | win ratio (overall + by odds bucket + by stage), ROI/yield with bootstrap CIs, equity/profit curves per scheme, the flat/fixed/Kelly/fractional-Kelly grid, drawdown + risk-of-ruin curves, minimum-bankroll table, CLV, deflated Sharpe, and walk-forward OOS all present. |
| Reproducibility | every artifact maps to a ReproLog; `git_dirty=false` for any artifact intended for the deliverable. |
| Multiple-testing | the config-search count is registered and the SPA/Reality-Check + DSR disposition is reported; no single result is presented as significant without the correction. |

---

## Citations

1. Kelly, J. L. (1956). A New Interpretation of Information Rate. *Bell System Technical Journal*, 35(4), 917–926. DOI: [10.1002/j.1538-7305.1956.tb03809.x](https://doi.org/10.1002/j.1538-7305.1956.tb03809.x)
2. MacLean, L. C., Thorp, E. O., & Ziemba, W. T. (2010). Long-term capital growth: the good and bad properties of the Kelly and fractional Kelly capital growth criteria. *Quantitative Finance*, 10(7), 681–687. DOI: [10.1080/14697688.2010.506108](https://doi.org/10.1080/14697688.2010.506108)
3. MacLean, L. C., Thorp, E. O., & Ziemba, W. T. (Eds.) (2011). *The Kelly Capital Growth Investment Criterion: Theory and Practice*. World Scientific. DOI: [10.1142/7598](https://doi.org/10.1142/7598)
4. Lo, A. W. (2002). The Statistics of Sharpe Ratios. *Financial Analysts Journal*, 58(4), 36–52. DOI: [10.2469/faj.v58.n4.2453](https://doi.org/10.2469/faj.v58.n4.2453)
5. Opdyke, J. D. (2007). Comparing Sharpe ratios: So where are the p-values? *Journal of Asset Management*, 8(5), 308–336. DOI: [10.1057/palgrave.jam.2250084](https://doi.org/10.1057/palgrave.jam.2250084)
6. Ledoit, O., & Wolf, M. (2008). Robust performance hypothesis testing with the Sharpe ratio. *Journal of Empirical Finance*, 15(5), 850–859. DOI: [10.1016/j.jempfin.2008.03.002](https://doi.org/10.1016/j.jempfin.2008.03.002)
7. Bailey, D. H., & López de Prado, M. (2014). The Deflated Sharpe Ratio: Correcting for Selection Bias, Backtest Overfitting, and Non-Normality. *The Journal of Portfolio Management*, 40(5), 94–107. DOI: [10.3905/jpm.2014.40.5.094](https://doi.org/10.3905/jpm.2014.40.5.094)
8. Bailey, D. H., Borwein, J., López de Prado, M., & Zhu, Q. J. (2017). The Probability of Backtest Overfitting. *Journal of Computational Finance*, 20(4), 39–69. DOI: [10.21314/JCF.2016.322](https://doi.org/10.21314/JCF.2016.322)
9. White, H. (2000). A Reality Check for Data Snooping. *Econometrica*, 68(5), 1097–1126. DOI: [10.1111/1468-0262.00152](https://doi.org/10.1111/1468-0262.00152)
10. Hansen, P. R. (2005). A Test for Superior Predictive Ability. *Journal of Business & Economic Statistics*, 23(4), 365–380. DOI: [10.1198/073500105000000063](https://doi.org/10.1198/073500105000000063)
11. Politis, D. N., & Romano, J. P. (1994). The Stationary Bootstrap. *Journal of the American Statistical Association*, 89(428), 1303–1313. DOI: [10.1080/01621459.1994.10476870](https://doi.org/10.1080/01621459.1994.10476870)
12. Politis, D. N., & White, H. (2004). Automatic Block-Length Selection for the Dependent Bootstrap. *Econometric Reviews*, 23(1), 53–70. DOI: [10.1081/ETC-120028836](https://doi.org/10.1081/ETC-120028836)
13. Newey, W. K., & West, K. D. (1994). Automatic Lag Selection in Covariance Matrix Estimation. *Review of Economic Studies*, 61(4), 631–653. DOI: [10.2307/2297912](https://doi.org/10.2307/2297912)
14. Andrews, D. W. K. (1991). Heteroskedasticity and Autocorrelation Consistent Covariance Matrix Estimation. *Econometrica*, 59(3), 817–858. DOI: [10.2307/2938229](https://doi.org/10.2307/2938229)
15. Shin, H. S. (1993). Measuring the Incidence of Insider Trading in a Market for State-Contingent Claims. *The Economic Journal*, 103(420), 1141–1153. DOI: [10.2307/2234240](https://doi.org/10.2307/2234240)
16. Štrumbelj, E. (2014). On determining probability forecasts from betting odds. *International Journal of Forecasting*, 30(4), 934–943. DOI: [10.1016/j.ijforecast.2014.02.008](https://doi.org/10.1016/j.ijforecast.2014.02.008)
17. Angelini, G., & De Angelis, L. (2019). Efficiency of online football betting markets. *International Journal of Forecasting*, 35(2), 712–721. DOI: [10.1016/j.ijforecast.2018.07.008](https://doi.org/10.1016/j.ijforecast.2018.07.008)
18. Constantinou, A. C., & Fenton, N. E. (2012). Solving the Problem of Inadequate Scoring Rules for Assessing Probabilistic Football Forecast Models. *Journal of Quantitative Analysis in Sports*, 8(1). DOI: [10.1515/1559-0410.1418](https://doi.org/10.1515/1559-0410.1418)
19. Brier, G. W. (1950). Verification of Forecasts Expressed in Terms of Probability. *Monthly Weather Review*, 78(1), 1–3. DOI: [10.1175/1520-0493(1950)078<0001:VOFEIT>2.0.CO;2](https://doi.org/10.1175/1520-0493(1950)078%3C0001:VOFEIT%3E2.0.CO;2)
20. Murphy, A. H. (1973). A New Vector Partition of the Probability Score. *Journal of Applied Meteorology*, 12(4), 595–600. DOI: [10.1175/1520-0450(1973)012<0595:ANVPOT>2.0.CO;2](https://doi.org/10.1175/1520-0450(1973)012%3C0595:ANVPOT%3E2.0.CO;2)
21. Wilson, E. B. (1927). Probable Inference, the Law of Succession, and Statistical Inference. *Journal of the American Statistical Association*, 22(158), 209–212. DOI: [10.1080/01621459.1927.10502953](https://doi.org/10.1080/01621459.1927.10502953)
22. MacIver, D. R., Hatfield-Dodds, Z., et al. (2019). Hypothesis: A new approach to property-based testing. *Journal of Open Source Software*, 4(43), 1891. DOI: [10.21105/joss.01891](https://doi.org/10.21105/joss.01891)
23. Football-Data.co.uk. Notes on data columns (1X2 closing odds PSCH/PSCD/PSCA; Asian-Handicap AHh/AvgAHH/AvgAHA). URL: [https://www.football-data.co.uk/notes.txt](https://www.football-data.co.uk/notes.txt) (accessed 2026-06-16)
24. International Committee of Medical Journal Editors (ICMJE). Recommendations (updated January 2026), AI-assistance disclosure. URL: [https://www.icmje.org/recommendations/](https://www.icmje.org/recommendations/)

---

## Open questions and assumptions to validate

1. **DNB settlement convention for knockout matches.** The architecture settles DNB on the **90-minute** result (refund on a 90' draw, regardless of ET/penalty outcome), matching Asian-Handicap 0.0 convention. Confirm this matches the actual book the user intends to price against — some operators settle "DNB" on the full result including ET in knockouts. The settlement module is config-switchable; the default must be justified against a specific bookmaker rulebook.
2. **De-vig method selection.** §3.3 leaves `devig_method ∈ {basic, shin, odds_ratio}` to be chosen by calibration (Brier/RPS). Validate that the chosen method's calibration advantage on the *estimation* universe transfers to the *World Cup* holdout (it may not — international football has different scoring/draw structure).
3. **Independence assumption for `N` in the deflated Sharpe.** Bailey & López de Prado's `E[max SR]` assumes independent trials; the config search (de-vig × staking × line) produces correlated trials, so naive `N` overstates the penalty's precision. Validate with an effective-number-of-trials estimate or the PBO (probability of backtest overfitting) procedure (Bailey et al. 2017) as a cross-check.
4. **Bootstrap dependence structure.** The stationary bootstrap assumes weak stationarity of the bet-return series; tournament clustering and the regime change at the 2026 expansion (64→104 matches, 32→48 teams) may break stationarity across the panel. Validate stationarity (e.g. on the estimation universe) before trusting the CIs; consider tournament-block resampling.
5. **Closing-line availability for the World Cup sample.** football-data.co.uk PSC* (Pinnacle closing) coverage is strong for leagues; confirm the World Cup odds source carries a genuine *closing* line (not pre-match) so CLV is well-defined and the OOS test uses the same decision line as estimation.
6. **Capacity/limits proxy.** The capacity metric uses posted limits as a market-impact proxy; for World Cup DNB markets this proxy quality is unverified. Flag as low-confidence unless a better liquidity source is found.
7. **2026 structural break.** Whether estimation-universe parameters (staking fractions selected by CV) remain valid for the 104-match 2026 format is untested; the walk-forward design must keep 2026 strictly out-of-sample and report it separately.
