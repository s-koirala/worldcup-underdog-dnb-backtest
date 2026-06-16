# Note — World-Cup odds-acquisition gap and the results-only hold-out panel

Protocol note. Project: [worldcup-underdog-dnb-backtest](../../README.md). Author dimension: SKIE. Date: 2026-06-16.
Phase 1 slice: World-Cup hold-out odds acquisition + 90-minute settlement labelling (plan tasks 4, 5, 10).
Owning plan section: [plan_phased-workplan_2026-06-16.md](plan_phased-workplan_2026-06-16.md) Phase 1, tasks 4/5/10 + Phase-1 risk "No clean public World-Cup odds CSV".

This note records, with provenance, the genuine search for a downloadable World-Cup **odds** source, the honest **gap** that no such source is obtainable headlessly in this environment, and the **results-only** held-out panel that was built instead so the World-Cup match list and the 90-minute FTR exist while odds are pending.

---

## 1. Headline state

- **World-Cup ODDS: NOT OBTAINED (gap).** No clean public World-Cup 1X2 closing-odds dataset is obtainable headlessly in this environment. The World-Cup transfer test is therefore **PENDING-ODDS**; Phases 2–4 run fully on the domestic-league estimation universe meanwhile (plan A.1, Phase-1 risk). **No odds data were fabricated** (data-integrity rule).
- **World-Cup RESULTS: OBTAINED.** The 384-match held-out list (2002–2022, 6×64) with a rigorously reconstructed **90-minute** Full-Time Result, a team-name alias crosswalk, a point-in-time qualification-state / dead-rubber feature, and CLV/synthetic-only tags is built from two independent, directly-downloadable results sources and cross-reconciled (100% agreement).

---

## 2. The odds search (what was tried, with provenance)

A genuine, exhaustive search for a *downloadable* World-Cup odds source was performed on 2026-06-16. Every candidate was probed by an actual headless fetch, not assumed:

| Candidate | Probe result | Verdict |
|---|---|---|
| **OddsPortal** `oddsportal.com/football/world/world-cup-2022/results/` | Static HTML returned **only navigation chrome — no scores, no odds**; the numeric content is JS-rendered. ToS prohibits scraping. | Not headlessly fetchable; ToS-bound. |
| **Kaggle** "Beat the Bookie", "Historical Football Results/Betting Odds", etc. | Require account auth (no headless download); the football-odds ones are **football-data.co.uk domestic** re-exports. | No WC international odds; auth-blocked. |
| **GitHub `xgabora/Club-Football-Match-Data-2000-2025`** (`data/Matches.csv`) | Downloaded + inspected: `Division` codes are club leagues only (`E0,D1,SP1,ARG,BRA,…`); **no World-Cup / international rows**. | Domestic club only. |
| **GitHub `eatpizzanot/soccer-dataset`** (`csv/odds.csv`, `leagues.csv`) | Downloaded `leagues.csv`: 59 **domestic club leagues**; no FIFA World Cup league id. | Domestic club only. |
| **Zenodo `10.5281/zenodo.12673394`** — Hegarty–Whelan "Tale of Two Markets" replication package | Downloaded `ReadMe.txt` + `notes.txt`: data "collected … from the football-data historical csv file repository" (`https://www.football-data.co.uk/data.php`); `raw_data1.0.csv` is the combined football-data **domestic** file. | Academic-grade, but **domestic-league only** — no WC. |
| **The Odds API historical** | Metered, API-key-gated. | Not obtainable headlessly. |

**Conclusion (confirms DATA §2.2):** every accessible odds dataset traces back to football-data.co.uk's **domestic-only** scope. There is no licensed, machine-readable, free World-Cup odds product; every World-Cup-odds path is a ToS-governed, JS-rendered scrape that cannot be re-derived byte-for-byte from a source URL.

---

## 3. The run-once scrape contract (provenance only)

Per plan task 4(i), a documented, **non-deterministic, run-once** scrape contract is retained for provenance at [src/scrape_wc_odds.py](../../src/scrape_wc_odds.py). It is **NOT** wired into `make reproduce-data` (the scrape is inherently non-reproducible). It records the target editions, the required 1X2-opening/1X2-closing/native-AH-0.0 columns (so the output is directly consumable by the Phase-2 pricing module and so CLV can be defined where the source carries line movement), and the operator preconditions (a browser-automation backend + explicit ToS acceptance). If a scrape is ever performed out-of-band, its output is frozen as `data/raw/wc_odds_<snapshot_date>.csv` + `.sha256` + a provenance JSON, and **that committed-by-checksum artifact** — not the source URL — is pinned in [config/baseline.yaml](../../config/baseline.yaml) `wc_holdout.odds_snapshot_sha256` and the ReproLog `dataset_checksums`: the held-out analysis is then **reproducible-from-snapshot, not reproducible-from-source** (plan §D.4).

---

## 4. The results-only hold-out panel (what was built)

Built by [src/build_wc_panel.py](../../src/build_wc_panel.py) → `data/processed/wc_holdout_panel.parquet` (+ `.csv` mirror), from:

- **jfjelstul/worldcup** (academic FIFA World Cup database, GitHub `master`): `matches.csv`, `goals.csv`, `penalty_kicks.csv`. The **settlement source**.
- **martj42/international_results** (GitHub `master`): `results.csv`, `shootouts.csv`. The **independent cross-check** (DATA §2.5).

Both are directly downloadable (HTTP 200, no auth) and are archived to `data/raw/` with LF-normalized SHA-256 sidecars + provenance JSONs under `data/raw/provenance/`.

### 4.1 90-minute FTR reconstruction (task 5 — the load-bearing step)

jfjelstul's match-level `home_team_score`/`away_team_score` is the **FULL result including extra time** (verified: the 2014 final Germany–Argentina is recorded **1-0** with `extra_time=1`, but the only goal — Götze, 113' — was an ET goal, so the **90-minute score was 0-0**, a DNB push). Settling DNB on the recorded full result would therefore mis-settle every ET-decided knockout.

The fix uses `goals.csv`, which carries a `match_period` label per goal. The 90-minute score sums **only** regulation-period goals (`first half`, `second half`, and their `…, stoppage time` variants), **excluding** every `extra time …` period. Validated against known matches:

| Match | Full (incl. ET) | Reconstructed 90-min | 90-min FTR | DNB |
|---|---|---|---|---|
| 2014 final Germany–Argentina | 1–0 (ET) | **0–0** | D | **push** |
| 2010 final Netherlands–Spain | 0–1 (ET) | **0–0** | D | **push** |
| 2006 SF Germany–Italy | 0–2 (ET) | **0–0** | D | **push** |
| 2006 final Italy–France | 1–1 (ET, pens) | **1–1** | D | **push** |

**Penalty-decided rule (task 5 acceptance):** all **21** penalty-shootout matches in 2002–2022 are level at 90 minutes and settle as a **DNB push** regardless of the shootout winner — verified for every one (unit-tested in [tests/test_wc_holdout.py](../../tests/test_wc_holdout.py) `test_penalty_decided_level_match_is_dnb_push`).

**Draw-rate consequence (DATA §6, Open Question 5):** the reconstruction recovers **12 additional 90-minute draws** that extra time turned into decided results. The arithmetic closes exactly:

```
full-result draws (incl. ET) = 88   (= DATA §6 recomputed 22.9% × 384)
+ ET-decided 90-min draws     = 12
= 90-minute (regulation) draws = 100  →  90-min draw rate q = 100/384 = 26.04%
```

The **regulation-time** WC 2002–2022 draw rate (the genuine DNB push frequency `q`) is **26.04%**, materially higher than the recorded-result 22.9% — exactly the direction DATA §6 anticipated ("ET decides some matches → the 90-min draw rate exceeds the recorded knockout rate"). This `q` is the value to carry to the power calc, not the 22.9% full-result anchor.

### 4.2 Alias crosswalk (task 5 / DATA §7.2)

`data/external/team_aliases.csv` maps each source's team strings to a canonical key by accent-stripped normalized-name match across the two results sources (restricted to the WC project years), surfacing any unmatched residue explicitly (never a silent drop). One reviewed historical-name alias is required: **"Serbia and Montenegro"** (jfjelstul, the correct 2006 name) ↔ **"Serbia"** (martj42). With it applied, all 61 WC teams match in both sources.

### 4.3 Settlement cross-reconciliation

The 90-minute panel's full-result FTR is cross-checked against martj42 **order-insensitively** (a WC fixture is the same regardless of which source calls which side "home" — the host/neutral home-away convention differs; e.g. martj42 lists the host as home). After re-orienting to the panel's home/away order, **384/384 (100%) of matches reconcile** between the two independent sources.

### 4.4 Point-in-time qualification-state / dead-rubber feature (task 7.1)

`qual_state ∈ {live, qualified, eliminated}` per (match, team) at kickoff, computed from the team's **own** group standings using **only results that precede each match** (no look-ahead). The 32-team-era rule (top 2 of 4 advance) is used; the clinch/elimination arithmetic is **tiebreak-safe** (a rival that can finish level on points blocks a clinch, since head-to-head/GD tiebreaks are not modelled) — validated against the South Africa 2002 case (4 points at matchday 3 is correctly **live**, not clinched: South Africa did not qualify). A group match where **both** sides are already decided is flagged `dead_rubber` (the EDGE §4.4 stratum where the only candidate WC edge lives); the famous Belgium–England 2018 dead rubber is correctly tagged. **10** group dead-rubbers across 2002–2022; knockout matches carry `qual_state='knockout'`. (The 2026 48-team format makes status contingent on *other* groups' third-place comparison and is out of this 384-match block; it is treated as descriptive-only per plan task 7.1 and is not built here.)

### 4.5 CLV-defined / synthetic-only fraction (task 10)

CLV needs a genuine **entry + closing** pair on the same selection. Native AH columns (the genuine pair) exist only from 2019/20 per football-data `notes.txt`, and the 2018 edition predates that, so **every** 2002–2022 WC edition is CLV-undefined for the AH route — and with **no WC odds obtained at all**, no row has an entry+closing pair. Therefore:

- `clv_defined = False` for **100%** of WC rows (CLV-defined fraction = **0.0000**);
- `synthetic_only = True` for **83.3%** of rows (the pre-2019/20 editions: 2002–2018 = 5/6 editions); the 2022 edition is past the 2019/20 native-AH boundary but, absent any obtained odds, still carries no CLV pair.

Consequence (carried to Phase 4 / the report card): a binding CLV edge test must **not** be run on the WC block; realized-return + Deflated-Sharpe is the primary edge test for these synthetic-only rows, exactly as the plan's honest-prior framing requires.

---

## 5. Honest gap statement (for the report card and Phase 4/5)

> The World-Cup hold-out is currently a **results-only** panel. The 384-match list (2002–2022) and its **90-minute** Full-Time Result are obtained, source-cross-reconciled (100%), and reproducible-from-snapshot (checksummed jfjelstul + martj42 raw pulls). **No World-Cup odds were obtainable headlessly and none were fabricated**, so the **underdog-DNB transfer test on the World Cup is PENDING-ODDS**. The rule and all hyperparameters are frozen on the domestic-league universe (Phases 2–4) regardless; the World-Cup transfer number is reported only once a ToS-cleared, checksum-frozen WC-odds snapshot exists. CLV is **undefined** for the entire WC block (CLV-defined fraction 0.0); realized-return + Deflated-Sharpe is the primary WC edge diagnostic when odds arrive.

### 5.1 Formal acceptance-criterion amendment (2026-06-16)

The Phase-1 acceptance criterion originally read "*every row carries `refC_*`, `ref_book`, `underdog_side`, `o_dnb_underdog`*" with no block qualifier — UNMET for the 384 WC rows given the odds gap above. Because fabricating WC odds is prohibited and no clean public source was obtainable, the criterion is **formally amended** (plan Phase-1 "Amendment A1"): the `refC_*`/`underdog_side`/`o_dnb_underdog` completeness requirement is **scoped to the league estimation block** (complete), and the **World-Cup transfer verdict is recorded as an explicitly DEFERRED, GATE-BLOCKED deliverable** — blocking precondition: a ToS-cleared, checksum-frozen WC closing-odds snapshot (task 4 / [src/scrape_wc_odds.py](../../src/scrape_wc_odds.py)). The deferral is registered in [docs/research/research_gaps-register_2026-06-16.md](../research/research_gaps-register_2026-06-16.md) (P1 row "World-Cup odds acquisition / transfer-test gate-block"). On snapshot arrival, re-running `--stage ingest`/`--stage validate` fills the WC odds fields from the pinned hash and lifts the gate with no other code change ([src/assemble.py](../../src/assemble.py) `wc_to_canonical` already populates `refC_*`/`underdog_side`/`o_dnb_underdog` when odds are present). **Net effect: the estimation universe is complete; the headline OOS transfer verdict is gate-blocked, not failed.**

---

## 6. Artifacts produced by this slice

| Artifact | Path |
|---|---|
| WC hold-out panel (90-min FTR, qual-state, dead-rubber, CLV tags) | `data/processed/wc_holdout_panel.parquet` (+ `.csv`) |
| Team-name alias crosswalk | `data/external/team_aliases.csv` |
| Raw results sources (immutable, checksummed) | `data/raw/wc_jfjelstul_{matches,goals,penalties}_2026-06-16.csv`, `data/raw/intl_{results,shootouts}_2026-06-16.csv` (+ `.sha256`) |
| Provenance records (URL + fetch context + SHA-256) | `data/raw/provenance/*.provenance.json` |
| 90-min reconstruction / alias / qual-state / CLV code | [src/wc_holdout.py](../../src/wc_holdout.py) |
| Panel builder + ReproLog emitter | [src/build_wc_panel.py](../../src/build_wc_panel.py) |
| Provenance fetch helper | [src/provenance.py](../../src/provenance.py) |
| Run-once scrape contract (provenance only) | [src/scrape_wc_odds.py](../../src/scrape_wc_odds.py) |
| Unit tests (incl. penalty-push, ET-exclusion, qual-state) | [tests/test_wc_holdout.py](../../tests/test_wc_holdout.py) |
| Per-run ReproLog (dataset_checksums pinned) | `logs/reprolog_wc-ingest-<run_id>.json` |

## 7. Citations / sources of record (accessed 2026-06-16)

1. jfjelstul/worldcup — *A Comprehensive Database on the FIFA World Cup* (matches/goals/penalty_kicks, with per-goal `match_period`). https://github.com/jfjelstul/worldcup (GitHub `master`).
2. Mart Jürisoo, *International football results from 1872 to 2026* (`results.csv`, `shootouts.csv`). https://github.com/martj42/international_results (GitHub `master`).
3. football-data.co.uk — *Notes* (`AHh` / native-AH since 2019/20; closing-`C` convention). https://www.football-data.co.uk/notes.txt.
4. Hegarty, T., & Whelan, K. (2025). *Forecasting Soccer Matches With Betting Odds: A Tale of Two Markets*, IJF 41(2):803–820, DOI [10.1016/j.ijforecast.2024.06.013](https://doi.org/10.1016/j.ijforecast.2024.06.013); replication package Zenodo DOI [10.5281/zenodo.12673394](https://doi.org/10.5281/zenodo.12673394) (verified domestic-league only — no WC odds).
5. OddsPortal World-Cup-2022 results page (verified JS-rendered, no static odds; ToS-bound). https://www.oddsportal.com/football/world/world-cup-2022/results/.
