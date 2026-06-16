---
name: ADR-0005 — Deterministic per-stage RNG sub-stream derivation and the root-seed exemption
description: Single root seed + a frozen named-stage SeedSequence.spawn map gives every stochastic stage an order-independent sub-stream; the root seed is the sole no-magic-number exemption
type: reproducibility
status: accepted
date: 2026-06-16
supersedes:
superseded_by: ""
---

# ADR-0005 — Deterministic per-stage RNG sub-stream derivation and the root-seed exemption

## Context

The project runs several **independent** resampling engines, each under its own per-phase
entrypoint (plan task 9) and each emitting its own ReproLog: the matchday-block bootstrap
ruin Monte-Carlo (Phase 3 task 4, `B = 10⁴`), the stationary bootstrap for CIs (Phase 4
task 4), the Ledoit-Wolf pairwise bootstrap (Phase 4 task 4), and the vector-Kelly
Monte-Carlo (Phase 3 task 3). Because each stage is **independently runnable**, reusing one
*mutable* `numpy.random.Generator` across stages would make a stage's draws depend on whether
upstream stages ran first in the same process — breaking the per-stage byte-reproducibility the
Phase-0 acceptance criteria require (plan §C "Per-stage RNG sub-streams are order-independent";
plan §D.4).

A second, separable decision rides here: the no-magic-number rule (CLAUDE.md; plan §D.3) forbids
unjustified literals, but a reproducible run needs **one** fixed seed. The plan's single explicit
exemption (task 9.1, §D.3) is the **RNG root seed**, and the exemption must be "stated in `config`
and an ADR" — this ADR is that record.

## Decision

### Sub-stream derivation (order-independent)

- A single **root seed** lives in [config/baseline.yaml](../../config/baseline.yaml)
  (`seeding.root_seed`, mirrored by `inference.seed` for ARCH §3.3 compatibility). Its current
  value is `20260616`.
- The root seed constructs one `numpy.random.SeedSequence(root_seed)`
  ([NumPy parallel-RNG docs](https://numpy.org/doc/stable/reference/random/parallel.html)).
- A **fixed `stage → spawn-index` map** assigns each named stage a deterministic spawn index.
  The map is the single source of truth in [src/seeding.py](../../src/seeding.py)
  (`STAGE_SPAWN_MAP`) and is mirrored **byte-for-byte** in
  [config/baseline.yaml](../../config/baseline.yaml) (`seeding.stage_spawn_map`); a unit test
  asserts the two agree (`tests/test_cross_platform.py::test_config_spawn_map_mirrors_seeding_module`).
- `substream(root_seed, stage_name)` reconstructs that stage's child `Generator` from
  `(root_seed, stage_name)` **alone** — it spawns the full fixed-width family in one call and
  selects the named index, so the result is independent of execution order or of how many other
  stages instantiated their generators in the same process.
- **Invariants.** No stage ever draws from the root generator directly; there is no global
  `np.random` (enforced by the ruff `NPY002` rule, [pyproject.toml](../../pyproject.toml)
  `[tool.ruff.lint]`). Each per-stage ReproLog records the **root seed** (`rng_seed`, ReproLog
  key 8). The `stage → spawn-index` map is **not** a ReproLog field; it is pinned by reference
  through the ReproLog's `config_resolved_sha256` (key 9), which is the SHA-256 of the resolved
  [config/baseline.yaml](../../config/baseline.yaml) whose `seeding.stage_spawn_map` block mirrors
  `STAGE_SPAWN_MAP` byte-for-byte (unit-test-enforced). A sub-stream is thus reconstructible from
  `(rng_seed, stage_name)` against the config pinned by `config_resolved_sha256` — not from the
  ReproLog's own fields alone. (Embedding the map directly in the ReproLog was considered but
  rejected: the schema fixes exactly 13 named keys as a Phase-0 acceptance invariant, and the map
  is already version-pinned via `config_resolved_sha256`, so a 14th key would duplicate provenance
  the config SHA already carries.)

The frozen map (index = position in `SeedSequence.spawn(n)` order):

| stage          | index | role                                                              |
|----------------|-------|-------------------------------------------------------------------|
| `ingest`       | 0     | per-phase pipeline stage (plan task 9)                            |
| `validate`     | 1     | per-phase pipeline stage                                          |
| `price`        | 2     | per-phase pipeline stage                                          |
| `stake`        | 3     | per-phase pipeline stage                                          |
| `infer`        | 4     | per-phase pipeline stage                                          |
| `report`       | 5     | per-phase pipeline stage                                          |
| `bootstrap-ci` | 6     | stationary bootstrap for CIs (Phase 4 task 4)                     |
| `ledoit-wolf`  | 7     | Ledoit-Wolf pairwise Sharpe-difference bootstrap (Phase 4 task 4) |
| `ruin-mc`      | 8     | matchday-block bootstrap ruin Monte-Carlo (Phase 3 task 4)        |
| `vector-kelly` | 9     | vector-Kelly Monte-Carlo (Phase 3 task 3)                         |

**The order is FROZEN.** Appending a new stage must take the next free index and never renumber
an existing one, or previously-recorded ReproLog sub-streams would no longer reconstruct.

### Root-seed no-magic-number exemption

The root seed is the **single explicit exemption** to the no-magic-number rule (CLAUDE.md; plan
§D.3, task 9.1). It is arbitrary-but-fixed: chosen once for reproducibility, recorded in
`config/baseline.yaml` and in every ReproLog (`rng_seed`), **never tuned, and never selected to
influence any result**. It is exempt on those stated grounds — recorded-but-not-optimized — not as
an unjustified literal. Every other tunable (thresholds, stake fractions, block lengths, bootstrap
`B`, quantile cut-points) remains data-selected per §D.3.

## Consequences

- **Positive.** Each stochastic stage is byte-reproducible in isolation under its own entrypoint,
  regardless of execution order; the entire run's randomness is reconstructible from the recorded
  `root_seed` plus the spawn map pinned by `config_resolved_sha256` over `config/baseline.yaml`; the
  no-magic-number rule is preserved with exactly one documented exemption.
- **New obligations.** The spawn map is append-only (never renumber); the config mirror must stay
  byte-identical to `src.seeding.STAGE_SPAWN_MAP` (unit-test-enforced); every per-stage ReproLog
  must record the root seed (`rng_seed`) and the resolved-config SHA (`config_resolved_sha256`) that
  pins the spawn map.
- **Negative.** Spawning the full fixed-width family on every `substream` call is marginally
  wasteful versus caching, but it is what makes the index assignment stable irrespective of how
  many stages a given process instantiates — the determinism is worth the negligible cost.

## Alternatives considered

- **One mutable `Generator` threaded through the stages.** Rejected: a stage's draws would depend
  on upstream draw order, breaking per-stage isolation (the load-bearing acceptance criterion).
- **A separate independent seed per stage in config.** Rejected: multiplies the magic-number
  surface (one literal per stage) and decouples the streams from a single reconstructible root;
  the `SeedSequence.spawn` tree gives statistically independent children from one recorded seed.
- **Global `np.random.seed(...)`.** Rejected: a process-global singleton is order-dependent and
  non-isolable; banned project-wide by the ruff `NPY002` rule.

## References

- [plan_phased-workplan_2026-06-16.md](../protocol/plan_phased-workplan_2026-06-16.md) Phase 0
  task 9.1 (deterministic per-stage sub-stream; the root-seed exemption), task 9 (per-phase
  entrypoints), §D.3 (no-magic-number + the seed exemption), §D.4 (reproducibility envelope).
- [research_backtest-architecture-deliverables_2026-06-16.md](../research/research_backtest-architecture-deliverables_2026-06-16.md)
  §3.2 ("Determinism guarantees": named sub-streams, no global `np.random`, fixed summation order).
- [src/seeding.py](../../src/seeding.py) (`STAGE_SPAWN_MAP`, `substream`, `child_sequence`,
  `spawn_map`); [config/baseline.yaml](../../config/baseline.yaml) (`seeding` block, the config
  mirror); [tests/test_seeding.py](../../tests/test_seeding.py) (order-independence + frozen-map
  tests).
- NumPy parallel RNG: [numpy.org/doc/stable/reference/random/parallel.html](https://numpy.org/doc/stable/reference/random/parallel.html)
  (`SeedSequence.spawn`).
