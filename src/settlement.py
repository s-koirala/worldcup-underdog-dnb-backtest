"""Three-way Draw-No-Bet settlement on the 90-minute result (plan Phase 2 task 3; CALC §10).

Settles an underdog Draw-No-Bet from the **90-minute** Full-Time Result (``FTR``),
returning the per-unit-stake gross return and the win/push/loss/void disposition. This is
the load-bearing settlement contract (ARCH §4.1) for both the league universe and the
World-Cup hold-out.

Frozen settlement map (``docs/protocol/design.md`` §4; CALC §10; ADR-0003):

    underdog wins in 90'   -> o_DNB        (win;  net profit o_DNB - 1)
    90-minute DRAW         -> 1.0          (push; stake refunded; net 0)
    favourite wins in 90'  -> 0.0          (loss; net -1)
    void / abandoned       -> 1.0          (refund; EXCLUDED from win-ratio denominator)

The **90-minute result governs**, including knockout matches decided by extra time or a
penalty shootout: a match level at 90' is a DNB **push** even though the tournament
records a winner after ET/penalties. Extra-time and penalty goals NEVER change settlement
(EDGE §4.6). The 90-minute ``FTR`` is supplied by the panel (``src.assemble`` carries the
reconstructed ``ftr_90`` as ``FTR`` for WC rows and the regulation ``FTR`` for league
rows -- domestic fixtures have no ET).

This module reads ONLY the 90-minute ``FTR`` and the underdog side; it deliberately does
NOT read ``decided_in_et`` / ``penalty_shootout`` for the win/push/loss decision (those
are progression metadata, not settlement inputs), which is exactly why an ET/penalty goal
cannot change the result. It is **idempotent**: settling an already-settled frame
reproduces identical dispositions and returns (no state, pure function of the inputs).

No magic numbers; pure numeric/vectorized over a DataFrame; scalar helper for unit tests.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

# Disposition vocabulary (the win-ratio denominator EXCLUDES 'void').
WIN = "win"
PUSH = "push"
LOSS = "loss"
VOID = "void"

# Per-unit-stake GROSS return by disposition (decimal-odds convention: a winning unit
# returns o_DNB incl. stake; a push refunds the unit; a loss returns 0). The win value is
# row-specific (o_DNB) and filled at settlement; push/loss/void are constants.
RETURN_PUSH = 1.0  # stake refunded
RETURN_LOSS = 0.0  # full loss
RETURN_VOID = 1.0  # refund (excluded from win ratio)

# The set of FTR tokens that mean the bet is settled on a real 90-minute result.
_FTR_HOME = "H"
_FTR_DRAW = "D"
_FTR_AWAY = "A"
# Void / abandoned 90-minute results (no valid regulation outcome). Recorded, not guessed.
VOID_FTR_TOKENS: frozenset[str] = frozenset({"V", "VOID", "ABD", "ABANDONED", "AWD", "NR"})


@dataclass(frozen=True)
class Settlement:
    """Scalar settlement outcome of one underdog DNB (for unit tests / single matches)."""

    disposition: str  # WIN | PUSH | LOSS | VOID
    gross_return: float  # per unit stake (incl. stake): o_DNB / 1.0 / 0.0 / 1.0
    net_profit: float  # gross_return - 1 on a placed (non-void) bet; 0.0 on a refund
    counts_in_denominator: bool  # False for VOID and PUSH-excluding conventions (see note)


def _normalize_ftr(ftr: object) -> str | None:
    """Normalize a raw FTR token to 'H'/'D'/'A', a void marker, or None (missing)."""
    if ftr is None or (isinstance(ftr, float) and np.isnan(ftr)):
        return None
    s = str(ftr).strip().upper()
    if s == "":
        return None
    if s in {_FTR_HOME, _FTR_DRAW, _FTR_AWAY}:
        return s
    if s in VOID_FTR_TOKENS:
        return VOID
    return s  # unknown token; classified as void downstream (no silent win/loss)


def settle_one(
    ftr_90: object,
    underdog_side: object,
    o_dnb: float,
) -> Settlement:
    """Settle a single underdog DNB from the 90-minute FTR (CALC §10 map).

    Parameters
    ----------
    ftr_90 : str
        The 90-minute Full-Time Result: 'H', 'D', 'A', or a void/abandoned token. A
        penalty-decided level match must arrive here as 'D' (the 90' result), and it
        settles as a PUSH -- ET/penalty progression is irrelevant.
    underdog_side : str
        'home' or 'away' -- which side the bet is on (``src.selection.underdog_side``).
    o_dnb : float
        The DNB decimal odds on the underdog side (quoted AH-0 where present, else the
        synthetic ``src.pricing.synthetic_dnb``).

    Returns
    -------
    Settlement
        Disposition + per-unit gross return + net profit + denominator flag.

    Void handling: a void/abandoned 90-minute result, a missing FTR, an undefined
    underdog side, or a non-finite ``o_dnb`` -> VOID (refund, excluded from the win-ratio
    denominator). No outcome is fabricated.
    """
    ftr = _normalize_ftr(ftr_90)
    side = None if underdog_side is None else str(underdog_side).strip().lower()

    void = (
        ftr is None
        or ftr == VOID
        or ftr not in {_FTR_HOME, _FTR_DRAW, _FTR_AWAY}
        or side not in {"home", "away"}
        or not np.isfinite(o_dnb)
    )
    if void:
        return Settlement(VOID, RETURN_VOID, 0.0, counts_in_denominator=False)

    if ftr == _FTR_DRAW:
        # 90-minute draw -> push (refund), INCLUDING ET/penalty-decided knockouts.
        return Settlement(PUSH, RETURN_PUSH, 0.0, counts_in_denominator=True)

    underdog_won = (side == "home" and ftr == _FTR_HOME) or (side == "away" and ftr == _FTR_AWAY)
    if underdog_won:
        return Settlement(WIN, float(o_dnb), float(o_dnb) - 1.0, counts_in_denominator=True)
    return Settlement(LOSS, RETURN_LOSS, -1.0, counts_in_denominator=True)


def settle(
    panel: pd.DataFrame,
    *,
    ftr_col: str = "FTR",
    side_col: str = "sel_underdog_side",
    odds_col: str = "o_dnb_underdog",
) -> pd.DataFrame:
    """Vectorized three-way DNB settlement over a panel (idempotent; CALC §10).

    Adds, per row:

    * ``settle_disposition`` -- WIN | PUSH | LOSS | VOID;
    * ``settle_gross_return`` -- per-unit gross (o_DNB / 1.0 / 0.0 / 1.0);
    * ``settle_net_profit``   -- gross - 1 on a placed bet, 0.0 on a refund;
    * ``settle_in_denominator`` -- False for VOID (excluded from the win ratio).

    ``side_col`` defaults to the selection output ``sel_underdog_side``; pass
    ``side_col='underdog_side'`` to settle directly off the assembled-panel column. The
    function is pure (no state) and idempotent: re-running on its own output yields
    identical columns (it overwrites, never accumulates).

    The 90-minute result governs: ``decided_in_et`` / ``penalty_shootout`` are NOT read
    here, so an ET/penalty goal cannot change any disposition (EDGE §4.6).
    """
    out = panel.copy()
    n = len(out)

    ftr_raw = out[ftr_col] if ftr_col in out else pd.Series([None] * n, index=out.index)
    side_raw = out[side_col] if side_col in out else pd.Series([None] * n, index=out.index)
    odds_raw = (
        pd.to_numeric(out[odds_col], errors="coerce")
        if odds_col in out
        else pd.Series([np.nan] * n, index=out.index)
    )

    ftr = ftr_raw.map(_normalize_ftr)
    side = side_raw.map(lambda s: None if s is None or pd.isna(s) else str(s).strip().lower())
    odds = odds_raw.to_numpy(dtype="float64")

    is_real_ftr = ftr.isin([_FTR_HOME, _FTR_DRAW, _FTR_AWAY]).to_numpy()
    valid_side = side.isin(["home", "away"]).to_numpy()
    finite_odds = np.isfinite(odds)
    void = ~(is_real_ftr & valid_side & finite_odds)

    is_draw = (ftr == _FTR_DRAW).to_numpy()
    home_win = ((side == "home") & (ftr == _FTR_HOME)).to_numpy()
    away_win = ((side == "away") & (ftr == _FTR_AWAY)).to_numpy()
    underdog_won = (home_win | away_win) & ~void

    disposition = np.full(n, LOSS, dtype=object)
    disposition[void] = VOID
    disposition[~void & is_draw] = PUSH
    disposition[underdog_won] = WIN

    gross = np.full(n, RETURN_LOSS, dtype="float64")
    gross[disposition == VOID] = RETURN_VOID
    gross[disposition == PUSH] = RETURN_PUSH
    gross[disposition == WIN] = odds[disposition == WIN]

    net = np.where(
        (disposition == VOID) | (disposition == PUSH),
        0.0,
        gross - 1.0,
    )

    out["settle_disposition"] = pd.Series(disposition, index=out.index, dtype="string")
    out["settle_gross_return"] = gross
    out["settle_net_profit"] = net
    out["settle_in_denominator"] = pd.Series(disposition != VOID, index=out.index, dtype="boolean")
    return out


def win_ratio(settled: pd.DataFrame, *, disposition_col: str = "settle_disposition") -> float:
    """Win ratio = wins / (placed bets), with VOID excluded from the denominator.

    Pushes are RETAINED in the denominator (a push is a placed, settled bet -- the refund
    is an outcome of the bet, not a non-event). Voids are EXCLUDED (the bet was never a
    valid wager). This is the convention frozen in design.md §4 and ARCH §4.1; the hit
    ratio with pushes also excluded is a separate reporting variant (Phase 4 task 3,
    "refunds excluded from denominator, convention stated") and is not computed here.

    Returns NaN when no bets count in the denominator.
    """
    disp = settled[disposition_col].astype("string")
    in_denom = disp != VOID
    denom = int(in_denom.sum())
    if denom == 0:
        return float("nan")
    wins = int((disp == WIN).sum())
    return wins / denom
