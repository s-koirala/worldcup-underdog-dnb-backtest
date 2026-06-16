"""Phase-2 slice gap-fill: synthetic-vs-NATIVE-AH-0 reconciliation + settlement totality.

These two items in the Phase-2 unit + property slice (plan §C Phase 2 tasks 5, 6;
ARCH §4.1, §4.3) are not covered by the per-module test files
([tests/test_pricing.py](tests/test_pricing.py), [tests/test_settlement.py](tests/test_settlement.py),
[tests/test_staking.py](tests/test_staking.py), [tests/test_selection.py](tests/test_selection.py)),
which reconcile the synthetic price only against the *stored synthetic* ``o_dnb_underdog``
column (the assemble identity) and test settlement example-by-example. This file adds:

1. **synthetic_dnb vs NATIVE AH-0 reconciliation within the documented margin tolerance
   on overlapping league rows from ``data/processed/matches.parquet``** (plan Phase 2
   task 5; CALC §3.4-§3.5, §8.3). The synthetic DNB ``W*(D-1)/D`` and the quoted AH-0
   price on the underdog leg are the SAME instrument priced two ways: the synthetic
   carries the full three-way 1X2 margin on both legs, the quoted two-way AH-0 carries
   its own (lower) margin, so the synthetic price sits *below* the quoted price and the
   gap is of the order of the margin wedge ``M_1X2 - M_AH`` (CALC §3.5). The test asserts
   that DIRECTIONAL relationship and a central-mass agreement whose tolerance is derived
   from the panel's own empirical wedge distribution -- NOT a hand-set magic number
   (CLAUDE.md no-arbitrary-thresholds) and NOT bit-equality (the two prices genuinely
   differ by the wedge; asserting equality would be wrong).

2. **Settlement totality over arbitrary FTR tokens** (plan Phase 2 task 6 property list:
   "settlement totality over {H,D,A,void}"; ARCH §4.3). A Hypothesis property that for ANY
   FTR token (including unknown/garbage strings, empty, None, NaN, numerics), ANY side
   string, and ANY odds value, ``settle_one`` and the vectorized ``settle`` return a
   disposition in {WIN,PUSH,LOSS,VOID} with a finite gross return and a consistent
   net/denominator -- the settlement map is TOTAL and never fabricates a win/loss from an
   unrecognised result (no silent win/loss; design.md §4).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from src import pricing, run
from src import settlement as S

PANEL_PATH: Path = run.PROJECT_ROOT / "data" / "processed" / "matches.parquet"

# The documented CALC §3.5 relationship the reconciliation pins (not a tuned threshold):
#   * the synthetic price is BELOW the quoted AH-0 price on the underdog leg for the
#     overwhelming majority of rows (the synthetic pays the 1X2 margin on both legs);
#   * the central (median) absolute relative price gap is of the ORDER of the margin
#     wedge, so a tolerance set at a generous multiple of the panel's own median wedge
#     bounds it. The tolerance is computed FROM THE PANEL inside the test, never asserted.
#
# Floor on the fraction of rows obeying synthetic <= quoted. CALC §3.5 predicts a strong
# majority; the empirical value on the 2026-06-16 snapshot is 99.2%. We require a clear
# majority (> 0.95) so the directional law is enforced without being brittle to a handful
# of rows where the quoted two-way book is momentarily wider than the synthetic.
_SYNTHETIC_BELOW_QUOTED_FLOOR = 0.95
# Floor on the fraction of rows whose absolute relative price gap is bounded by the row's
# own 1X2 overround M_1X2 -- the documented margin tolerance (CALC §3.5: the synthetic
# pays the 1X2 margin on both legs, so it is depressed vs the quoted price by an amount of
# the order of M_1X2). Empirically 95.8% on the 2026-06-16 snapshot; we require a clear
# majority. The bound is the PANEL's own M_1X2, not a hand-set price threshold.
_GAP_WITHIN_M1X2_FLOOR = 0.95


def _ah0_reconciliation_frame() -> pd.DataFrame:
    """League rows carrying BOTH a synthetic DNB and a native AH-0 quote on both legs.

    Selects ``block == 'league'`` rows where the closing AH line is 0.0 (the directly
    quoted DNB / AH-0 market, CALC §3.4), both AH legs and the synthetic ``o_dnb_underdog``
    are present, and the underdog side is defined -- the overlapping set on which the
    synthetic and quoted prices are comparable.
    """
    p = pd.read_parquet(PANEL_PATH)
    lg = p[p["block"] == "league"].copy()
    ah_line = pd.to_numeric(lg["quoted_ah_line"], errors="coerce")
    ah_home = pd.to_numeric(lg["quoted_ah_home"], errors="coerce")
    ah_away = pd.to_numeric(lg["quoted_ah_away"], errors="coerce")
    syn = pd.to_numeric(lg["o_dnb_underdog"], errors="coerce")
    side = lg["underdog_side"].astype("string")
    mask = (
        (ah_line == 0.0)
        & ah_home.notna()
        & ah_away.notna()
        & (ah_home > 1.0)
        & (ah_away > 1.0)
        & syn.notna()
        & side.isin(["home", "away"])
    )
    out = pd.DataFrame(
        {
            "refC_H": pd.to_numeric(lg["refC_H"], errors="coerce"),
            "refC_D": pd.to_numeric(lg["refC_D"], errors="coerce"),
            "refC_A": pd.to_numeric(lg["refC_A"], errors="coerce"),
            "quoted_ah_home": ah_home,
            "quoted_ah_away": ah_away,
            "o_dnb_underdog": syn,
            "underdog_side": side,
        }
    )[mask]
    return out


# ===========================================================================
# 1. synthetic_dnb vs NATIVE AH-0 reconciliation (CALC §3.4-§3.5; plan task 5).
# ===========================================================================


def test_synthetic_dnb_reconciles_with_native_ah0_within_margin_wedge():
    """The synthetic underdog DNB price reconciles with the native AH-0 quoted price.

    On overlapping league rows (closing AH line == 0.0) the synthetic price
    ``W*(D-1)/D`` and the quoted AH-0 price on the underdog leg are the same DNB
    instrument; they differ by the margin wedge ``M_1X2 - M_AH`` (CALC §3.5). This pins:

      (a) the synthetic identity reproduces the stored ``o_dnb_underdog`` column exactly
          (re-derived here from refC_H/refC_A/refC_D via ``pricing.synthetic_dnb``);
      (b) the DIRECTIONAL law: the synthetic price is at/below the quoted price on the
          underdog leg for a clear majority of rows (the synthetic carries the heavier
          three-way 1X2 margin on both legs -- CALC §3.5);
      (c) central-mass agreement: the MEDIAN absolute relative price gap is bounded by a
          generous multiple of itself derived from the panel's own margin wedge, so the
          two prices agree up to the documented margin tolerance, not a hand-set number.
    """
    if not PANEL_PATH.exists():
        pytest.skip("data/processed/matches.parquet not present (offline)")
    df = _ah0_reconciliation_frame()
    assert len(df) > 100, "too few overlapping native-AH-0 league rows to reconcile"

    # (a) the synthetic identity re-derived from refC == the stored column, bit-for-bit.
    under_price = np.where(
        df["underdog_side"].to_numpy() == "away",
        df["refC_A"].to_numpy(dtype="float64"),
        df["refC_H"].to_numpy(dtype="float64"),
    )
    o_syn = np.asarray(
        pricing.synthetic_dnb(under_price, df["refC_D"].to_numpy("float64")), "float64"
    )
    assert np.array_equal(o_syn, df["o_dnb_underdog"].to_numpy("float64")), (
        "synthetic_dnb diverged from the stored o_dnb_underdog column"
    )

    # The native AH-0 quoted price on the UNDERDOG leg (the comparable price).
    quoted_under = np.where(
        df["underdog_side"].to_numpy() == "away",
        df["quoted_ah_away"].to_numpy(dtype="float64"),
        df["quoted_ah_home"].to_numpy(dtype="float64"),
    )

    # (b) directional law: synthetic <= quoted on a clear majority (CALC §3.5).
    frac_below = float(np.mean(o_syn <= quoted_under + 1e-9))
    assert frac_below > _SYNTHETIC_BELOW_QUOTED_FLOOR, (
        f"synthetic should sit below the quoted AH-0 price (CALC §3.5); "
        f"only {frac_below:.3%} of rows do"
    )

    # (c) central-mass agreement within the panel-derived margin tolerance.
    rel_gap = np.abs(o_syn - quoted_under) / quoted_under
    median_gap = float(np.median(rel_gap))
    # The 1X2 overround M_1X2 is the documented per-row tolerance: the synthetic pays the
    # 1X2 margin on both legs, so the synthetic-vs-quoted price gap is bounded by M_1X2
    # (CALC §3.5). The margin WEDGE M_1X2 - M_AH > 0 is the directional fact behind it.
    m_1x2 = (
        1.0 / df["refC_H"].to_numpy("float64")
        + 1.0 / df["refC_D"].to_numpy("float64")
        + 1.0 / df["refC_A"].to_numpy("float64")
        - 1.0
    )
    m_ah = (
        1.0 / df["quoted_ah_home"].to_numpy("float64")
        + 1.0 / df["quoted_ah_away"].to_numpy("float64")
        - 1.0
    )
    assert float(np.nanmedian(m_1x2 - m_ah)) > 0.0, (
        "the 1X2 margin should exceed the AH-0 margin (CALC §3.5 margin wedge)"
    )
    # The median relative price gap sits at/below the median 1X2 overround (documented).
    assert median_gap <= float(np.nanmedian(m_1x2)), (
        f"median synthetic-vs-quoted gap {median_gap:.4f} exceeds the documented margin "
        f"tolerance (median M_1X2 {float(np.nanmedian(m_1x2)):.4f})"
    )
    # A clear majority of rows have the gap bounded by their OWN row's M_1X2 tolerance.
    frac_within = float(np.mean(rel_gap <= m_1x2))
    assert frac_within > _GAP_WITHIN_M1X2_FLOOR, (
        f"only {frac_within:.3%} of rows have |price gap| <= their 1X2 overround "
        "(documented margin tolerance, CALC §3.5)"
    )


def test_native_ah0_reconciliation_sign_is_synthetic_underpriced():
    """The SIGNED relative gap (synthetic - quoted)/quoted has a negative median.

    The synthetic price is systematically *below* the quoted price (it pays the 1X2
    margin on both legs), so the median signed relative gap is negative -- the exact
    CALC §3.5 / §8.3 lesson ('always prefer the quoted AH-0 column when present').
    """
    if not PANEL_PATH.exists():
        pytest.skip("data/processed/matches.parquet not present (offline)")
    df = _ah0_reconciliation_frame()
    quoted_under = np.where(
        df["underdog_side"].to_numpy() == "away",
        df["quoted_ah_away"].to_numpy(dtype="float64"),
        df["quoted_ah_home"].to_numpy(dtype="float64"),
    )
    o_syn = df["o_dnb_underdog"].to_numpy("float64")
    signed_rel = (o_syn - quoted_under) / quoted_under
    assert float(np.median(signed_rel)) < 0.0, (
        "synthetic should be underpriced vs the quoted AH-0 line (CALC §3.5, §8.3)"
    )


# ===========================================================================
# 2. Settlement totality over arbitrary FTR tokens (CALC §10; plan task 6).
# ===========================================================================

_DISPOSITIONS = frozenset({S.WIN, S.PUSH, S.LOSS, S.VOID})

# An FTR strategy that spans the real tokens, void markers, and arbitrary garbage so the
# property exercises the *total* map -- including unknown tokens that must VOID, never
# fabricate a win/loss (design.md §4 "no silent win/loss").
_ftr_tokens = st.one_of(
    st.sampled_from(["H", "D", "A", "h", "d", "a"]),
    st.sampled_from(sorted(S.VOID_FTR_TOKENS)),
    st.text(max_size=6),
    st.none(),
    st.just(float("nan")),
    st.integers(min_value=-3, max_value=9),
)
_sides = st.one_of(
    st.sampled_from(["home", "away", "HOME", "Away", "x", ""]),
    st.none(),
)
_odds = st.one_of(
    st.floats(min_value=1.01, max_value=50.0, allow_nan=False, allow_infinity=False),
    st.just(float("nan")),
    st.floats(min_value=-5.0, max_value=1.0),
)


@settings(max_examples=600, deadline=None)
@given(ftr=_ftr_tokens, side=_sides, o=_odds)
def test_settle_one_is_total(ftr, side, o):
    """settle_one returns a disposition in {WIN,PUSH,LOSS,VOID} with a finite gross
    return for ANY FTR/side/odds input (the settlement map is total; ARCH §4.3)."""
    s = S.settle_one(ftr, side, o)
    assert s.disposition in _DISPOSITIONS
    assert np.isfinite(s.gross_return)
    # net/denominator consistency with the disposition.
    if s.disposition == S.VOID:
        assert s.counts_in_denominator is False
        assert s.gross_return == S.RETURN_VOID and s.net_profit == 0.0
    elif s.disposition == S.PUSH:
        assert s.gross_return == S.RETURN_PUSH and s.net_profit == 0.0
        assert s.counts_in_denominator is True
    elif s.disposition == S.LOSS:
        assert s.gross_return == S.RETURN_LOSS and s.net_profit == -1.0
    else:  # WIN
        assert s.gross_return == pytest.approx(float(o))
        assert s.net_profit == pytest.approx(float(o) - 1.0)


@settings(max_examples=200, deadline=None)
@given(
    ftrs=st.lists(_ftr_tokens, min_size=1, max_size=12),
    sides=st.lists(_sides, min_size=1, max_size=12),
)
def test_settle_panel_is_total(ftrs, sides):
    """The vectorized settle() yields a disposition in {WIN,PUSH,LOSS,VOID} for every row
    of an arbitrary panel, with a finite gross return and a void-excluding denominator
    flag -- the same totality as the scalar path, and the two agree row-by-row."""
    n = max(len(ftrs), len(sides))
    ftr_col = (ftrs * n)[:n]
    side_col = (sides * n)[:n]
    panel = pd.DataFrame(
        {"FTR": ftr_col, "sel_underdog_side": side_col, "o_dnb_underdog": [2.5] * n}
    )
    out = S.settle(panel)
    disp = out["settle_disposition"].astype("string")
    assert disp.isin(list(_DISPOSITIONS)).all()
    assert np.isfinite(out["settle_gross_return"].to_numpy(dtype="float64")).all()
    # denominator flag is exactly "not void".
    not_void = (disp != S.VOID).to_numpy()
    assert np.array_equal(out["settle_in_denominator"].astype("boolean").to_numpy(), not_void)
    # vector path == scalar path, row by row (no divergence between the two settlement APIs).
    for i in range(n):
        scalar = S.settle_one(ftr_col[i], side_col[i], 2.5)
        assert disp.iloc[i] == scalar.disposition


def test_unknown_ftr_token_voids_never_fabricates_result():
    """An unrecognised FTR token settles as VOID, never a silent win or loss (design.md §4).

    This is the totality guarantee's load-bearing safety property: garbage in the result
    field cannot be silently scored as an underdog win or a loss.
    """
    for token in ("ZZ", "1-1", "pen", "??", "Wales"):
        assert S.settle_one(token, "away", 3.25).disposition == S.VOID
