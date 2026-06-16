"""Per-stage RNG sub-stream tests (plan task 9.1; acceptance: order-independence).

Covers: substream determinism from (root_seed, stage_name) alone; order
independence (a stage's draws do not depend on whether other stages ran first in
the same process); distinct stages give distinct streams; the spawn map is the
frozen config/ADR map; unknown stages raise; the public API never touches a
global np.random.
"""

from __future__ import annotations

import numpy as np
import pytest
from src import seeding

ROOT = 20260616


def test_substream_is_deterministic_from_root_and_name():
    a = seeding.substream(ROOT, "bootstrap-ci").standard_normal(50)
    b = seeding.substream(ROOT, "bootstrap-ci").standard_normal(50)
    np.testing.assert_array_equal(a, b)


def test_substream_order_independent():
    """A stage's draws must be identical whether or not OTHER stages ran first.

    This is the load-bearing Phase-0 acceptance: per-stage entrypoints are
    independently runnable, so a stage drawn standalone must byte-match the same
    stage drawn after upstream stages instantiated their own generators in the
    same process.
    """
    standalone = seeding.substream(ROOT, "ruin-mc").integers(0, 1_000_000, size=100)
    # Simulate upstream stages running first and drawing from their own streams.
    for upstream in ("ingest", "price", "stake", "bootstrap-ci"):
        seeding.substream(ROOT, upstream).random(123)
    after_upstream = seeding.substream(ROOT, "ruin-mc").integers(0, 1_000_000, size=100)
    np.testing.assert_array_equal(standalone, after_upstream)


def test_distinct_stages_give_distinct_streams():
    x = seeding.substream(ROOT, "ruin-mc").standard_normal(100)
    y = seeding.substream(ROOT, "vector-kelly").standard_normal(100)
    assert not np.array_equal(x, y)


def test_distinct_root_seeds_give_distinct_streams():
    x = seeding.substream(ROOT, "bootstrap-ci").standard_normal(100)
    y = seeding.substream(ROOT + 1, "bootstrap-ci").standard_normal(100)
    assert not np.array_equal(x, y)


def test_spawn_map_is_frozen_and_contiguous():
    sm = seeding.spawn_map()
    # The four resampling engines named in task 9.1 must be present.
    for stage in ("bootstrap-ci", "ledoit-wolf", "ruin-mc", "vector-kelly"):
        assert stage in sm
    # The six pipeline stages must be present.
    for stage in ("ingest", "validate", "price", "stake", "infer", "report"):
        assert stage in sm
    indices = sorted(sm.values())
    # Contiguous 0..n-1 with no duplicates (renumbering would break old logs).
    assert indices == list(range(len(sm)))


def test_spawn_map_indices_are_stable_known_values():
    sm = seeding.spawn_map()
    assert sm["ingest"] == 0
    assert sm["bootstrap-ci"] == 6
    assert sm["ledoit-wolf"] == 7
    assert sm["ruin-mc"] == 8
    assert sm["vector-kelly"] == 9


def test_unknown_stage_raises():
    with pytest.raises(KeyError, match="unknown stage"):
        seeding.substream(ROOT, "no-such-stage")


def test_negative_root_seed_rejected():
    with pytest.raises(ValueError, match="non-negative"):
        seeding.substream(-1, "ingest")


def test_bool_root_seed_rejected():
    with pytest.raises(TypeError):
        seeding.substream(True, "ingest")


def test_substream_returns_generator_not_global():
    g = seeding.substream(ROOT, "ingest")
    assert isinstance(g, np.random.Generator)
    # The default global RandomState is a different object/type entirely.
    assert g is not np.random.mtrand._rand


def test_child_sequence_matches_substream():
    seq = seeding.child_sequence(ROOT, "infer")
    g_from_seq = np.random.default_rng(seq)
    g_direct = seeding.substream(ROOT, "infer")
    np.testing.assert_array_equal(g_from_seq.standard_normal(20), g_direct.standard_normal(20))
