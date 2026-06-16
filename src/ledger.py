"""Chronological PnL ledger, equity path, and bankroll state (Phase 3 task 2; ARCH §2.2).

Walks a time-ordered set of settled underdog DNB bets, applying a staking scheme
(src.staking) and the execution-cost model (src.costs) to produce a per-bet ledger
whose every entry carries BOTH a gross and a net (cost-adjusted) PnL. Net is the
reported figure: the Phase-4 metrics engine consumes ``net_pnl`` / ``net_equity``
(slice brief; ADR-0004 reporting precondition).

Two load-bearing invariants the tests enforce:

  * NON-ANTICIPATION (STAT §9.2; ARCH §2.2 staking contract). The stake on bet ``t``
    is sized from ``(o_dnb_t, p_win_t, p_draw_t, bankroll_before_t)`` ONLY -- the
    bankroll *before* bet ``t``, which by construction depends only on the settled
    outcomes of bets ``< t``. The stake never reads bet ``t``'s own (or any future)
    result. The ledger walks strictly in date order and computes the stake from the
    running bankroll BEFORE settling the bet, so permuting future results cannot move
    an earlier stake (test_ledger.py property test).
  * CONSERVATION (ARCH §2.2 ledger contract). For both the gross and the net columns,
    ``equity_t = equity_0 + sum(pnl_{<=t})`` to machine precision -- the equity path
    is exactly the cumulative sum of realised PnL on top of the initial bankroll.
    :func:`check_conservation` asserts this.

Bankroll dynamics. ``W_t = W_{t-1} + s_t * r_t`` where ``s_t`` is the cash stake and
``r_t in {o_dnb-1, 0, -1}`` is the settled NET-return multiple (a win nets ``o_dnb-1``,
a push/void nets 0 -- stake refunded -- and a loss nets ``-1``). The GROSS PnL uses the
settlement gross return; the NET PnL re-prices the win leg through the cost model
(src.costs: slippage + leg-out + exchange commission). The bankroll used to size the
NEXT stake is the NET bankroll (you compound what you actually keep), so the cost model
feeds back into sizing -- which is the honest, tradable dynamics.

Zero-stake handling. A negative-edge Kelly/fractional-Kelly bet sizes ``f* = 0`` ->
stake 0 -> a recorded ledger entry with zero PnL and an unchanged bankroll (a "did not
bet" entry, not a dropped row), so the all-negative-edge honest-prior case (slice brief;
STAKE §7.3) produces a flat equity path of zeros, cleanly, rather than an empty ledger.

No magic numbers (the initial bankroll is a config/CLI input; every stake parameter is
the scheme's swept grid value; the cost magnitudes are data-selected in src.costs).
pathlib not required here (pure in-memory dataframe walk). No global RNG -- the ledger
is deterministic given the ordered bets, stakes, and costs.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from src import costs as costs_mod
from src import settlement, staking

# Initial-bankroll convention. The wealth path is scale-FREE for the multiplicative
# schemes (fixed_fraction / kelly / fractional_kelly stake a fraction of current
# bankroll), so W_0 = 1.0 is the canonical normalised unit -- equity is then read
# directly as a growth multiple. It is a CONVENTION (a unit choice), not a tuned
# value; the CLI/config can override it. Flat / level_to_odds are cash stakes whose
# ruin dynamics depend on W_0, so the bankroll-MC stage (src.ruin, Phase 3 task 4)
# sweeps W_0; the per-pass ledger uses the configured unit.
DEFAULT_INITIAL_BANKROLL = 1.0

# Columns the ledger reads from the settled panel. These are the PRE-KICKOFF signal
# (o_dnb, devigged p) + the settlement outcome; the stake is sized from the signal,
# the PnL realised from the outcome.
DEFAULT_ODDS_COL = "o_dnb_underdog"
# The underdog 1X2 closing price that the open->close slippage buckets were cut on
# (src.ingest.open_close_moves). Used to resolve each bet's odds bucket so the per-bucket
# slippage is APPLIED per bet (ADR-0004; Phase-3 task 9), not the pooled value. Absent ->
# the cost model falls back to resolving the bucket from o_dnb / pooled.
DEFAULT_UNDERDOG_PRICE_COL = "underdog_price"
DEFAULT_PWIN_COL = "p_win"
DEFAULT_PDRAW_COL = "p_draw"
DEFAULT_DATE_COL = "date"
DEFAULT_MATCH_ID_COL = "match_id"
DEFAULT_GROSS_RETURN_COL = "settle_gross_return"
DEFAULT_DISPOSITION_COL = "settle_disposition"


@dataclass(frozen=True)
class LedgerResult:
    """The chronological ledger frame + the bankroll endpoints (gross and net)."""

    ledger: pd.DataFrame  # one row per bet, time-ordered; gross + net columns
    initial_bankroll: float
    final_gross_bankroll: float
    final_net_bankroll: float
    n_bets: int
    n_staked: int  # bets with a positive stake (excludes f*=0 "do not bet" entries)
    scheme: str
    scheme_params: dict[str, float]

    @property
    def net_returns(self) -> np.ndarray:
        """Per-bet NET arithmetic returns on staked capital (the Phase-4 metric input).

        ``net_pnl / stake`` on staked bets; the unit the per-bet Sharpe / ROI / ruin
        Monte-Carlo consume. Bets with zero stake contribute no return (they are not
        wagers); returned for the staked subset only.
        """
        led = self.ledger
        staked = led[led["stake"] > 0.0]
        with np.errstate(divide="ignore", invalid="ignore"):
            r = (staked["net_pnl"] / staked["stake"]).to_numpy(dtype="float64")
        return r[np.isfinite(r)]


def _order_bets(panel: pd.DataFrame, *, date_col: str, match_id_col: str) -> pd.DataFrame:
    """Sort bets by ``(date, match_id)`` -- the deterministic chronological order.

    Row order is sorted before any reduction (ARCH §3.2 "Determinism guarantees")
    so two runs walk the bets identically. The date is football-data ``DD/MM/YY`` for
    league rows; parse to a sortable timestamp for ordering only (never used as a
    signal). A stable secondary key on ``match_id`` breaks intra-day ties
    deterministically -- this fixes the WITHIN-matchday order, which the sequential
    single-bet ledger needs to be reproducible (the concurrency-correct joint sizing
    is the vector-Kelly path, src.vector_kelly).
    """
    out = panel.copy()
    # Parse the date for ORDERING only (dayfirst = football-data DD/MM/YY).
    out["_order_dt"] = pd.to_datetime(out[date_col], dayfirst=True, errors="coerce")
    sort_keys = ["_order_dt"]
    if match_id_col in out.columns:
        sort_keys.append(match_id_col)
    out = out.sort_values(sort_keys, kind="stable").reset_index(drop=True)
    return out


def build_ledger(
    panel: pd.DataFrame,
    *,
    scheme: str,
    scheme_params: dict[str, float] | None = None,
    cost_model: costs_mod.CostModel | None = None,
    initial_bankroll: float = DEFAULT_INITIAL_BANKROLL,
    odds_col: str = DEFAULT_ODDS_COL,
    underdog_price_col: str = DEFAULT_UNDERDOG_PRICE_COL,
    pwin_col: str = DEFAULT_PWIN_COL,
    pdraw_col: str = DEFAULT_PDRAW_COL,
    date_col: str = DEFAULT_DATE_COL,
    match_id_col: str = DEFAULT_MATCH_ID_COL,
    gross_return_col: str = DEFAULT_GROSS_RETURN_COL,
    disposition_col: str = DEFAULT_DISPOSITION_COL,
) -> LedgerResult:
    """Walk the settled bets chronologically into a gross+net PnL ledger (ARCH §2.2).

    ``panel`` must already carry the de-vigged ``p_win``/``p_draw`` (src.pricing),
    the DNB odds ``o_dnb_underdog``, and the settlement columns (src.settlement.settle:
    ``settle_gross_return`` + ``settle_disposition``). The walk:

      1. order bets by (date, match_id);
      2. for each bet, size the stake from (o_dnb, p_win, p_draw, bankroll_before)
         via src.staking.stake(scheme, ...) -- bankroll_before is the NET running
         bankroll (non-anticipation: depends only on settled outcomes of earlier bets);
      3. realise the GROSS PnL ``stake * (gross_return - 1)`` (a push/void's gross
         return is 1.0 -> 0 PnL; a loss 0.0 -> -stake; a win o_dnb -> stake*(o_dnb-1));
      4. realise the NET PnL by re-pricing through the cost model (slippage + leg-out
         + commission); when no cost model is supplied, net == gross (an explicitly
         labelled GROSS-ONLY ledger -- net metrics require the cost model, ADR-0004).

    Returns a :class:`LedgerResult` whose ``ledger`` frame has, per bet:
    ``stake, gross_return, net_return, gross_pnl, net_pnl,
    gross_bankroll_before, gross_bankroll_after, net_bankroll_before,
    net_bankroll_after`` plus the carried ``date/match_id/o_dnb/disposition``.
    """
    params = dict(scheme_params or {})
    bets = _order_bets(panel, date_col=date_col, match_id_col=match_id_col)
    n = len(bets)

    o = pd.to_numeric(bets[odds_col], errors="coerce").to_numpy(dtype="float64")
    # Underdog 1X2 closing price for per-bet odds-bucket resolution (slippage applies
    # per bucket; ADR-0004 / Phase-3 task 9). Absent -> None per bet -> the cost model
    # resolves from o_dnb / falls back to pooled.
    if underdog_price_col in bets:
        under_price = pd.to_numeric(bets[underdog_price_col], errors="coerce").to_numpy(
            dtype="float64"
        )
    else:
        under_price = np.full(n, np.nan, dtype="float64")
    p_w = pd.to_numeric(bets[pwin_col], errors="coerce").to_numpy(dtype="float64")
    p_d = pd.to_numeric(bets[pdraw_col], errors="coerce").to_numpy(dtype="float64")
    gross_ret = pd.to_numeric(bets[gross_return_col], errors="coerce").to_numpy(dtype="float64")
    disp = (
        bets[disposition_col].astype("string").to_numpy()
        if disposition_col in bets
        else np.array([None] * n, dtype=object)
    )

    stake_arr = np.zeros(n, dtype="float64")
    gross_ret_used = np.full(n, np.nan, dtype="float64")
    net_ret_used = np.full(n, np.nan, dtype="float64")
    gross_pnl = np.zeros(n, dtype="float64")
    net_pnl = np.zeros(n, dtype="float64")
    gross_before = np.zeros(n, dtype="float64")
    gross_after = np.zeros(n, dtype="float64")
    net_before = np.zeros(n, dtype="float64")
    net_after = np.zeros(n, dtype="float64")

    w_gross = float(initial_bankroll)
    w_net = float(initial_bankroll)

    for t in range(n):
        gross_before[t] = w_gross
        net_before[t] = w_net

        # --- size the stake from the PRE-KICKOFF signal + the bankroll BEFORE bet t.
        # The NET bankroll funds the next stake (compound what you keep). A non-finite
        # signal (missing odds / probs) -> zero stake (no fabricated wager), recorded.
        if not (np.isfinite(o[t]) and np.isfinite(p_w[t]) and np.isfinite(p_d[t])):
            s = 0.0
        else:
            s = float(staking.stake(scheme, o[t], p_w[t], p_d[t], w_net, **params))
            if not np.isfinite(s) or s < 0.0:
                s = 0.0
        # A stake cannot exceed the current bankroll (no leverage / no negative wealth);
        # this binds only for pathological fixed-fraction phi > 1, never for Kelly f<1.
        s = min(s, w_net) if np.isfinite(w_net) else s
        stake_arr[t] = s

        # --- realise GROSS and NET PnL from the settled outcome.
        if s > 0.0 and np.isfinite(gross_ret[t]):
            gr = float(gross_ret[t])
            gross_ret_used[t] = gr
            g_pnl = s * (gr - 1.0)
            gross_pnl[t] = g_pnl
            w_gross = w_gross + g_pnl

            # No cost model -> gross-only ledger (net == gross; explicitly labelled,
            # ADR-0004); otherwise re-price the win leg through slippage/leg-out/commission.
            # The odds bucket is resolved from the underdog 1X2 price (the slippage-cut
            # variable) so the PER-BUCKET slippage bites (ADR-0004 / Phase-3 task 9).
            if cost_model is None:
                nr = gr
            else:
                bucket = (
                    cost_model.slippage.resolve_odds_bucket(float(under_price[t]))
                    if np.isfinite(under_price[t])
                    else None
                )
                nr = cost_model.net_return(float(o[t]), gr, odds_bucket=bucket)
            net_ret_used[t] = nr
            n_pnl = s * (nr - 1.0)
            net_pnl[t] = n_pnl
            w_net = w_net + n_pnl
        # else: zero-stake / non-settleable -> zero PnL, bankrolls unchanged (recorded).

        gross_after[t] = w_gross
        net_after[t] = w_net

    ledger = pd.DataFrame(
        {
            date_col: bets[date_col].to_numpy() if date_col in bets else np.array([None] * n),
            match_id_col: (bets[match_id_col].to_numpy() if match_id_col in bets else np.arange(n)),
            "o_dnb": o,
            disposition_col: disp,
            "stake": stake_arr,
            "gross_return": gross_ret_used,
            "net_return": net_ret_used,
            "gross_pnl": gross_pnl,
            "net_pnl": net_pnl,
            "gross_bankroll_before": gross_before,
            "gross_bankroll_after": gross_after,
            "net_bankroll_before": net_before,
            "net_bankroll_after": net_after,
        }
    )

    return LedgerResult(
        ledger=ledger,
        initial_bankroll=float(initial_bankroll),
        final_gross_bankroll=float(w_gross),
        final_net_bankroll=float(w_net),
        n_bets=n,
        n_staked=int((stake_arr > 0.0).sum()),
        scheme=scheme,
        scheme_params=params,
    )


def check_conservation(result: LedgerResult, *, atol: float = 1e-9) -> bool:
    """Assert ``equity_t = equity_0 + sum(pnl_{<=t})`` on BOTH gross and net (ARCH §2.2).

    The equity path (``*_bankroll_after``) must equal the initial bankroll plus the
    cumulative realised PnL at every step, for both the gross and the net columns.
    Returns True on success; raises ``AssertionError`` with the first breach otherwise.
    ``atol`` is a floating-point accumulation tolerance (a numerical constant, not a
    tunable) -- the equality is exact in exact arithmetic.
    """
    led = result.ledger
    w0 = result.initial_bankroll
    for pnl_col, eq_col in (
        ("gross_pnl", "gross_bankroll_after"),
        ("net_pnl", "net_bankroll_after"),
    ):
        cum = w0 + led[pnl_col].cumsum().to_numpy(dtype="float64")
        eq = led[eq_col].to_numpy(dtype="float64")
        if not np.allclose(cum, eq, atol=atol, rtol=0.0):
            bad = int(np.argmax(~np.isclose(cum, eq, atol=atol, rtol=0.0)))
            raise AssertionError(
                f"conservation breach in {eq_col} at bet {bad}: "
                f"equity={eq[bad]!r} != equity_0 + sum(pnl)={cum[bad]!r}"
            )
    return True


def prepare_settled_bets(
    panel: pd.DataFrame,
    *,
    devig_method: str = "shin",
    block: str | None = "league",
    side_col: str = "underdog_side",
    odds_col: str = DEFAULT_ODDS_COL,
) -> pd.DataFrame:
    """De-vig + settle the canonical panel into the ledger's bet table (price->stake glue).

    Convenience assembler used by the ``--stage stake`` entrypoint: takes the canonical
    ``data/processed/matches.parquet`` rows, de-vigs the 1X2 closing reference price to
    ``p_win``/``p_draw`` on the UNDERDOG side (src.pricing.devig, a-priori-frozen Shin
    primary), and settles the 90-minute result (src.settlement.settle). Returns the rows
    that carry a finite DNB price and a settleable outcome -- the bet table build_ledger
    walks. Rows with no usable closing price (the logged vendor-missingness; Phase-1
    Gate 1) are excluded here, not silently: they were never settleable wagers.

    ``p_win`` is the underdog (backed-side) fair win probability and ``p_draw`` the fair
    draw probability -- exactly the (p_win, p_draw) the EV/Kelly closed forms expect.
    """
    from src import pricing

    df = panel.copy()
    if block is not None and "block" in df.columns:
        df = df[df["block"] == block].copy()

    needed = ["refC_H", "refC_D", "refC_A", side_col, odds_col]
    have = (
        df[needed].notna().all(axis=1)
        if all(c in df for c in needed)
        else pd.Series([False] * len(df), index=df.index)
    )
    df = df[have].copy()

    p_win = np.full(len(df), np.nan, dtype="float64")
    p_draw = np.full(len(df), np.nan, dtype="float64")
    h = df["refC_H"].to_numpy(dtype="float64")
    d = df["refC_D"].to_numpy(dtype="float64")
    a = df["refC_A"].to_numpy(dtype="float64")
    side = df[side_col].astype("string").to_numpy()
    for i in range(len(df)):
        try:
            ph, pd_, pa = pricing.devig(float(h[i]), float(d[i]), float(a[i]), method=devig_method)
        except (ValueError, RuntimeError):
            continue  # degenerate book -> not a settleable bet (logged upstream)
        p_draw[i] = pd_
        p_win[i] = pa if str(side[i]).lower() == "away" else ph
    df["p_win"] = p_win
    df["p_draw"] = p_draw

    # The underdog 1X2 CLOSING price (refC_A away / refC_H home) -- the variable the
    # open->close slippage buckets were cut on (src.ingest.open_close_moves), so the
    # per-bet odds bucket is resolved from THIS price, not from the DNB composite o_dnb
    # (which is a different price object; ADR-0004 "Slippage magnitude" 1X2->DNB mapping).
    df["underdog_price"] = np.where(
        df[side_col].astype("string").str.lower().to_numpy() == "away",
        df["refC_A"].to_numpy(dtype="float64"),
        df["refC_H"].to_numpy(dtype="float64"),
    )

    # Settle the 90-minute result on the underdog side.
    settled = settlement.settle(df, side_col=side_col, odds_col=odds_col)
    # Keep rows with a finite price + a valid devig (a settleable bet table).
    keep = settled["p_win"].notna() & settled["p_draw"].notna() & settled[odds_col].notna()
    return settled[keep].reset_index(drop=True)


def ledger_summary(result: LedgerResult) -> dict[str, Any]:
    """Compact, JSON-serialisable summary of a ledger pass (for the stage ReproLog/CLI).

    Reports gross AND net side by side (net is the headline; gross is shown only
    alongside its net counterpart and explicitly labelled -- ADR-0004). Growth/ROI is
    the realised wealth multiple ``final/initial`` minus 1; this is a NET figure when a
    cost model was applied (the only one that may be reported as net, ADR-0004).
    """
    w0 = result.initial_bankroll
    return {
        "scheme": result.scheme,
        "scheme_params": result.scheme_params,
        "n_bets": result.n_bets,
        "n_staked": result.n_staked,
        "initial_bankroll": w0,
        "final_gross_bankroll": result.final_gross_bankroll,
        "final_net_bankroll": result.final_net_bankroll,
        "gross_growth_multiple": (result.final_gross_bankroll / w0) if w0 else float("nan"),
        "net_growth_multiple": (result.final_net_bankroll / w0) if w0 else float("nan"),
        "conservation_ok": check_conservation(result),
    }
