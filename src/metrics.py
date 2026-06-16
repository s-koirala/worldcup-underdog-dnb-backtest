"""Metrics-facing helpers for the DNB bet (plan Phase 2 task 4; CALC §5-§6).

The per-bet EV and three-point variance closed forms (CALC §5-§6) and the fair-win
benchmark / fair-price variance identity (CALC §6.2) are SINGLE-SOURCED in
:mod:`src.staking` (where they sit next to the push-Kelly ``f*`` they share ``b``,
``mu`` and ``p_fav`` with, so the three closed forms can never drift). This module
re-exports them under the metrics namespace so downstream metric/inference code
(Phase 4 ``src.metrics`` ROI/Sharpe/variance reporting) imports the EV/variance
helpers from here, while the staking path imports them -- and ``f*`` -- from
``src.staking``.

The full performance-metric suite (ROI/yield, hit ratio, per-bet Sharpe, Sortino,
MaxDD, turnover, CLV, each with a bootstrap CI) is Phase 4 (plan §"Phase 4" task 3)
and is added to this module then; this Phase-2 stub provides only the analytic
per-bet EV / variance helpers task 4 requires.
"""

from __future__ import annotations

from src.staking import (
    expected_value,
    fair_dnb_odds,
    fair_price_variance_reduction,
    fair_win_bet_variance,
    per_bet_variance,
)

__all__ = [
    "expected_value",
    "fair_dnb_odds",
    "fair_price_variance_reduction",
    "fair_win_bet_variance",
    "per_bet_variance",
]
