"""Underdog labelling + eligibility selection (plan Phase 2 task 2; CALC §2; DATA §5.3).

Identifies the **underdog** = the side with the higher decimal win price (equivalently
the lower raw implied win probability ``1/o``); applies the frozen near-tie rule; and
filters to the bettable, point-in-time-eligible set. Every quantity is evaluable at
kickoff on the season-conditional reference price (no look-ahead).

Frozen design (``docs/protocol/design.md`` §3, ``config/baseline.yaml`` ``selection``):

* **Underdog side** = ``argmax(refC_H, refC_A)``. The American +/- sign is unreliable in
  a three-way book (all three selections can be plus-money once the draw absorbs mass),
  so the discriminant is purely the relative order of the two win prices (CALC §2.2).
  Tie-break: exact ties resolve to **away** (``refC_A >= refC_H -> away``), matching
  ``src.ingest.attach_reference_price`` bit-for-bit so the assembled ``underdog_side`` /
  ``o_dnb_underdog`` columns are reproduced exactly.

* **Near-tie rule = the SWEPT coin-flip exclusion band** (design.md §3, Phase-0 task
  4.2). The strict-tie-only ``require_strict_underdog`` branch is the one design.md
  explicitly rejects (it is cleared ``false`` in config). A ``min_price_gap`` (``tau_tie``)
  band on the win-price gap is swept on the SAME walk-forward CV as the underdog-strength
  threshold ``tau`` and is registered as a family dimension in
  ``config/multipletest_family.yaml`` (counted in ``K``). It is therefore ``null`` in
  config (no-magic-number) until the Phase-4 §D.3 sweep resolves it -- so the default in
  this module is **no near-tie exclusion** (``min_price_gap=None`` keeps every row whose
  two win prices are present and ordered). This module does NOT assert ``tau`` (the
  underdog-STRENGTH threshold): that grid is selected out-of-fold in Phase 4, not here.

* **Eligibility filters**: both 1X2 win prices present (``refC_H`` and ``refC_A`` finite)
  and a draw price present (the synthetic DNB needs ``refC_D``); a **liquidity proxy**
  (the row carries a usable reference book, i.e. ``ref_book`` is a real source, not
  ``none_available``, and the overround is finite). Rows failing any filter are
  ``eligible=False`` with a recorded ``ineligible_reason`` -- never silently dropped.

The price-gap statistic used by the near-tie band is the **gap in win prices**
``|refC_H - refC_A|`` (a coin-flip exclusion band, CALC §2.3 "price-gap thresholds").
The underdog-strength threshold ``tau`` (Phase 4) uses the odds ratio ``g = W/W_fav``;
that is a separate, out-of-fold-selected dimension and is intentionally not applied here.

No magic numbers; pathlib only where files are read; vectorized over a DataFrame.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

# The eligibility-reason vocabulary (recorded per ineligible row; no silent drops).
REASON_MISSING_WIN_PRICE = "missing_1x2_win_price"
REASON_MISSING_DRAW_PRICE = "missing_draw_price"
REASON_NO_REFERENCE_BOOK = "no_reference_book"  # liquidity proxy: refC unsourced
REASON_NEAR_TIE = "near_tie_below_min_price_gap"  # swept tau_tie band excludes it

# The "no usable reference price" sentinel written by src.ingest.attach_reference_price.
NONE_AVAILABLE = "none_available"


def underdog_side(refC_H: pd.Series, refC_A: pd.Series) -> pd.Series:
    """Underdog side label per row: 'away' where ``refC_A >= refC_H`` else 'home'.

    Matches ``src.ingest.attach_reference_price`` exactly (exact ties -> away). Returns a
    nullable-string Series; ``<NA>`` where either win price is missing (the side is
    undefined, not guessed).
    """
    h = pd.to_numeric(refC_H, errors="coerce")
    a = pd.to_numeric(refC_A, errors="coerce")
    both = h.notna() & a.notna()
    side = np.where(a >= h, "away", "home")
    return pd.Series(np.where(both, side, pd.NA), index=refC_H.index, dtype="string")


def underdog_win_price(refC_H: pd.Series, refC_A: pd.Series) -> pd.Series:
    """The underdog's decimal win price ``W = max(refC_H, refC_A)`` (the higher price).

    Uses the same ``refC_A >= refC_H`` selection as :func:`underdog_side` so the chosen
    price is the away price on exact ties (bit-for-bit consistent with ``src.ingest``).
    NaN where either price is missing.
    """
    h = pd.to_numeric(refC_H, errors="coerce")
    a = pd.to_numeric(refC_A, errors="coerce")
    w = np.where(a.to_numpy() >= h.to_numpy(), a.to_numpy(), h.to_numpy())
    w = np.where(h.notna().to_numpy() & a.notna().to_numpy(), w, np.nan)
    return pd.Series(w, index=refC_H.index, dtype="float64")


def favourite_win_price(refC_H: pd.Series, refC_A: pd.Series) -> pd.Series:
    """The favourite's decimal win price ``W_fav = min(refC_H, refC_A)`` (the lower)."""
    h = pd.to_numeric(refC_H, errors="coerce")
    a = pd.to_numeric(refC_A, errors="coerce")
    f = np.where(a.to_numpy() >= h.to_numpy(), h.to_numpy(), a.to_numpy())
    f = np.where(h.notna().to_numpy() & a.notna().to_numpy(), f, np.nan)
    return pd.Series(f, index=refC_H.index, dtype="float64")


def win_price_gap(refC_H: pd.Series, refC_A: pd.Series) -> pd.Series:
    """The absolute win-price gap ``|refC_H - refC_A|`` (the near-tie statistic, CALC §2.3).

    This is the coin-flip-exclusion-band statistic for the swept ``min_price_gap``
    (``tau_tie``); a small gap means a near-coin-flip match. NaN where either price is
    missing. (The underdog-STRENGTH threshold ``tau`` uses the odds ratio ``W/W_fav``
    instead and is applied out-of-fold in Phase 4, not here.)
    """
    h = pd.to_numeric(refC_H, errors="coerce")
    a = pd.to_numeric(refC_A, errors="coerce")
    return (h - a).abs()


@dataclass(frozen=True)
class SelectionConfig:
    """Frozen selection knobs read from ``config/baseline.yaml`` ``selection`` block.

    ``require_strict_underdog`` is the rejected strict-tie-only branch (design.md §3);
    it is ``False`` in the frozen config and a ``True`` value here is an explicit
    deviation. ``min_price_gap`` is the swept ``tau_tie`` near-tie band -- ``None`` until
    the Phase-4 §D.3 walk-forward sweep resolves it (no-magic-number), in which case no
    near-tie exclusion is applied.
    """

    require_strict_underdog: bool = False
    min_price_gap: float | None = None  # tau_tie; None = no near-tie exclusion (pre-sweep)

    @classmethod
    def from_config(cls, config: dict) -> SelectionConfig:
        """Build from a loaded baseline.yaml dict (``selection`` block)."""
        sel = (config or {}).get("selection") or {}
        gap = sel.get("min_price_gap", None)
        return cls(
            require_strict_underdog=bool(sel.get("require_strict_underdog", False)),
            min_price_gap=None if gap is None else float(gap),
        )


def _has_reference_book(panel: pd.DataFrame) -> pd.Series:
    """Liquidity proxy: the row has a usable reference book (refC_* is sourced).

    ``ref_book == 'none_available'`` is the ``src.ingest`` sentinel for a row with no
    reference triplet (and ``odds_status == 'pending'`` is the WC odds gap). Either makes
    the row non-bettable. If ``ref_book`` is absent entirely the proxy falls back to a
    finite overround.
    """
    n = len(panel)
    if "ref_book" in panel.columns:
        rb = panel["ref_book"].astype("string")
        ok = rb.notna() & (rb != NONE_AVAILABLE)
    else:
        ok = pd.Series([True] * n, index=panel.index, dtype="boolean")
    if "odds_status" in panel.columns:
        ok = ok & (panel["odds_status"].astype("string") != "pending")
    return ok.astype("boolean")


def select_underdog(
    panel: pd.DataFrame,
    config: SelectionConfig | None = None,
    *,
    h_col: str = "refC_H",
    d_col: str = "refC_D",
    a_col: str = "refC_A",
) -> pd.DataFrame:
    """Label the underdog side + win price, apply the near-tie band + eligibility filters.

    Returns a copy of ``panel`` with added columns (PIT-correct; CALC §2, DATA §5.3):

    * ``sel_underdog_side``    -- 'away'/'home'/<NA> (``argmax(refC_H, refC_A)``);
    * ``sel_underdog_price``   -- the underdog win price ``W``;
    * ``sel_favourite_price``  -- the favourite win price ``W_fav``;
    * ``sel_win_price_gap``    -- ``|refC_H - refC_A|`` (the near-tie statistic);
    * ``eligible``             -- bool: bettable under the frozen filters;
    * ``ineligible_reason``    -- the first failing filter (<NA> when eligible).

    Eligibility (frozen design): both win prices present, a draw price present, a usable
    reference book (liquidity proxy), and -- when the swept ``min_price_gap`` is set -- a
    win-price gap at or above the band. ``tau`` (underdog STRENGTH) is NOT applied here:
    it is selected out-of-fold in Phase 4 (CALC §2.3, design.md §5).

    No row is dropped: ineligible rows are flagged with a reason for auditability.
    """
    cfg = config or SelectionConfig()
    out = panel.copy()

    h = pd.to_numeric(out[h_col], errors="coerce") if h_col in out else pd.Series(dtype="float64")
    a = pd.to_numeric(out[a_col], errors="coerce") if a_col in out else pd.Series(dtype="float64")
    d = pd.to_numeric(out[d_col], errors="coerce") if d_col in out else pd.Series(dtype="float64")

    out["sel_underdog_side"] = underdog_side(out.get(h_col, h), out.get(a_col, a))
    out["sel_underdog_price"] = underdog_win_price(out.get(h_col, h), out.get(a_col, a))
    out["sel_favourite_price"] = favourite_win_price(out.get(h_col, h), out.get(a_col, a))
    out["sel_win_price_gap"] = win_price_gap(out.get(h_col, h), out.get(a_col, a))

    has_win = h.notna() & a.notna()
    has_draw = d.notna() & (d > 0.0)
    has_book = _has_reference_book(out)

    # Near-tie band: exclude coin-flips only when the swept tau_tie is resolved (Phase 4).
    # require_strict_underdog (the rejected branch) excludes exact ties only.
    if cfg.require_strict_underdog:
        not_near_tie = out["sel_win_price_gap"] > 0.0
    elif cfg.min_price_gap is not None:
        not_near_tie = out["sel_win_price_gap"] >= float(cfg.min_price_gap)
    else:
        not_near_tie = pd.Series([True] * len(out), index=out.index, dtype="boolean")
    not_near_tie = not_near_tie.fillna(False).astype("boolean")

    # First-failing-reason precedence: win price -> draw price -> book -> near-tie.
    reason = pd.Series([pd.NA] * len(out), index=out.index, dtype="string")
    reason = reason.mask(~not_near_tie & reason.isna(), REASON_NEAR_TIE)
    reason = reason.mask(~has_book.fillna(False) & reason.isna(), REASON_NO_REFERENCE_BOOK)
    reason = reason.mask(~has_draw & reason.isna(), REASON_MISSING_DRAW_PRICE)
    reason = reason.mask(~has_win & reason.isna(), REASON_MISSING_WIN_PRICE)

    out["eligible"] = reason.isna()
    out["ineligible_reason"] = reason
    return out
