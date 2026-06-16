# worldcup-underdog-dnb-backtest

Backtest of a FIFA World Cup betting strategy: **back the underdog** (the team with the
higher decimal win price / lower implied win probability) using **Draw-No-Bet** (DNB,
"tie no bet" — stake refunded on a 90-minute draw; equivalent to Asian Handicap 0.0).

## Status

Phases 0–1 complete; Phases 2–5 in progress. Full history in [CHANGELOG.md](CHANGELOG.md);
implementation follows [docs/protocol/plan_phased-workplan_2026-06-16.md](docs/protocol/plan_phased-workplan_2026-06-16.md).
Each phase is built and verified by a multi-agent audit-remediate workflow.

- **Phase 0 — reproducibility scaffold:** pinned `uv` env (Python 3.11.9), 13-key ReproLog,
  order-independent seeding, pre-registered [design.md](docs/protocol/design.md), frozen
  pre-data power record, multiple-testing register, ADRs. 69 tests.
- **Phase 1 — data:** point-in-time `data/processed/matches.parquet` of **50,071 matches** —
  49,687 domestic-league (football-data.co.uk, 7 seasons × 21 divisions, season-conditional
  Pinnacle/consensus closing reference) + 384 World-Cup hold-out (2002–2022; results from
  jfjelstul/martj42, 90-minute FTR reconstructed). World-Cup **odds** have no public source,
  so the transfer test is pending-odds and the league universe carries the estimation. 109 tests.
- **Phase 2 — DNB core:** [src/pricing.py](src/pricing.py) (synthetic DNB `o = W·(D−1)/D`, Shin/power/basic
  de-vig with a reproduced Shin-`z` estimator gate), [src/selection.py](src/selection.py) (underdog
  labelling), [src/settlement.py](src/settlement.py) (90-minute three-way settlement; knockout draw →
  push), and the EV / variance / push-Kelly closed forms. Reconciled bit-for-bit against the panel. 195 tests.

## Project thesis and honest prior

The World-Cup-only odds sample is small (~384 matches with clean odds, 2002–2022) and
statistically underpowered. The favorite-longshot bias plus bookmaker margin imply a
**likely-negative expected-value prior** for underdog betting. The estimation universe is
therefore expanded to domestic leagues (football-data.co.uk, which carries Pinnacle closing
1X2 and Asian-Handicap = DNB columns); the World Cup is treated as a held-out subsample.
The deliverable **quantifies** the edge (or its absence) with confidence intervals; it does
not assume profitability.

## Layout

```
docs/research/    audited research documents (calculations, data, methodology, staking, edge, architecture)
docs/protocol/    phased work plan, pre-registration / design docs
docs/decisions/   architecture decision records (ADRs)
data/raw/         immutable source pulls
data/processed/   cleaned, point-in-time-correct datasets
data/external/    third-party reference data
src/              pipeline modules
notebooks/        exploratory analysis (nbstripout on save)
artifacts/figures artifacts/tables artifacts/reports   rendered deliverables
config/           config-as-data (stake grids, families, splits)
logs/             reproducibility logs (ReproLog JSON per run)
tests/            unit + integration tests
```

## Standards

Time-series integrity (no look-ahead, walk-forward CV), bootstrap CIs on Sharpe/ROI,
multiple-testing correction across the staking grid, deflated Sharpe for selection bias, and
a reproducibility envelope (git HEAD, pip freeze, dataset checksum, RNG seed) logged per run.
See [docs/protocol/](docs/protocol/).

## AI-assistance

Research synthesis, planning, and code authored with Claude (Opus 4.8) under human direction;
all citations and methods are independently verified against primary sources. Reproducibility
logs under [logs/](logs/).
