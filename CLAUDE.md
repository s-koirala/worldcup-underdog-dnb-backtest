# Project: worldcup-underdog-dnb-backtest

Quant backtest project. The path contains `backtest`, so **quant-project rules apply**
(time-series integrity, HAC/Newey-West inference, bootstrap CIs on Sharpe, White/Hansen
multiple-testing, full backtest reporting). Population-health and publishing rules do not apply.

## Strategy under test

Back the underdog (higher decimal win price) in FIFA World Cup matches via Draw-No-Bet
(stake refunded on a 90-minute draw; equivalent to Asian Handicap 0.0). Synthetic DNB from
1X2 decimal odds (H, D, A) for the away side: stake `1/D` on the draw + `(1 - 1/D)` on the
away win → effective DNB decimal odds `= A·(D-1)/D`.

## Non-negotiables for this project

- **No look-ahead.** Underdog label and every feature computable at kickoff from pre-match
  (closing) odds only. Settlement on the **90-minute result** (knockout extra time / penalties
  do not change the bet outcome).
- **Underpowered World Cup sample.** Estimate on the expanded domestic-league universe
  (football-data.co.uk, Pinnacle closing 1X2 + Asian-Handicap); treat the World Cup as a
  held-out subsample. Report power explicitly.
- **No magic numbers.** Every threshold / stake fraction / block length is grid/CV/bootstrap
  selected with a documented rationale and citation.
- **Multiple-testing register.** The staking grid (flat / fixed-fraction / Kelly / fractional
  Kelly) and any rule variants form one family — correct with White 2000 / Hansen 2005 and
  report the deflated Sharpe (Bailey & López de Prado 2014).
- **Reproducibility envelope** per run: git HEAD, project-venv pip freeze SHA-256, dataset
  checksum, RNG seed, model hash → `logs/`.

## Tooling

uv (env), ruff (lint/format), pytest, nbstripout + nbqa on notebooks.
