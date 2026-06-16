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
- **Phase 3 — staking & risk:** [src/staking.py](src/staking.py) (flat / fixed-fraction / level-to-odds /
  Kelly / fractional-Kelly, non-anticipating), [src/costs.py](src/costs.py) (net-of-cost: data-calibrated
  slippage + one-tick leg-out stress + BFEC commission → effective overround), [src/ledger.py](src/ledger.py)
  (gross+net PnL, conservation-checked), [src/vector_kelly.py](src/vector_kelly.py) (cvxpy/Clarabel),
  [src/ruin.py](src/ruin.py) + [src/frontier.py](src/frontier.py) (matchday-block bootstrap ruin / min-bankroll,
  Busseti–Ryu–Boyd RCK, growth–drawdown frontier). **Honest result:** under the frozen Shin de-vig, 0 of
  49,628 league bets are positive-EV → `λ*=0` ("do not bet"). 279 tests.

## Running the pipeline (canonical entrypoint)

The project pins native dependencies (cvxpy + Clarabel for the convex vector-Kelly solve;
ADR-0001) in a `uv`-managed virtual environment. **Every invocation must run under that env**
— a bare `python -m src.run` resolves to the system interpreter, which lacks the pinned deps
and crashes with `ModuleNotFoundError: No module named 'cvxpy'` (the stake stage hard-imports
cvxpy via [src/vector_kelly.py](src/vector_kelly.py)). Sync the env once, then prefix every run
with `uv run`:

```bash
uv sync --frozen                                  # provision the pinned env (out-of-the-box)
uv run python -m src.run --config config/baseline.yaml --stage stake   # run a stage
```

The [Makefile](Makefile) wraps the canonical chain (every target prefixes `uv run`):

```bash
make sync                # uv sync --frozen
make reproduce-staking   # the Phase-3 staking + bankroll/risk stage
make reproduce           # the full per-phase chain (ingest → … → report)
make check               # ruff lint/format + pytest (the CI gate)
```

Bare `python -m src.run` works **only** if the project venv is already the active interpreter
(e.g. `source .venv/bin/activate` first); otherwise use `uv run` as above. Running `--stage`
without `uv run` against a global interpreter is unsupported and emits an actionable error.

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
