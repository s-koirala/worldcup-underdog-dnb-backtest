"""Unit + property tests for the pricing / de-vig core (plan Phase 2 tasks 1, 5, 6, 7).

Covers (CALC §3, §4; ARCH §4.1 unit + §4.3 property; §5.1 estimator-verification gate):
  * ``synthetic_dnb`` matches the CALC §8.1 worked 3.25 example and the no-arbitrage
    settlement ledger (CALC §3.1);
  * ``synthetic_dnb`` RECONCILES bit-for-bit with the ``src.ingest`` arithmetic and the
    stored ``data/processed/matches.parquet`` ``o_dnb_underdog`` column (the load-bearing
    reconciliation: the panel content SHA is unchanged after ingest imports it);
  * the de-vig dispatcher (basic / shin / power) returns fair probs in (0,1) summing to 1
    with margin ≥ 0, and Shin endogenously shades the longshot down (FLB);
  * the ESTIMATOR-VERIFICATION GATE (task 7): the Shin z-root reproduces the exact
    two-way Jullien-Salanié closed form (analytic ground truth) and the documented
    CALC §8.1/§8.2 worked z + probability map;
  * Shin is run on the THREE-WAY 1X2 book; the under-round draw-dropped residual is
    REJECTED (invalid z < 0 -- CALC §4.2 applicability note);
  * the conditional q_W = p_W/(1 - p_D), the margin wedge M_1X2 - M_AH, and the
    prefer-quoted-then-synthetic price selector;
  * Hypothesis property tests: de-vig probs in (0,1) sum to 1; o_DNB monotone in W,
    decreasing in p_D, and o_DNB ≤ raw win price.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st
from src import pricing

# ===========================================================================
# synthetic_dnb -- worked example + the no-arbitrage ledger (CALC §3.1, §8.1).
# ===========================================================================


def test_synthetic_dnb_worked_example_3_25():
    """CALC §8.1: H=1.80, D=3.60, A=4.50 (away longshot) -> o_DNB = 4.50*(3.60-1)/3.60
    = 3.25 exactly."""
    o = pricing.synthetic_dnb(4.50, 3.60)
    assert o == pytest.approx(3.25, abs=1e-12)
    # equivalent W*(1 - r_D) form (NOT the impl order, but algebraically equal here)
    assert o == pytest.approx(4.50 * (1.0 - 1.0 / 3.60), rel=1e-12)


def test_synthetic_dnb_no_arbitrage_ledger():
    """The draw leg is a perfect hedge: staking 1/D at D returns exactly 1 on a draw,
    so the combined position returns the unit stake (a push). The win leg pays
    s_W*W = (D-1)/D * W = o_DNB (CALC §3.1 ledger)."""
    w, d = 4.50, 3.60
    s_d = 1.0 / d  # draw hedge
    s_w = 1.0 - s_d  # win stake
    assert s_d * d == pytest.approx(1.0, abs=1e-12)  # draw -> push (unit stake back)
    assert s_w * w == pytest.approx(pricing.synthetic_dnb(w, d), abs=1e-12)  # win -> o_DNB


def test_synthetic_dnb_le_raw_win_price():
    """o_DNB = W*(D-1)/D < W for any finite D > 1 (the push hedge costs return)."""
    for w, d in [(4.50, 3.60), (2.55, 3.35), (10.0, 2.10), (1.50, 8.0)]:
        assert pricing.synthetic_dnb(w, d) < w


def test_synthetic_dnb_array_nan_propagation():
    """The array path yields NaN where D is null/non-positive (the ingest divide-guard);
    a valid row computes W*(D-1)/D."""
    w = np.array([4.50, 2.55, 3.0, 3.0])
    d = np.array([3.60, np.nan, 0.0, -1.0])
    out = np.asarray(pricing.synthetic_dnb(w, d), dtype="float64")
    assert out[0] == pytest.approx(3.25, abs=1e-12)
    assert np.isnan(out[1]) and np.isnan(out[2]) and np.isnan(out[3])


def test_synthetic_dnb_rejects_bad_draw_price():
    """Scalar synthetic_dnb requires D > 0 via the array NaN convention; the explicit
    dnb_price selector rejects a non-positive quoted price."""
    assert math.isnan(float(pricing.synthetic_dnb(4.50, 0.0)))
    with pytest.raises(ValueError):
        pricing.dnb_price(4.50, 3.60, quoted_ah_price=0.5)


# ===========================================================================
# RECONCILIATION: synthetic_dnb == src.ingest arithmetic == stored panel column.
# (The load-bearing reconciliation the slice brief mandates.)
# ===========================================================================


def test_synthetic_dnb_reconciles_with_ingest_arithmetic():
    """synthetic_dnb's array path is bit-for-bit identical to the former inline ingest
    expression ``under * (D-1.0)/D`` under the same divide-guard -- so importing it into
    src.ingest leaves o_dnb_underdog (and the panel content SHA) unchanged."""
    rng = np.random.default_rng(0)
    refc_h = rng.uniform(1.05, 12.0, size=5000)
    refc_a = rng.uniform(1.05, 12.0, size=5000)
    refc_d = rng.uniform(1.05, 20.0, size=5000)
    under = np.where(refc_a >= refc_h, refc_a, refc_h)  # ingest tie-break (away wins ties)
    with np.errstate(divide="ignore", invalid="ignore"):
        ingest_arith = np.where(
            np.isfinite(refc_d) & (refc_d > 0), under * (refc_d - 1.0) / refc_d, np.nan
        )
    syn = np.asarray(pricing.synthetic_dnb(under, refc_d), dtype="float64")
    # bit-identical (np.array_equal treats NaN positions; here there are none)
    assert np.array_equal(syn, ingest_arith)


def test_synthetic_dnb_reconciles_with_stored_panel():
    """synthetic_dnb reproduces the stored matches.parquet o_dnb_underdog column EXACTLY
    on every settleable league row (0 mismatches). This pins the assemble.py / ingest.py
    reconciliation: the panel content SHA is unchanged after ingest imports synthetic_dnb.

    Skips gracefully if the committed panel is absent (offline CI without data)."""
    from pathlib import Path

    panel_path = Path(__file__).resolve().parent.parent / "data" / "processed" / "matches.parquet"
    if not panel_path.exists():
        pytest.skip("data/processed/matches.parquet not present (offline)")
    p = pd.read_parquet(panel_path)
    lg = p[(p["block"] == "league") & p["o_dnb_underdog"].notna()].copy()
    refc_h = pd.to_numeric(lg["refC_H"], errors="coerce").to_numpy(dtype="float64")
    refc_a = pd.to_numeric(lg["refC_A"], errors="coerce").to_numpy(dtype="float64")
    refc_d = pd.to_numeric(lg["refC_D"], errors="coerce").to_numpy(dtype="float64")
    under = np.where(refc_a >= refc_h, refc_a, refc_h)
    syn = np.asarray(pricing.synthetic_dnb(under, refc_d), dtype="float64")
    stored = pd.to_numeric(lg["o_dnb_underdog"], errors="coerce").to_numpy(dtype="float64")
    assert np.array_equal(syn, stored), "synthetic_dnb diverged from the stored panel column"


# ===========================================================================
# implied_probs + overround (CALC §1).
# ===========================================================================


def test_implied_probs_and_overround():
    """Raw reciprocal prices and overround M = Π - 1 (CALC §8.1: M = 5.56%)."""
    ip = pricing.implied_probs(1.80, 3.60, 4.50)
    assert ip.r_H == pytest.approx(1 / 1.80, abs=1e-12)
    assert ip.booksum == pytest.approx(1 / 1.80 + 1 / 3.60 + 1 / 4.50, abs=1e-12)
    assert ip.overround == pytest.approx(0.0555555556, abs=1e-9)


def test_implied_probs_rejects_non_price():
    with pytest.raises(ValueError):
        pricing.implied_probs(1.0, 3.60, 4.50)  # o = 1.0 is not a profitable price


# ===========================================================================
# De-vig dispatcher: basic / shin / power (CALC §4).
# ===========================================================================


@pytest.mark.parametrize("method", ["basic", "shin", "power"])
def test_devig_returns_valid_simplex(method):
    """Every method returns fair probs in (0,1) summing to 1 (ARCH §2.2 contract)."""
    p_h, p_d, p_a = pricing.devig(1.80, 3.60, 4.50, method=method)
    for p in (p_h, p_d, p_a):
        assert 0.0 < p < 1.0
    assert p_h + p_d + p_a == pytest.approx(1.0, abs=1e-9)


def test_devig_basic_matches_calc_8_2():
    """CALC §8.2 basic de-vig: p_W(away)=0.2105, p_D=0.2632, p_fav(home)=0.5263."""
    p_h, p_d, p_a = pricing.devig(1.80, 3.60, 4.50, method="basic")
    assert p_a == pytest.approx(0.2105, abs=5e-4)  # away = underdog
    assert p_d == pytest.approx(0.2632, abs=5e-4)
    assert p_h == pytest.approx(0.5263, abs=5e-4)  # home = favourite


def test_shin_shades_longshot_down_vs_basic():
    """Shin endogenously produces the favourite-longshot bias: the longshot (away, the
    higher price) is shaded DOWN and the favourite UP relative to basic (CALC §4.2)."""
    _, _, a_basic = pricing.devig(1.80, 3.60, 4.50, method="basic")
    h_basic, _, _ = pricing.devig(1.80, 3.60, 4.50, method="basic")
    h_shin, _, a_shin = pricing.devig(1.80, 3.60, 4.50, method="shin")
    assert a_shin < a_basic  # longshot shaded down
    assert h_shin > h_basic  # favourite shaded up


def test_devig_unknown_method_raises():
    with pytest.raises(ValueError):
        pricing.devig(1.80, 3.60, 4.50, method="odds_ratio")  # type: ignore[arg-type]


# ===========================================================================
# ESTIMATOR-VERIFICATION GATE (task 7, ARCH §5.1): the Shin z-root.
# ===========================================================================


def test_shin_z_two_way_closed_form_reproduces_numeric_root():
    """The numeric Shin z (shin_z) on a two-outcome over-round book reproduces the EXACT
    Jullien-Salanié 1994 / Štrumbelj 2016 analytic closed form (shin_z_two_way) -- the
    estimator-verification ground truth (ARCH §5.1 'Shin de-vig z-solution')."""
    # Strongly-skewed two-way book (favourite 1.25, longshot 4.00).
    z_numeric = pricing.shin_z((1.25, 4.00))
    z_closed = pricing.shin_z_two_way(1.25, 4.00)
    # Independently reproduced ground-truth value (SciPy brentq + the closed form):
    assert z_closed == pytest.approx(0.05103259941969624, abs=1e-12)
    assert z_numeric == pytest.approx(z_closed, abs=1e-9)


def test_shin_z_two_way_matches_calc_8_3_quoted_ah_book():
    """CALC §8.3 quoted AH-0 book (away 3.40, home 1.40): the two-way Shin z closed form
    and the numeric root agree, and Shin probs sum to 1."""
    z_closed = pricing.shin_z_two_way(3.40, 1.40)
    z_numeric = pricing.shin_z((3.40, 1.40))
    assert z_closed == pytest.approx(z_numeric, abs=1e-9)
    r = np.array([1 / 3.40, 1 / 1.40])
    p = pricing.shin_probs_from_raw(r, z_closed)
    assert p.sum() == pytest.approx(1.0, abs=1e-12)


def test_shin_z_three_way_worked_value_and_map():
    """ESTIMATOR-VERIFICATION (three-way 1X2 book, CALC §8.1: H=1.80,D=3.60,A=4.50).

    The reproduced Shin z-root and implied-probability map (independently computed via
    SciPy brentq on the Jullien-Salanié fixed point) -- the documented worked value the
    gate asserts before the de-vig is wired into the pipeline."""
    z = pricing.shin_z((1.80, 3.60, 4.50))
    # Reproduced z (Shin 1992/1993; Jullien-Salanié 1994; verified to 1e-12):
    assert z == pytest.approx(0.02792287176121207, abs=1e-9)
    p_h, p_d, p_a = pricing.devig(1.80, 3.60, 4.50, method="shin")
    # The Shin implied-probability map (longshot shaded vs basic 0.2105):
    assert p_h == pytest.approx(0.53427497, abs=1e-6)
    assert p_d == pytest.approx(0.26023809, abs=1e-6)
    assert p_a == pytest.approx(0.20548693, abs=1e-6)
    assert p_h + p_d + p_a == pytest.approx(1.0, abs=1e-12)


# ===========================================================================
# Shin-on-the-right-book (CALC §4.2 applicability note): the load-bearing constraint.
# ===========================================================================


def test_shin_rejects_under_round_draw_dropped_residual():
    """The draw-dropped 1X2 residual is UNDER-round (r_W + r_fav < 1); feeding it to the
    two-way Shin form must FAIL (invalid z < 0), not silently return a degenerate value
    (CALC §4.2, §8.2 caveat). For the synthetic DNB the de-vig runs on the THREE-WAY
    book and forms q_W."""
    # CALC §8.2: dropping the draw from H=1.80,A=4.50 -> r_A + r_H = 0.7778 < 1.
    assert (1 / 1.80 + 1 / 4.50) < 1.0  # confirm under-round
    with pytest.raises(ValueError, match="over-round"):
        pricing.shin_z((1.80, 4.50))  # under-round residual -> reject
    with pytest.raises(ValueError, match="over-round"):
        pricing.shin_z_two_way(1.80, 4.50)


def test_shin_q_w_formed_from_three_way_book():
    """The DNB conditional q_W is formed from the THREE-WAY Shin fair probs (the correct
    route), NOT from a draw-dropped residual. q_W = p_W/(1 - p_D) in (0,1)."""
    p_h, p_d, p_a = pricing.devig(1.80, 3.60, 4.50, method="shin")  # away = underdog
    q_w = pricing.conditional_win_prob(p_a, p_d)
    assert q_w == pytest.approx(p_a / (1 - p_d), abs=1e-12)
    assert 0.0 < q_w < 1.0


# ===========================================================================
# conditional_win_prob + margin wedge + prefer-quoted price (CALC §3.4, §3.5).
# ===========================================================================


def test_conditional_win_prob_rejects_certain_draw():
    with pytest.raises(ValueError):
        pricing.conditional_win_prob(0.3, 1.0)  # p_D = 1 -> no no-draw mass


def test_margin_wedge_quoted_lower_than_synthetic():
    """CALC §8.3: the quoted two-way AH-0 book carries a LOWER margin than the 1X2 book
    (M_AH < M_1X2), so the wedge M_1X2 - M_AH > 0."""
    mw = pricing.margin_wedge(1.80, 3.60, 4.50, quoted_ah_win=3.40, quoted_ah_fav=1.40)
    assert mw.m_1x2 == pytest.approx(0.0555555556, abs=1e-9)
    assert mw.m_ah == pytest.approx(1 / 3.40 + 1 / 1.40 - 1.0, abs=1e-12)
    assert mw.wedge > 0.0  # synthetic carries the heavier margin (CALC §3.5)


def test_margin_wedge_no_quote_returns_none():
    mw = pricing.margin_wedge(1.80, 3.60, 4.50)
    assert mw.m_ah is None and mw.wedge is None
    assert mw.m_1x2 == pytest.approx(0.0555555556, abs=1e-9)


def test_dnb_price_prefers_quoted_then_synthetic():
    """The pipeline prefers the quoted AH-0 price when present; synthetic is the fallback
    (CALC §3.5; design.md §3)."""
    price, source = pricing.dnb_price(4.50, 3.60, quoted_ah_price=3.40)
    assert (price, source) == (3.40, "quoted_ah")
    price, source = pricing.dnb_price(4.50, 3.60)
    assert source == "synthetic"
    assert price == pytest.approx(3.25, abs=1e-12)


# ===========================================================================
# Property tests (Hypothesis, ARCH §4.3).
# ===========================================================================

# A valid over-round 1X2 book: three decimal odds > 1 whose reciprocals sum to > 1.
_odds = st.floats(min_value=1.02, max_value=50.0, allow_nan=False, allow_infinity=False)


@st.composite
def _over_round_book(draw):
    """Sample a genuinely over-round 1X2 book (Π = Σ 1/o_i > 1, the real-world case)."""
    h, d, a = draw(_odds), draw(_odds), draw(_odds)
    assume(1 / h + 1 / d + 1 / a > 1.0 + 1e-6)
    return h, d, a


@settings(max_examples=300, deadline=None)
@given(book=_over_round_book(), method=st.sampled_from(["basic", "shin", "power"]))
def test_property_devig_simplex(book, method):
    """De-vig probs are strictly in (0,1) and sum to 1 for any over-round book; the
    overround is ≥ 0 (CALC §4 range-safety / ARCH §4.3)."""
    h, d, a = book
    assert pricing.implied_probs(h, d, a).overround >= 0.0
    p_h, p_d, p_a = pricing.devig(h, d, a, method=method)
    for p in (p_h, p_d, p_a):
        assert 0.0 < p < 1.0
    assert p_h + p_d + p_a == pytest.approx(1.0, abs=1e-7)


@settings(max_examples=300, deadline=None)
@given(
    w=st.floats(min_value=1.02, max_value=50.0, allow_nan=False),
    d=st.floats(min_value=1.02, max_value=50.0, allow_nan=False),
)
def test_property_o_dnb_le_win_price_and_positive(w, d):
    """o_DNB is positive and never exceeds the raw win price W (the push hedge costs
    return); o_DNB = W*(D-1)/D ≤ W with equality only as D→∞ (ARCH §4.3)."""
    o = float(pricing.synthetic_dnb(w, d))
    assert 0.0 < o <= w


@settings(max_examples=300, deadline=None)
@given(
    w=st.floats(min_value=1.02, max_value=50.0, allow_nan=False),
    d1=st.floats(min_value=1.05, max_value=49.0, allow_nan=False),
    bump=st.floats(min_value=0.01, max_value=5.0, allow_nan=False),
)
def test_property_o_dnb_monotone(w, d1, bump):
    """o_DNB is increasing in the win price W and increasing in the draw price D
    (equivalently DECREASING in the draw probability r_D = 1/D), since o_DNB =
    W*(1 - 1/D) (ARCH §4.3 monotonicity)."""
    d2 = d1 + bump  # higher D == lower draw probability
    o_d1 = float(pricing.synthetic_dnb(w, d1))
    o_d2 = float(pricing.synthetic_dnb(w, d2))
    assert o_d2 >= o_d1  # increasing in D (decreasing in draw prob)
    # increasing in win price at fixed D
    assert float(pricing.synthetic_dnb(w + 1.0, d1)) > o_d1
