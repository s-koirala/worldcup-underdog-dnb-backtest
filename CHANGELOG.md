# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog 1.1.0](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning 2.0.0](https://semver.org/spec/v2.0.0.html).

Each entry corresponds to a phase of [docs/protocol/plan_phased-workplan_2026-06-16.md](docs/protocol/plan_phased-workplan_2026-06-16.md),
built and verified via multi-agent audit-remediate workflows.

## [Unreleased]

- Phase 3 (staking grid + bankroll / risk-of-ruin simulation) — next.

## [0.2.0] - 2026-06-16 — Phase 2: DNB construction, underdog labelling, 90-minute settlement

### Added
- `src/pricing.py`: synthetic DNB identity `o_DNB = W·(D−1)/D` (reconciled bit-for-bit with the ingest
  arithmetic on 49,687 rows; `matches.parquet` content SHA unchanged); `implied_probs`/overround; a
  de-vig dispatcher (`basic`/`shin`/`power`, Shin default) returning fair simplex probabilities; the
  conditional `q_W = p_W/(1−p_D)`; and the synthetic-vs-quoted margin wedge. Shin runs on the three-way
  1X2 book — under-round draw-dropped residuals are rejected fail-closed.
- `src/selection.py` (underdog = higher decimal win price; the frozen near-tie branch) and
  `src/settlement.py` (three-way 90-minute DNB map; knockout extra-time/penalty draws settle as a push;
  void → refund, excluded from the win-ratio denominator).
- EV, three-point `Var_DNB`, and the push-Kelly fraction `f*` closed forms (negative edge → `f*=0`;
  degenerates to two-outcome Kelly as the draw probability → 0).
- Estimator-verification gate: Shin `z` reproduced against the Jullien–Salanié closed form (three-way
  z=0.0279; two-way matched to ~1e-9). Unit + Hypothesis property tests (195 total).

### Fixed
- `test_reprolog` / `test_run_dry_run` git-head assertions updated for the committed-repo state (they
  previously assumed the pre-first-commit zero-commit state).

## [0.1.0] - 2026-06-16 — Phase 1: data acquisition and validation

### Added
- Point-in-time canonical panel `data/processed/matches.parquet`: **50,071 matches**
  (49,687 domestic-league + 384 World-Cup hold-out), 35 canonical fields; every row carries
  `refC_*`, `ref_book`, `underdog_side`, `o_dnb_underdog`, `overround`, and a 90-minute `FTR`.
- League ingest (`src/ingest.py`): 147 football-data.co.uk Main-league CSVs (7 seasons
  2019/20–2025/26 × 21 divisions) with per-file SHA-256 provenance; empirical-quantile
  data-quality gates (no hard-coded plausibility bands); no silent row drops.
- Season-conditional closing reference price: Pinnacle (`PSC*`) ≤ 2024/25, consensus
  (`AvgC*`/`BFEC*`) ≥ 2025/26 after the 2025-07-23 Pinnacle public-feed degradation. The
  degradation notice was round-tripped verbatim and archived under `data/raw/provenance/`
  (provenance gate passed; `PSC*` staleness empirically confirmed in a 2025/26 file).
- Closing-Pinnacle Asian-Handicap column resolved empirically to `PCAHH/PCAHA` against a live
  CSV header (the `notes.txt`-convention guess `PAHCH/PAHCA` is absent); ingest fails closed
  if the pinned code is missing (8.8% of rows flagged `quoted_ah_missing`).
- World-Cup hold-out: 384 matches (2002–2022) with 90-minute `FTR` reconstructed from
  regulation-period goals (push rate q = 0.260), sourced from `jfjelstul/worldcup` +
  `martj42/international_results` (cross-reconciled, checksummed).
- Phase-3 execution-cost inputs: open→close move distribution (pooled mean 6.57%, monotone
  increasing across odds buckets) and synthetic-vs-quoted AH margin wedge (+0.80% mean).
- Edge-prior verification register; recomputed draw-rate base rates; survivorship/capacity
  report-card statements.

### Known gaps
- **World-Cup odds** are unavailable from any public source (OddsPortal is JS/ToS-bound;
  Kaggle/GitHub/Zenodo odds sets are football-data.co.uk domestic-only). The WC underdog-DNB
  transfer test is **pending-odds**; Phases 2–4 proceed on the domestic-league estimation
  universe where the statistical power lives. See
  [docs/protocol/note_wc-odds-gap_2026-06-16.md](docs/protocol/note_wc-odds-gap_2026-06-16.md).
- Published-version journal table numbering for two paywalled edge-prior sources is the sole
  manuscript-stage open item (cell values confirmed against the working papers).

## [0.0.1] - 2026-06-16 — Phase 0: environment and reproducibility scaffold

### Added
- Pinned `uv` environment (`requires-python >=3.11,<3.12`, exact `==` direct deps, committed
  `uv.lock`); Clarabel cvxpy solver and native-deps recorded in `docs/decisions/0001`.
- 13-key ReproLog (pydantic model + JSON schema) emitted before every artifact write; handles
  the zero-commit state; the five CLAUDE.md-mandated provenance keys present by name.
- Deterministic, execution-order-independent RNG sub-streams via a `numpy.random.SeedSequence`
  named-stage spawn map (no global `np.random`).
- Pre-registered, frozen `docs/protocol/design.md` (SHA-256); pre-data power record with
  `δ`/`Var_DNB` sourced from the literature, not the panel (Hoenig–Heisey 2001); multiple-
  testing register (`K`, `K_WC`, cross-pillar checklist, conservative raw-`N` deflated Sharpe).
- ADRs: reference-price cutover, 90-minute settlement, transaction-cost/execution-model stub.
- Per-phase entrypoints (`python -m src.run --stage …`) + `Makefile`; `.gitattributes` (LF
  normalization); ruff + pytest (69 tests).

### Notes
- This is a personal/hobby repository committed under the author's real GitHub identity
  (`s-koirala`), modeled on the sibling World-Cup repos. The SKIE-pseudonym identity-hygiene
  gate scaffolded in Phase 0 is therefore disabled for this repo.
