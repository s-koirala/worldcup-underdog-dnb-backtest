"""World-Cup HOLD-OUT settlement panel: 90-minute FTR, aliases, qual-state, CLV tags.

Phase 1 slice (plan tasks 4, 5, 10; DATA §7.1-§7.2; CALC §10; EDGE §4.6).

This module builds the WORLD-CUP held-out match list with a regulation-time
(90-minute) Full-Time Result -- the block the headline out-of-sample verdict
rests on -- EVEN WHERE ODDS ARE PENDING. The honest data state (verified
2026-06-16):

  * ODDS: no clean public World-Cup 1X2 closing-odds source is obtainable
    headlessly in this environment. OddsPortal is JS-rendered + ToS-bound;
    every Kaggle/GitHub odds dataset (xgabora, eatpizzanot, the Hegarty-Whelan
    Zenodo replication package 10.5281/zenodo.12673394) traces back to
    football-data.co.uk's DOMESTIC-only scope and contains NO WC international
    matches. The WC transfer test is therefore PENDING-ODDS; Phases 2-4 run
    fully on the league universe meanwhile (plan A.1, Phase-1 risk).

  * RESULTS: genuinely accessible. Two independent, directly-downloadable
    sources are used and cross-reconciled:
      - jfjelstul/worldcup (academic DB): matches.csv + goals.csv +
        penalty_kicks.csv. goals.csv carries `match_period` and
        `minute_regulation`, which lets us recompute the score AT 90 MINUTES
        (sum only first-half / second-half goals, EXCLUDING extra time) --
        the rigorous, source-backed 90-min FTR reconstruction (DATA §6, §7.2;
        CALC §10). jfjelstul's match-level `home_team_score` is the FULL result
        (incl. ET) -- verified: 2014 final recorded 1-0 with extra_time=1, but
        90-min = 0-0 (a DNB push), which the goals.csv reconstruction recovers.
      - martj42/international_results: results.csv + shootouts.csv, used as the
        independent settlement cross-check (DATA §2.5).

KEY 90-MINUTE SETTLEMENT RULE (CALC §10; DATA Open Question 4; CALC Open Q 7):
a penalty-decided or extra-time-decided knockout match is settled on the
90-minute score. A match level at 90 minutes is a DNB PUSH regardless of the
shootout / ET winner. This is why the goals.csv `match_period` split is
load-bearing: it is the only field that distinguishes "won in ET" (90-min draw,
push) from "won in regulation".

No look-ahead: the qualification-state feature uses only group results available
BEFORE each match kickoff (plan task 7.1).
"""

from __future__ import annotations

import unicodedata
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = PROJECT_ROOT / "data" / "raw"
EXTERNAL_DIR = PROJECT_ROOT / "data" / "external"

# The project clean-odds-era pool: 6 editions x 64 = 384 matches (DATA §3.2).
PROJECT_WC_YEARS: tuple[int, ...] = (2002, 2006, 2010, 2014, 2018, 2022)

# Regulation-time match periods in jfjelstul goals.csv `match_period`. Anything
# tagged "extra time ..." is EXCLUDED from the 90-minute score (DATA §7.2).
REGULATION_PERIODS: frozenset[str] = frozenset(
    {
        "first half",
        "second half",
        "first half, stoppage time",
        "second half, stoppage time",
    }
)

# Manual historical-name aliases the normalized-name auto-match cannot bridge
# (different official names for the same entity across the two results sources).
# Each maps an alternate normalized key to the canonical normalized key. Reviewed,
# never silent (DATA §7.2). "Serbia and Montenegro" (jfjelstul, the correct 2006
# name) vs "Serbia" (martj42) is the one such case in the 2002-2022 WC pool.
MANUAL_NAME_ALIASES: dict[str, str] = {
    "serbia": "serbia and montenegro",
}

# CLV-era boundary: native AH columns (the entry+closing pair CLV needs) exist
# only from 2019/20 per football-data notes.txt (plan task 10; DATA §2.2, §7.1).
# For the WC, pre-2019/20 editions carry at most a single closing price, so CLV
# is undefined; we tag those rows synthetic_only / clv_defined=False. (The 2018
# edition predates 2019/20, so ALL 2002-2022 WC editions are CLV-undefined for
# the AH route; this is reported as the WC CLV-defined fraction in task 10.)
CLV_NATIVE_AH_FIRST_SEASON_YEAR = 2019


# --------------------------------------------------------------------------
# 90-minute FTR reconstruction (plan task 5; CALC §10).
# --------------------------------------------------------------------------


def reconstruct_90min_scores(matches: pd.DataFrame, goals: pd.DataFrame) -> pd.DataFrame:
    """Return per-match 90-minute home/away goals + FTR from jfjelstul tables.

    The 90-minute score sums ONLY regulation-period goals (excludes extra time
    and penalties). `goals.home_team`/`goals.away_team` are 0/1 flags marking
    which side of the fixture the scoring credit belongs to (own goals already
    resolved to the credited side in jfjelstul), so a simple count per side is
    correct.

    Output columns added to a copy of `matches` (keyed on `match_id`):
      `fthg_90`, `ftag_90`  -- 90-minute goals
      `ftr_90`              -- H/D/A on the 90-minute score (the DNB settlement)
      `decided_in_et`       -- True iff the match was level at 90 but the FULL
                               (incl-ET) recorded result was NOT a draw, i.e. ET
                               changed the apparent outcome (DNB push hidden in
                               the full result).
      `is_push_90`          -- True iff ftr_90 == 'D' (the DNB refund case).
    """
    reg = goals[goals["match_period"].isin(REGULATION_PERIODS)]
    # Count regulation goals per match per side.
    h90 = reg.groupby("match_id")["home_team"].sum()
    a90 = reg.groupby("match_id")["away_team"].sum()

    out = matches.copy()
    out["fthg_90"] = out["match_id"].map(h90).fillna(0).astype(int)
    out["ftag_90"] = out["match_id"].map(a90).fillna(0).astype(int)

    diff = out["fthg_90"] - out["ftag_90"]
    out["ftr_90"] = pd.Series(
        ["H" if d > 0 else "A" if d < 0 else "D" for d in diff], index=out.index
    )
    out["is_push_90"] = out["ftr_90"].eq("D")

    # Full-result FTR (incl. ET) from jfjelstul's match-level columns, for the
    # ET-changed-the-outcome diagnostic.
    full_diff = out["home_team_score"] - out["away_team_score"]
    full_ftr = pd.Series(
        ["H" if d > 0 else "A" if d < 0 else "D" for d in full_diff], index=out.index
    )
    out["decided_in_et"] = out["is_push_90"] & full_ftr.ne("D")
    return out


# --------------------------------------------------------------------------
# Team-name alias crosswalk (plan task 5 / DATA §7.2).
# --------------------------------------------------------------------------


def _norm(name: str) -> str:
    """Canonical key for a team name: strip accents, lowercase, collapse spaces,
    then apply the reviewed manual historical-name alias map (DATA §7.2)."""
    s = unicodedata.normalize("NFKD", str(name))
    s = "".join(c for c in s if not unicodedata.combining(c))
    key = " ".join(s.lower().split())
    return MANUAL_NAME_ALIASES.get(key, key)


def reconcile_settlement(panel: pd.DataFrame, mj_results: pd.DataFrame) -> pd.DataFrame:
    """Order-INSENSITIVE settlement cross-check of the panel vs martj42.

    A World-Cup match is the same fixture regardless of which source calls which
    side "home" -- the host/neutral home-away convention differs between
    jfjelstul and martj42 (e.g. martj42 lists the host as home). So the match key
    is (match_date, frozenset{normalized team names}); the recorded FTR is
    compared after re-orienting martj42's result to the panel's home/away order.

    Adds `ftr_full_martj42`, `martj42_matched`, `settlement_reconciled` to a copy
    of `panel` (uses the FULL incl-ET result on both sides, since martj42 also
    records incl-ET scores; the 90-min FTR is jfjelstul-derived and reconciled
    separately by the penalty/ET diagnostics).
    """
    out = panel.copy()
    mj = mj_results.copy()
    mj["date_str"] = pd.to_datetime(mj["date"]).dt.strftime("%Y-%m-%d")

    # martj42 lookup keyed on (date, frozenset of normalized names) -> outcome for
    # a specific (home_norm) perspective.
    mj_idx: dict[tuple[str, frozenset[str]], dict[str, str]] = {}
    for _, m in mj.iterrows():
        if pd.isna(m["home_score"]) or pd.isna(m["away_score"]):
            continue
        hn, an = _norm(m["home_team"]), _norm(m["away_team"])
        d = int(m["home_score"]) - int(m["away_score"])
        # store the result from the home team's perspective in BOTH name keys.
        key = (m["date_str"], frozenset({hn, an}))
        mj_idx[key] = {"home_norm": hn, "ftr": "H" if d > 0 else "A" if d < 0 else "D"}

    full_diff = out["home_team_score"] - out["away_team_score"]
    out["ftr_full_jfjelstul"] = ["H" if v > 0 else "A" if v < 0 else "D" for v in full_diff]

    mj_ftr = []
    for date, h, a in zip(
        out["match_date"], out["home_team_name"], out["away_team_name"], strict=True
    ):
        hn, an = _norm(h), _norm(a)
        rec = mj_idx.get((date, frozenset({hn, an})))
        if rec is None:
            mj_ftr.append(None)
            continue
        ftr = rec["ftr"]
        # re-orient to the panel's home/away if martj42's home is our away.
        if rec["home_norm"] != hn and ftr in ("H", "A"):
            ftr = "A" if ftr == "H" else "H"
        mj_ftr.append(ftr)

    out["ftr_full_martj42"] = mj_ftr
    out["martj42_matched"] = out["ftr_full_martj42"].notna()
    out["settlement_reconciled"] = out["martj42_matched"] & (
        out["ftr_full_jfjelstul"] == out["ftr_full_martj42"]
    )
    return out


def build_team_alias_crosswalk(
    jf_matches: pd.DataFrame, mj_results: pd.DataFrame, years: tuple[int, ...] = PROJECT_WC_YEARS
) -> pd.DataFrame:
    """Build the alias/crosswalk table mapping each source's team strings to a
    canonical key (DATA §7.2: fuzzy-join only with a reviewed mapping, never
    silent). Columns: canonical_key, jfjelstul_name, martj42_name, norm_key.

    The crosswalk is built by NORMALIZED-name match across the two results
    sources restricted to the WC project years; any name present in one source
    but not matched in the other is emitted with the missing side blank so the
    reviewer sees the unmatched residue explicitly (never a silent drop).
    """
    jf_names = pd.unique(
        pd.concat([jf_matches["home_team_name"], jf_matches["away_team_name"]]).dropna()
    )
    mj_names = pd.unique(pd.concat([mj_results["home_team"], mj_results["away_team"]]).dropna())

    jf_map = {_norm(n): n for n in jf_names}
    mj_map = {_norm(n): n for n in mj_names}
    all_keys = sorted(set(jf_map) | set(mj_map))

    rows = []
    for k in all_keys:
        jf = jf_map.get(k)
        mj = mj_map.get(k)
        # canonical name preference: jfjelstul (academic DB, full English names).
        canonical = jf or mj
        rows.append(
            {
                "canonical_key": canonical,
                "norm_key": k,
                "jfjelstul_name": jf or "",
                "martj42_name": mj or "",
                "matched_both": bool(jf and mj),
            }
        )
    return pd.DataFrame(rows).sort_values("canonical_key").reset_index(drop=True)


# --------------------------------------------------------------------------
# Point-in-time qualification-state feature (plan task 7.1) -- 32-team era.
# --------------------------------------------------------------------------


def qual_state_32team(matches_year: pd.DataFrame) -> pd.DataFrame:
    """Return a per-(match, team) qualification-state at kickoff for ONE 32-team
    edition (2002-2022), computable from the team's OWN group standings before
    kickoff (no look-ahead; plan task 7.1).

    32-team rule: 8 groups of 4, top 2 advance, 3 group rounds. A team's status
    at the kickoff of group matchday `r` (r in {1,2,3}) is:
      `live`       -- mathematically still able to finish top 2 AND not yet
                      mathematically secured top 2 (status undecided);
      `qualified`  -- already mathematically secured a top-2 finish before this
                      match (clinched);
      `eliminated` -- already mathematically unable to finish top 2.
    Matchday-1 is always `live` for every team (no prior results).

    Implementation note: this needs only the within-group results that PRECEDE
    each match, which the goals/match tables supply via match dates. The full
    clinch/elimination arithmetic over the 4-team group is implemented in
    `_group_qual_status`. Returns columns: match_id, team_id, matchday,
    qual_state. KNOCKOUT matches are tagged qual_state='knockout' (the dead-
    rubber stratum is a group-stage construct; EDGE §4.4).

    The 2026 48-team format (8 best third-placed -> Round of 32) makes status
    contingent on OTHER groups' results and is NOT computable from the group's
    own table alone; it is handled separately and treated as descriptive only
    (plan task 7.1, restriction to the 32-team headline block).
    """
    df = matches_year.copy()
    out_rows = []

    group_matches = df[df["group_stage"] == 1].copy()
    knockout_matches = df[df["knockout_stage"] == 1].copy()

    # Tag knockout matches (no group qual-state).
    for _, m in knockout_matches.iterrows():
        for tid in (m["home_team_id"], m["away_team_id"]):
            out_rows.append(
                {
                    "match_id": m["match_id"],
                    "team_id": tid,
                    "matchday": pd.NA,
                    "qual_state": "knockout",
                }
            )

    # Group stage: process per group, ordered by date, deriving matchday and the
    # pre-kickoff standings for each team.
    group_matches = group_matches.sort_values(["group_name", "match_date"])
    for _gname, gdf in group_matches.groupby("group_name"):
        gdf = gdf.sort_values("match_date").reset_index(drop=True)
        # Assign matchday by date-order within the group (4-team group => 3
        # rounds of 2 matches each; date-sorted pairs give matchday 1,1,2,2,3,3).
        gdf["matchday"] = (gdf.index // 2) + 1
        # Build the cumulative table BEFORE each matchday.
        played: list[dict] = []  # list of completed matches (90-min decided)
        for md in sorted(gdf["matchday"].unique()):
            md_matches = gdf[gdf["matchday"] == md]
            standings = _standings_from_played(played)
            for _, m in md_matches.iterrows():
                for tid in (m["home_team_id"], m["away_team_id"]):
                    state = _group_qual_status(tid, standings, played_count_before=len(played))
                    out_rows.append(
                        {
                            "match_id": m["match_id"],
                            "team_id": tid,
                            "matchday": int(md),
                            "qual_state": state,
                        }
                    )
            # After recording kickoff-state for this matchday, add its results to
            # the played history for the NEXT matchday's standings.
            for _, m in md_matches.iterrows():
                played.append(
                    {
                        "home": m["home_team_id"],
                        "away": m["away_team_id"],
                        # use 90-min FTR if present, else full result
                        "ftr": m.get("ftr_90", m.get("result")),
                        "hg": m.get("fthg_90", m.get("home_team_score")),
                        "ag": m.get("ftag_90", m.get("away_team_score")),
                    }
                )
    return pd.DataFrame(out_rows)


def _standings_from_played(played: list[dict]) -> dict[str, dict]:
    """3-points-for-a-win mini-table from a list of completed group matches."""
    tbl: dict[str, dict] = {}

    def _ensure(t: str) -> dict:
        return tbl.setdefault(t, {"pts": 0, "gd": 0, "played": 0})

    for m in played:
        h, a = _ensure(m["home"]), _ensure(m["away"])
        hg, ag = int(m["hg"]), int(m["ag"])
        h["played"] += 1
        a["played"] += 1
        h["gd"] += hg - ag
        a["gd"] += ag - hg
        if hg > ag:
            h["pts"] += 3
        elif ag > hg:
            a["pts"] += 3
        else:
            h["pts"] += 1
            a["pts"] += 1
    return tbl


def _group_qual_status(
    team_id: str, standings: dict, played_count_before: int, group_size: int = 4
) -> str:
    """Clinch/elimination status for `team_id` BEFORE its current match.

    Conservative, TIEBREAK-SAFE point arithmetic over a 4-team / 3-matchday group
    (top 2 advance). Because head-to-head / goal-difference tiebreaks are NOT
    modelled, a team that can FINISH LEVEL with me on points is treated as able
    to overtake me (it might win the tiebreak) -- so a level is neither a clinch
    nor an elimination guarantee. This makes 'qualified'/'eliminated' strict
    (only mathematically certain states), and everything else 'live'.

      * before matchday 1 (no matches played) -> 'live';
      * 'eliminated' iff at least `group_size - 2` (= 2) other teams have a
        MINIMUM final-points floor (their current points -- they can't lose
        points) that is STRICTLY GREATER than my MAXIMUM attainable points, i.e.
        at least two teams are certain to finish above me -> I cannot make top 2;
      * 'qualified' iff at most one other team can finish with points >= my
        current points (using >=, the tiebreak-safe test) -> I am certain top 2;
      * else 'live'.
    Each team plays 3 group games (games_left = 3 - played).
    """
    if played_count_before == 0:
        return "live"
    me = standings.get(team_id, {"pts": 0, "gd": 0, "played": 0})
    my_max = me["pts"] + 3 * (3 - me["played"])

    others = [(t, s) for t, s in standings.items() if t != team_id]

    # Eliminated: teams whose CURRENT points (their floor) already strictly exceed
    # my MAX are certain to finish above me; if >= (group_size - 2) such teams
    # exist, the top-2 slots are taken (tiebreak-safe: strict '>' on a certainty).
    certain_above = sum(1 for _, s in others if s["pts"] > my_max)
    if certain_above >= (group_size - 2):
        return "eliminated"

    # Qualified: count other teams that COULD finish with points >= mine (their
    # max attainable >= my current points). '>=' is tiebreak-safe -- a level team
    # might win the tiebreak, so it counts against my clinch. If at most one such
    # team exists, I am certain to be top 2.
    can_reach_me = sum(1 for _, s in others if (s["pts"] + 3 * (3 - s["played"])) >= me["pts"])
    if can_reach_me <= 1:
        return "qualified"
    return "live"


# --------------------------------------------------------------------------
# CLV-defined / synthetic-only tagging (plan task 10).
# --------------------------------------------------------------------------


def tag_clv_defined(panel: pd.DataFrame, year_col: str = "year") -> pd.DataFrame:
    """Add `clv_defined` and `synthetic_only` per row (plan task 10).

    CLV needs BOTH an entry (opening) and a closing price on the SAME selection.
    For the WC hold-out there is currently NO odds source at all (gap), and even
    when odds are obtained, native AH (the genuine entry+closing pair) exists only
    from 2019/20, so EVERY 2002-2022 WC edition is CLV-undefined for the AH route.
    Rows are tagged:
      `synthetic_only = True`  -- only a synthetic-DNB-from-1X2 (single closing)
                                  price is/will be available (no native AH pair);
      `clv_defined   = False`  -- no genuine entry+closing pair, so a CLV (closing-
                                  line-value) edge test must NOT be run on the row.
    The fraction is reported per universe x era in the data-quality report so a
    binding edge test is never run where CLV is undefined.
    """
    out = panel.copy()
    yr = out[year_col]
    out["synthetic_only"] = yr < CLV_NATIVE_AH_FIRST_SEASON_YEAR
    # With no WC odds source obtained, clv_defined is False for ALL rows; even with
    # odds, it would require a native entry+closing pair (>=2019/20). Encode both.
    out["clv_defined"] = (yr >= CLV_NATIVE_AH_FIRST_SEASON_YEAR) & out.get(
        "has_entry_and_closing", False
    )
    return out
