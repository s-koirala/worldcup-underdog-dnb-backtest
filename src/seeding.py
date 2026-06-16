"""Deterministic, order-independent per-stage RNG sub-stream derivation.

Phase 0 task 9.1 (plan §C, plan §D.4; ARCH §3.2 "Determinism guarantees").

The project runs several *independent* resampling engines, each under its own
per-stage entrypoint (Phase 0 task 9): the matchday-block bootstrap ruin
Monte-Carlo (Phase 3 task 4), the stationary bootstrap for CIs (Phase 4 task 4),
and the Ledoit-Wolf pairwise bootstrap (Phase 4 task 4). (The ``vector-kelly``
slot is RESERVED for a future scenario-resampled evaluation but is currently
UNUSED: the deployed vector-Kelly path is a deterministic convex program with no
rng draw -- see ADR-0005 and src.vector_kelly.) Reusing one *mutable* ``Generator`` across stages
would make a stage's draws depend on whether upstream stages ran first in the
same process, breaking the per-stage reproducibility the acceptance criteria
require.

Mechanism (NumPy SeedSequence spawning, per the NumPy parallel-RNG docs
https://numpy.org/doc/stable/reference/random/parallel.html):

  * a single ROOT seed (``config/baseline.yaml: inference.seed``) constructs one
    ``numpy.random.SeedSequence(root_seed)``;
  * a FIXED ``stage -> spawn-index`` map (``STAGE_SPAWN_MAP`` below, mirrored in
    config and ADR-0005) assigns each named stage a deterministic spawn index;
  * ``substream(stage_name)`` reconstructs that stage's child ``Generator`` from
    ``(root_seed, stage_name)`` ALONE -- independent of execution order or
    whether any other stage ran in the same process.

No stage ever draws from the root generator directly, and there is no global
``np.random``. The root seed is the single no-magic-number exemption (plan §D.3,
task 9.1): arbitrary-but-fixed, recorded in config and every ReproLog, never
tuned, never selected to influence a result.
"""

from __future__ import annotations

from collections.abc import Mapping

import numpy as np

# Fixed named-stage spawn map. Index = position in SeedSequence.spawn(n) order.
# The order is FROZEN: appending a NEW stage must take the next free index and
# never renumber an existing one, or previously-recorded ReproLog sub-streams
# would no longer reconstruct. This map is the single source of truth and is
# mirrored verbatim in config/baseline.yaml (seeding.stage_spawn_map) and
# docs/decisions/0005-rng-substream-derivation.md.
STAGE_SPAWN_MAP: Mapping[str, int] = {
    # Pipeline stages (per-phase entrypoints, plan task 9).
    "ingest": 0,
    "validate": 1,
    "price": 2,
    "stake": 3,
    "infer": 4,
    "report": 5,
    # Independent resampling engines (plan task 9.1).
    "bootstrap-ci": 6,  # stationary bootstrap for CIs (Phase 4 task 4)
    "ledoit-wolf": 7,  # Ledoit-Wolf pairwise Sharpe-difference bootstrap (Phase 4 task 4)
    "ruin-mc": 8,  # matchday-block bootstrap ruin Monte-Carlo (Phase 3 task 4)
    # RESERVED, currently UNUSED: the deployed vector-Kelly path is a deterministic convex
    # program (no rng draw); slot kept for a future scenario-resampled eval (ADR-0005).
    "vector-kelly": 9,
}


def _validate_root_seed(root_seed: int) -> int:
    """Coerce/validate the root seed to a non-negative int (NumPy entropy contract)."""
    if isinstance(root_seed, bool) or not isinstance(root_seed, int):
        raise TypeError(f"root_seed must be a non-bool int, got {type(root_seed).__name__}")
    if root_seed < 0:
        raise ValueError(f"root_seed must be non-negative, got {root_seed}")
    return root_seed


def root_sequence(root_seed: int) -> np.random.SeedSequence:
    """Return the single root ``SeedSequence`` for this run.

    Every sub-stream descends from this one object so the entire run's
    randomness is reconstructible from the recorded ``root_seed`` alone.
    """
    return np.random.SeedSequence(_validate_root_seed(root_seed))


def child_sequence(root_seed: int, stage_name: str) -> np.random.SeedSequence:
    """Reconstruct the child ``SeedSequence`` for ``stage_name``.

    Order-independent: spawns the full fixed-width family from the root and
    selects the named stage's index, so the result depends only on
    ``(root_seed, stage_name)`` and never on which other stages have run.
    """
    if stage_name not in STAGE_SPAWN_MAP:
        raise KeyError(f"unknown stage {stage_name!r}; known stages: {sorted(STAGE_SPAWN_MAP)}")
    root = root_sequence(root_seed)
    # Spawn the full fixed-width family in one call so indices are stable
    # regardless of how many stages a given process actually instantiates.
    children = root.spawn(len(STAGE_SPAWN_MAP))
    return children[STAGE_SPAWN_MAP[stage_name]]


def substream(root_seed: int, stage_name: str) -> np.random.Generator:
    """Return the deterministic ``Generator`` for ``stage_name``.

    This is the public entry point every stochastic stage calls. Two calls with
    the same ``(root_seed, stage_name)`` yield byte-identical draw sequences,
    independent of execution order (Phase 0 acceptance: order-independence).

    Example
    -------
    >>> g = substream(20260616, "bootstrap-ci")
    >>> isinstance(g, np.random.Generator)
    True
    """
    return np.random.default_rng(child_sequence(root_seed, stage_name))


def spawn_map() -> dict[str, int]:
    """Return a copy of the fixed stage->spawn-index map.

    The map is the single source of truth here, mirrored byte-for-byte in
    ``config/baseline.yaml`` (``seeding.stage_spawn_map``). It is NOT a ReproLog
    field: each per-stage ReproLog records ``rng_seed`` (the root) and pins this
    map by reference via ``config_resolved_sha256`` (the SHA-256 of the resolved
    ``config/baseline.yaml``). A sub-stream is reconstructible from
    ``(rng_seed, stage_name)`` against the config pinned by that SHA -- not from
    the ReproLog's own fields alone (ADR-0005; plan task 9.1). This accessor
    exposes the map for tests and for code that resolves the config.
    """
    return dict(STAGE_SPAWN_MAP)
