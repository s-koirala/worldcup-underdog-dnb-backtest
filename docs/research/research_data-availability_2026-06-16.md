# Data Availability and Engineering for a World-Cup Underdog Draw-No-Bet Backtest

## Scope

This document is the data-engineering research dimension for the project **"Backtest a FIFA World Cup underdog Draw-No-Bet (DNB) strategy."** The strategy backs the **underdog** — the team with the higher decimal win price (lower implied probability) — on a **Draw-No-Bet** basis (stake refunded on a 90-minute draw; identical payoff to Asian Handicap 0.0).

The deliverable enumerates and verifies data sources, quantifies the achievable sample size by World Cup era, specifies the universe-expansion plan (domestic leagues as the estimation universe, World Cup as a held-out subsample), defines point-in-time correctness requirements, fixes the data schema and join keys, documents draw-rate base rates, and lists the data-quality gates. It does **not** perform the backtest, estimate edge, or run inference — those are downstream dimensions. Every factual claim is tied to a verified primary source (official documentation, peer-reviewed literature, or professional standard) in the [Citations](#citations) section.

Reporting against the quant-project rule set in [rules/quant-project.md](../../../.claude/rules/quant-project.md): this document fixes the *universe, data vendor, snapshot date, and survivorship treatment* that the backtest report must later cite, and enforces point-in-time integrity (no look-ahead) at the data layer.

---

## 1. The DNB payoff identity and its variance (engineering target)

The data schema must support exact settlement of the DNB bet from whatever odds columns a source provides. Two representations exist; both must be reconcilable.

### 1.1 Native DNB / Asian Handicap 0.0

A handicap of `0.0` ("level ball", "tie no bet") refunds the stake on a draw and is, by construction, the Draw-No-Bet market: only Home-win and Away-win are live outcomes, the draw is a push ([Wikipedia, *Asian handicap* — "Draw → Stake refund"](https://en.wikipedia.org/wiki/Asian_handicap)). football-data.co.uk carries native AH odds (`AHh` market line plus `B365AHH/B365AHA`, `PAHH/PAHA` and their closing `C` variants); when the posted line is exactly 0, those columns *are* DNB.

### 1.2 Synthetic DNB from 1X2 decimal odds (primary construction)

When only 1X2 decimal odds `(H, D, A)` are available, DNB on the away (underdog) side is replicated by a stake split:

- place `1/D` of the unit on the **draw** at decimal odds `D`, and
- place `1 − 1/D` of the unit on the **away win** at decimal odds `A`.

On a draw the draw leg returns `(1/D)·D = 1`, exactly refunding the unit; the away leg loses → net 0 (push). On an away win the away leg returns `(1 − 1/D)·A`; the draw leg loses. The effective DNB decimal odds on the away side are therefore

```
o_DNB,away = (1 − 1/D) · A = A·(D − 1)/D.
```

Symmetrically for a home DNB: `o_DNB,home = H·(D − 1)/D`.

**Worked example.** Underdog (away) at `A = 4.00`, draw `D = 3.40`:
`o_DNB = 4.00 · (3.40 − 1)/3.40 = 4.00 · 2.40/3.40 = 4.00 · 0.70588 = 2.8235`.
A unit staked returns 2.8235 on an away win (profit +1.8235), 1.0000 on a draw (profit 0), 0 on a home win.

### 1.3 Per-bet variance (sample-size driver)

**Two-outcome fair win bet.** For a fair single win bet at decimal odds `o` with win probability `p = 1/o`, the per-unit P&L is `(o−1)` with prob `p` and `−1` with prob `(1−p)`. Mean `= p·(o−1) − (1−p) = 0`; second moment `= p·(o−1)² + (1−p)·1`. With `p = 1/o`:

```
Var = (1/o)(o−1)² + (1 − 1/o) = (o−1)²/o + (o−1)/o = (o−1)[(o−1)+1]/o = (o−1).
```

So **per-bet variance = `o − 1`** for a *fair two-outcome win bet*. This matches the sibling methodology doc's load-bearing identity ([research_statistical-methodology_2026-06-16.md §2.10](research_statistical-methodology_2026-06-16.md)).

**Three-outcome DNB bet — the `o − 1` identity does NOT carry over.** DNB is not a two-outcome bet: it has a third outcome, the draw *push* (payoff exactly 0), with probability `p_d`. The P&L is `(o_DNB − 1)` on the underdog win (prob `p_A`), `−1` on the favorite win (prob `p_H`), and `0` on the draw (prob `p_d`), with `p_A + p_H + p_d = 1`. At the fair DNB price the live (no-push) outcomes are priced fairly, i.e. `o_DNB = (1 − p_d)/p_A` so that `E[R_DNB] = 0`. The second moment then includes the push, which contributes zero to `E[R²]` but shrinks the win/loss mass to `1 − p_d`:

```
Var(R_DNB) = E[R_DNB²] = p_A·(o_DNB − 1)² + p_H·1 + p_d·0  (E[R_DNB] = 0 at the fair price)
           = (1 − p_d)·(o_DNB − 1).
```

So **at the fair price, `Var(R_DNB) = (1 − p_d)·(o_DNB − 1)`** — the straight two-outcome value `o_DNB − 1` is reduced by the no-push factor `(1 − p_d)`. Numerically verified: with `p_H = 0.55`, `p_d = 0.25`, `p_A = 0.20` the fair DNB odds are `o_DNB = (1 − 0.25)/0.20 = 3.75`, giving `Var(R_DNB) = 0.75·2.75 = 2.0625`, **not** `o_DNB − 1 = 2.75` (the latter overstates variance by 33%). Applying the two-outcome `o − 1` identity directly to DNB is therefore an error.

**Consequences for §3.** The straight-win `o − 1` is a strict **upper bound** on DNB variance (since `0 < 1 − p_d ≤ 1`), not the DNB variance itself; it is used in §3 only as a *conservative prior* for the power calculation, never as a settled estimate. The actual per-bucket DNB variance must be **measured empirically** from the assembled table (per odds bucket, against realized push frequency), as flagged in the methodology doc's open-question 5 ([research_statistical-methodology_2026-06-16.md](research_statistical-methodology_2026-06-16.md)). Margin and favorite-longshot distortion move the realized variance further from any analytic value, reinforcing that the bound is a prior, not an estimate.

---

## 2. Source enumeration: coverage, granularity, access

### 2.1 football-data.co.uk — the domestic estimation universe (primary)

The pivotal source for the universe-expansion plan. Column semantics are taken **verbatim** from the official notes file ([football-data.co.uk/notes.txt](https://www.football-data.co.uk/notes.txt)) and the data index ([football-data.co.uk/data.php](https://www.football-data.co.uk/data.php)).

**Coverage (verified):**

| Tier | Countries | Earliest | Odds onset | Granularity |
|---|---|---|---|---|
| **Main Leagues** | England, Scotland, Germany, Italy, Spain, France, Netherlands, Belgium, Portugal, Turkey, Greece (11 countries, up to 22 divisions) | results back to **1993/94** | bookmaker 1X2 odds back to **2000/01** | pre-match + **closing**; match stats |
| **Extra Leagues** | Argentina, Austria, Brazil, China, Denmark, Finland, Ireland, Japan, Mexico, Norway, Poland, Romania, Russia, Sweden, Switzerland, USA (16 countries) | results + **closing** match odds back to **2012/13** | best & average market price + **Pinnacle** | closing only (one row/match) |

**Odds columns (verified from notes.txt).** Pre-match: `B365`, `BW`, `IW`, `PS` (Pinnacle Sports), `WH`, `VC`, plus market `Max` and `Avg`, and `BFE` (Betfair Exchange) — each suffixed `H/D/A`. **Closing** odds append a `C` after the bookmaker abbreviation: `B365CH`, `PSCH/PSCD/PSCA` (Pinnacle closing), `MaxCH`, `AvgCH`, `BFECH`, etc. Official definition: *"For the closing odds, as below but with an additional 'C' character following the bookmaker abbreviation/Max/Avg."* Asian Handicap: `AHh` = market size of handicap (home team), **available since 2019/20**; `B365AHH/A`, `PAHH/A` (Pinnacle AH), and closing `B365CAHH/A`, `PCAHH/A`.

**Why Pinnacle is the reference book.** Pinnacle is a low-margin "sharp" bookmaker whose closing line is the standard efficient-market benchmark. Two distinct results support this. First, on the *level* of expected loss: average loss rates are in fact **higher** than the raw overround implies, because the favourite-longshot bias loads bookmakers' margin disproportionately onto longshots ([Hegarty & Whelan 2025, *Estimating Expected Loss Rates in Betting Markets: Theory and Evidence*, Applied Economics, DOI 10.1080/00036846.2025.2507979](https://doi.org/10.1080/00036846.2025.2507979)) — so the overround is a floor, not the true cost, especially in the underdog region this strategy targets. Second, on *market efficiency*: the Asian-handicap market (which is exactly the DNB construction here, §1.2) generates efficient forecasts for the same matches in which the traditional 1X2 market shows strong favourite-longshot bias ([Hegarty & Whelan 2025, *Forecasting Soccer Matches With Betting Odds: A Tale of Two Markets*, International Journal of Forecasting 41(2):803–820, DOI 10.1016/j.ijforecast.2024.06.013](https://doi.org/10.1016/j.ijforecast.2024.06.013)) — both studies built on Pinnacle data. The closing line is the relevant point-in-time price for a strategy that bets at or near kickoff (§4).

> **CAVEAT — Pinnacle feed degraded from 2025-07-23 (affects 2025/26 onward and the 2026 World Cup window).** The vendor's own data index now carries the following notice ([football-data.co.uk/data.php](https://www.football-data.co.uk/data.php), accessed 2026-06-16), quoted verbatim:
>
> *"Since 23/07/2025 Pinnacle's public API for odds delivery has become unreliable meaning their odds are systematically out of date relative to odds for other bookmakers, including both the pre-closing and closing odds. Consequently they should be used with caution when undertaking any betting analyses, and are no longer being included for the calculation of market average and maximum odds."*
>
> **Consequence for this project.** The `PSC*` (Pinnacle closing 1X2) reference-price recommendation is therefore restricted to **seasons predating 2025/26** — i.e. up to and including 2024/25 — where the Pinnacle closing line remains the efficient-market benchmark of record. For **2025/26 onward**, including the 2025/26 domestic data the universe-expansion plan extends into and the 2026 World Cup window the project targets, `PSC*` must **not** be used as the closing benchmark; substitute the **market average / maximum closing columns `AvgC*` / `MaxC*`** (which, per the notice, now *exclude* the stale Pinnacle leg) or the **Betfair Exchange closing `BFEC*`** (commission-, not overround-, priced; reconcile per §2.3). The cutover season is logged as **2025/26 = first season on the non-Pinnacle closing reference**; pre-2025/26 stays on `PSC*`. This split must be carried through §4.2 (estimation universe), §5 (PIT closing-price field), §6 (push-frequency base rates), and the §7 schema, where the reference-price column is now season-conditional rather than always `PSC*`. Note `AvgC*`/`MaxC*` are *consensus* prices, not a single sharp book, so the de-vig and favorite-longshot treatment of §5.4 is re-checked on the post-cutover segment (a max-odds column in particular understates margin and is not a fair-price proxy); the empirical population-rate gate of open-question 2 is extended to confirm `AvgC*`/`BFEC*` coverage on 2025/26+.

**Access.** Static CSVs, no auth, path scheme `https://www.football-data.co.uk/mmz4281/{SEASON}/{DIV}.csv` where `SEASON` is the 4-digit compaction (e.g. `2526` = 2025/26) and `DIV` is the division code (`E0` = Premier League, `D1` = Bundesliga, `SP1` = La Liga, `I1` = Serie A, `F1` = Ligue 1, etc.). Extra-league files are single CSVs per country (e.g. `new/ARG.csv`). Updated twice weekly. Personal-use terms — see §2.9 on licensing.

### 2.2 World Cup odds — there is no clean public CSV

football-data.co.uk does **not** publish a World Cup file; its scope is domestic league divisions only (the 11 Main + 16 Extra countries above). World Cup 1X2 closing odds must be assembled from:

- **OddsPortal** (oddsportal.com): historical 1X2 + AH closing and movement, World Cup back to ~2002; HTML/JS, no official API → scraping, subject to ToS.
- **Covers** (covers.com): historical line/consensus archives, US-centric, moneyline format (convertible to decimal).
- **Kaggle international-results datasets** (see §2.5): provide *results* but **not odds**.

There is no licensed, machine-readable, free World Cup odds product; every path is a scrape governed by site ToS. This is the central data-availability constraint behind the universe-expansion mandate.

### 2.3 Betfair Historical Data Service (exchange truth, optional)

Time-stamped Exchange order-book data for registered Betfair customers via `https://historicdata.betfair.com`. Tiers: **BASIC** (free; last-traded-price per minute, no volume), **ADVANCED** and **PRO** (paid; full price ladder + traded volume + BSP). Near-complete coverage of Exchange markets since **2016** (post-APING). Files are `.bz2`/`.tar` JSON streams; convertible to CSV via the Betfair Historical Data Processor ([Betfair Developer Program — Historical Data](https://support.developer.betfair.com/hc/en-us/articles/360002407732-What-data-is-provided-by-the-Historical-Data-service)). Use case: independent verification of the closing price and a *commission-aware* exchange DNB (Betfair offers a native Draw-No-Bet market) — but only the 2018 and 2022 World Cups fall in coverage, and exchange prices carry commission (typically 2–5%), not overround.

### 2.4 Commercial odds APIs

- **The Odds API** (the-odds-api.com): historical + live, decimal, multiple books, includes "draw_no_bet" / "h2h" markets; metered request credits.
- **OddsJam / OpticOdds**: enterprise historical odds incl. closing-line snapshots; paid.
- **API-Football (api-sports.io)**: 1,200+ leagues incl. World Cup; odds endpoint exists but historical odds depth and book breadth are weaker than dedicated odds vendors; free tier 100 req/day ([API-Football coverage](https://www.api-football.com/coverage)).

### 2.5 Results sources (settlement ground truth)

- **football-data.org**: 12 free competitions incl. **World Cup**, fixtures/results/tables, 10 req/min ([football-data.org/coverage](https://www.football-data.org/coverage)). Free tier is permanent for top competitions.
- **API-Football**: 1,236 leagues, free tier 100 req/day.
- **Kaggle "International football results 1872–2024"** (Mart Jürisoo, `martj42/international-football-results-from-1872-to-2017`): complete international result set incl. all World Cup matches, neutral-venue flag, CSV. **Results only, no odds.**
- **RSSSF** (rsssf.org): authoritative historical result archive for cross-validation.

### 2.6 Source comparison matrix

| Source | Domain | Odds? | Open/Close | WC coverage | Access | Cost |
|---|---|---|---|---|---|---|
| football-data.co.uk | domestic | 1X2 + AH | **both** (Main); close (Extra) | none | static CSV | free |
| OddsPortal | all incl. WC | 1X2 + AH | both + movement | ~2002→ | scrape | free/ToS |
| Covers | all incl. WC | moneyline | line history | deep | scrape | free/ToS |
| Betfair Hist. | exchange | back/lay + DNB | full ladder | 2016→ (WC 2018, 2022) | acct download | free/paid |
| The Odds API | broad | 1X2/DNB | snapshots | recent | REST | metered |
| API-Football | broad | 1X2 | limited hist. | yes | REST | freemium |
| football-data.org | broad | none | n/a | results | REST | free tier |
| Kaggle intl-results | international | none | n/a | all WC results | CSV | free |

### 2.7 Licensing / ToS constraints

football-data.co.uk publishes for **personal use**; redistribution of raw files is discouraged — store locally, cite the snapshot date, do not re-host. Scraping OddsPortal/Covers is governed by each site's ToS and rate limits; capture provenance (URL, fetch timestamp) and respect robots/rate constraints. Betfair historical data requires an account and (for paid tiers) purchase, and carries the Betfair data licence. Under [rules/publishing.md](../../../.claude/rules/publishing.md) identity-hygiene, no scraped credentials or real-name metadata enter committed files; raw vendor data stays in `data/raw/` and is git-ignored.

---

## 3. Sample-size arithmetic by World Cup era

### 3.1 Match counts per format (verified)

| Era | Teams | Tournaments | Matches / tournament |
|---|---|---|---|
| 1982–1994 | 24 | 1982, 86, 90, 94 | **52** |
| 1998–2022 | 32 | 1998…2022 (7) | **64** |
| 2026→ | 48 | 2026 | **104** |

The 32-team era produced 64 matches via 8 groups of 4 (48 group + 16 knockout); the 24-team era produced 52; 2026's 48-team / 12-group format produces **104** matches ([FIFA — *How the FIFA World Cup 26 will work with 48 teams*](https://www.fifa.com/en/articles/article-fifa-world-cup-2026-mexico-canada-usa-new-format-tournament-football-soccer); [Britannica — *2026 FIFA World Cup*](https://www.britannica.com/event/2026-FIFA-World-Cup)).

### 3.2 Clean-odds era and usable n

Clean, comparable 1X2 closing odds for the World Cup are realistically available from **2002** onward (the OddsPortal archive depth). The 32-team tournaments 2002–2022 = 6 editions × 64 = **384 matches** — the project's stated prior. This is the *full* underdog-DNB pool only if every match has a defined favorite/underdog; matches priced as near-coin-flips (`H ≈ A`) carry an ambiguous "underdog" and may be dropped, shrinking effective n further.

### 3.3 Power arithmetic (why 384 is underpowered)

Per §1.3, a fair two-outcome win bet has per-bet variance `o − 1`, which is a *conservative upper bound* on the three-outcome DNB variance `(1 − p_d)·(o_DNB − 1)`. Using the upper bound (it inflates `n`, so the power requirement below is conservative): underdog DNB lines cluster around `o_DNB ≈ 2.2–3.0`; take a representative `o_DNB = 2.5` ⇒ per-bet variance ≲ `1.5`, per-bet sd ≲ `1.225`. Suppose a true per-bet edge `μ` (mean P&L per unit). The t-statistic over `n` bets is `t = μ√n / sd`. To detect a *positive* edge at 5% one-sided (`z ≈ 1.645`) with 80% power (`z ≈ 0.84`) requires

```
n ≥ ((1.645 + 0.84)·sd / μ)² = (2.485 · 1.225 / μ)² = (3.044 / μ)².
```

- A large `+5%` edge (`μ = 0.05`): `n ≥ (3.044/0.05)² ≈ 3,707` bets.
- A `+2%` edge (`μ = 0.02`): `n ≥ ≈ 23,170` bets.

Against `n ≈ 384` (and far fewer after the coin-flip drop), the World Cup alone can only resolve an edge of magnitude `μ ≥ 3.044/√384 = 3.044/19.6 ≈ 0.155` — i.e. a **+15.5% per-bet** (one-sided) effect, since the `3.044 = (1.645 + 0.84)·1.225` constant in the required-`n` formula already contains the per-bet sd of `1.225` (inverting `n = (3.044/μ)²` for `μ` at `n = 384` must not multiply by sd a second time). A +15.5% per-bet edge is wildly implausible. The World Cup sample is therefore underpowered for any realistic edge, confirming the project prior. (Sharpe-based inference is the same statement in ratio units: a per-bet Sharpe `SR = μ/sd ≈ 0.041` for the `+5%` case needs `n ≈ (z/SR)² = (2.485/0.041)² ≈ 3,674`, matching above.) Inference on the realized Sharpe must use the small-sample-aware standard error of [Lo 2002, *The Statistics of Sharpe Ratios*, Financial Analysts Journal 58(4):36–52, DOI 10.2469/faj.v58.n4.2453](https://doi.org/10.2469/faj.v58.n4.2453): `se(SR) ≈ √((1 + ½SR²)/T)`, per the bootstrap/asymptotic-CI mandate in [rules/quant-project.md](../../../.claude/rules/quant-project.md).

These thresholds (5% α, 80% power) are stated as the **register inputs** to a pre-data power analysis, not as the analysis itself; the actual required-n is fixed downstream by the `power-analysis` skill against the pre-registered effect of interest, after the effect is justified (no post-hoc power, per Hoenig & Heisey 2001).

---

## 4. Universe-expansion plan: domestic leagues as the estimation universe

### 4.1 Rationale

The World Cup is statistically underpowered (§3.3). The mitigation is to **estimate the underdog-DNB edge on the large domestic universe** (where Pinnacle closing 1X2 and AH columns exist back to 2000/01 / 2012/13, usable as the reference through 2024/25 before the 2025-07-23 feed degradation — §2.1) and treat the **World Cup as a held-out, out-of-sample subsample** — never used to fit the rule, only to test transfer. Because the 2026 World Cup falls *after* the Pinnacle cutover, the held-out set is priced on the non-Pinnacle closing reference (`AvgC*`/`MaxC*`/`BFEC*`); to keep train and test on a comparable price basis, the late-domestic segment (2025/26) used for the most recent walk-forward window is put on the same non-Pinnacle reference, and the regime change is itself a transfer risk to report. This mirrors the time-ordered, disjoint train/test discipline required by [rules/quant-project.md](../../../.claude/rules/quant-project.md) (walk-forward, no k-fold).

### 4.2 Candidate estimation set and approximate match counts

Using football-data.co.uk Main Leagues with Pinnacle closing 1X2 (`PSCH/PSCD/PSCA`) reliably populated from the early-2010s closing-odds era **through 2024/25** (the last full season before the 2025-07-23 Pinnacle-feed degradation, §2.1 caveat); the 2025/26 segment and the 2026 World Cup hold-out use the non-Pinnacle closing reference (`AvgC*`/`MaxC*` or `BFEC*`) instead:

| Division pool | ~Matches/season | ~Seasons w/ closing PS odds | ~Pool n |
|---|---|---|---|
| Top-5 first divisions (E0, D1, SP1, I1, F1) | ~380×3 + 306×2 ≈ 1,752 | ~12 (2012/13→2024/25) | **~21,000** |
| + second tiers (E1, D2, SP2, etc.) | adds ~2,000/season | ~12 | **+~24,000** |
| Extra leagues (16 countries) | varies | 2012/13→ | **+ tens of thousands** |

Even the top-5-first-division pool (~21k matches) exceeds the §3.3 power requirement for a `+2%` edge by an order of magnitude. This is the analytic justification for the expansion: the domestic universe makes the edge *estimable*; the World Cup makes it *generalization-testable*.

### 4.3 Mapping the World Cup as held-out

- **Strict hold-out:** the rule (which side = underdog, any odds filter, any staking cap) is frozen on the domestic universe; the World Cup matches are scored once, never used to select hyperparameters. The pre-kickoff favorite/underdog assignment uses the same closing-Pinnacle-implied-probability rule on both sets.
- **Held-out generalization gap:** report domestic in-sample edge, domestic walk-forward out-of-sample edge, and World-Cup-transfer edge as three separate numbers with separate CIs.

### 4.4 Risks of pooling (must be modeled, not ignored)

1. **Different draw rates.** Pooling changes the DNB push frequency, which directly affects realized variance and turnover. Recomputed on the assembled 90-minute-result tables (§6), the international draw rate is **comparable to, slightly lower than** top-club leagues — World Cup 2002–2022 D = 22.9% (n=384) and competitive-international D = 21.3% vs EPL 23.2% / UCL 21.4% — **not** the higher rate previously asserted. The push-frequency gap is therefore small (≈ 0–2 pts) and directionally toward *fewer* international pushes, so the variance/turnover impact of pooling on this axis is second-order; the load-bearing pooling risks are the venue and talent-dispersion effects (risks 2–3), not the draw rate. The genuinely material draw-rate effect is the *within-World-Cup* group-vs-knockout split, and even that must be re-measured on regulation-time `FTR` because knockout extra time deflates the recorded 90-minute draw count (§6).
2. **Neutral-venue home advantage.** Domestic data embeds a structural home-field effect; World Cup matches are largely neutral (host excepted). The `H/A` columns are not symmetric in meaning across the two universes. The favorite/underdog assignment via odds is venue-robust (the book has already priced venue), but any feature built on the raw `H/A` distinction is not transferable. Use the odds-implied probability, not the home/away label, as the underdog definition.
3. **Talent dispersion.** Group-stage World Cup matches exhibit wider talent gaps (and thus more extreme underdog prices) than mid-table league fixtures, exactly the favorite-longshot region where mispricing is largest ([Cain, Law & Peel 2000, *Scottish Journal of Political Economy* 47(1):25–36, DOI 10.1111/1467-9485.00151](https://doi.org/10.1111/1467-9485.00151)). The edge may be *non-stationary across the odds range*, so the domestic fit must be conditioned on the odds bucket, and the World Cup's odds distribution checked against the domestic one before claiming transfer.
4. **Margin/efficiency drift.** Bookmaker forecasting accuracy improved over the 2000s ([Forrest, Goddard & Simmons 2005, *International Journal of Forecasting* 21(3):551–564, DOI 10.1016/j.ijforecast.2005.03.003](https://doi.org/10.1016/j.ijforecast.2005.03.003)); pooling across a long window mixes regimes. Walk-forward, not pooled-static, estimation is required.

---

## 5. Point-in-time correctness

1. **Pre-kickoff odds only.** The settlement field (`FTR`) is realized after kickoff; any odds used as a feature must be timestamped strictly before kickoff. football-data.co.uk's pre-match columns (`PSH/PSD/PSA`) are pre-kickoff; the **closing** columns (`PSCH/PSCD/PSCA`) are the *last* pre-kickoff prices and are the correct choice for a near-kickoff bet — they are not post-match. **Season-conditional reference:** for seasons through 2024/25 the closing reference is `PSC*` (Pinnacle closing); for 2025/26 onward the Pinnacle feed is degraded (§2.1 caveat) and the closing reference is `AvgC*`/`MaxC*` or `BFEC*`. The point-in-time property is unchanged — all of these are *last* pre-kickoff prices — but the column that carries the reference price switches at the 2025/26 cutover.
2. **Closing-line capture.** Closing line is the most efficient available price; using it as the feature both maximizes realism and gives the conservative (hardest-to-beat) benchmark. For scraped World Cup data, capture the last price before kickoff and store the fetch timestamp.
3. **Revision / leakage avoidance.** Never join on any field computed from the final score except the settlement outcome. The underdog assignment is `argmax(refC_H, refC_A)` on the season-conditional closing reference (point 1; `PSC*` for ≤ 2024/25, `AvgC*`/`MaxC*`/`BFEC*` for ≥ 2025/26) — higher decimal = lower implied prob, evaluable pre-kickoff. The `pit-canary` skill (inject a known future-knowing feature; it must dominate if the pipe leaks) is the prescribed leak test before any backtest run.
4. **Overround stripping.** Implied probabilities `1/refC_H + 1/refC_D + 1/refC_A = 1 + margin` on the season-conditional reference (point 1). Normalize per match to remove overround before any probability comparison; the basic (proportional) normalization is the floor, but the favorite-longshot shape means proportional de-vig is biased, so use the bias-aware **Shin probabilities**, which endogenously model the longshot bias as a margin that loads more heavily on longshots. **Post-cutover caveat:** if `refC_*` is sourced from `MaxC*` (best-price consensus) the sum can fall to ≈ 1 or below — a max-odds column is not a single-book fair-price proxy — so on the 2025/26+ segment prefer `AvgC*` (or `BFEC*`, then convert commission to an effective margin) for the de-vig step, and re-fit the Shin insider-trading parameter `z` on that segment rather than reusing the Pinnacle-era value. Shin's model derives from [Shin 1993, *Measuring the Incidence of Insider Trading in a Market for State-Contingent Claims*, Economic Journal 103(420):1141–1153, DOI 10.2307/2234240](https://doi.org/10.2307/2234240) and is validated as the most accurate odds-to-probability method (vs. basic normalization and regression) in [Štrumbelj 2014, *On determining probability forecasts from betting odds*, International Journal of Forecasting 30(4):934–943, DOI 10.1016/j.ijforecast.2014.02.008](https://doi.org/10.1016/j.ijforecast.2014.02.008). Keep raw odds for settlement.

---

## 6. Draw-rate base rates (the DNB push frequency)

The draw is the DNB push; its base rate drives realized variance and turnover and must be reported per [rules/quant-project.md](../../../.claude/rules/quant-project.md).

Figures below for the international/World-Cup rows are **recomputed directly** from the martj42 international-results CSV ([Jürisoo, Kaggle/GitHub `martj42/international_results`](https://github.com/martj42/international_results), `results.csv`, accessed 2026-06-16; direct H/D/A count over rows with non-null scores), superseding the earlier aggregator (FootyStats/WinDrawWin) estimates. **Distinction that matters for DNB:** this dataset records the *result the match is logged with* — for older knockout editions that includes extra-time goals (penalty-shootout outcomes are not in the score), so the recorded draw rate is a **lower bound on the 90-minute draw rate**: ET turns some 90-minute level scores into a decided result, deflating apparent draws. A 90-minute (regulation) `FTR` must be reconstructed (§7.2) before the push frequency is finalized; the figures here are full-result counts unless noted.

| Universe | Draw rate (recomputed) | n | H / D / A | Note |
|---|---|---|---|---|
| International — all (1872–2024) | **22.7%** | 49,421 | 49.0 / 22.7 / 28.2 | full-result counts |
| International — competitive (non-friendly) | **21.3%** | 31,033 | 50.0 / 21.3 / 28.7 | excludes friendlies |
| FIFA World Cup — all editions (1930–2022) | **22.7%** | 980 | 45.5 / 22.7 / 31.8 | full-result; ET inflates older knockouts |
| FIFA World Cup — 2002–2022 (project sample) | **22.9%** | 384 | **43.5 / 22.9 / 33.6** | the 6-edition odds-era pool |
| World Cup group stage | ~16–22% | — | — | varies by edition; 2018 group = 8/48 ≈ 16.7% (still aggregator-sourced; recompute) |
| World Cup knockout (90-min) | recompute | — | — | ET decides some matches → 90-min draw rate exceeds the *recorded* knockout rate; needs regulation `FTR` |
| English Premier League (10y) | **23.2%** | 3,799 | — | 882/3799 |
| UEFA Champions League | **21.4%** | 2,245 | — | 480/2245 |

**Direction of the international-vs-club comparison is corrected.** The recomputed World-Cup 2002–2022 draw rate (22.9%, n=384) and competitive-international rate (21.3%) are **at or below**, not above, the document's own EPL figure (23.2%) — and the all-international rate (22.7%) is likewise below EPL. The earlier "International ≈ 25% > top-club ≈ 21–23%" claim, and the "home 50.5% / draw 25% / away 24.5%" split, are both **wrong for this universe**: the project-sample split is H 43.5% / D 22.9% / A 33.6% (away understated by ~9 pts, draw overstated). The correct structural statement is that the international draw rate is **comparable to, slightly lower than** top-club leagues — which *weakens* (and at the competitive-only margin reverses) the §4.4-risk-1 pooling argument that international play raises DNB push frequency. The within-World-Cup group-vs-knockout split remains material and is the one genuinely format-dependent effect, but its magnitude must come from the recomputed regulation-time table, not aggregator vendors. This is consistent with the favorite-longshot literature's treatment of the draw as a distinct, often-mispriced outcome ([Cain, Law & Peel 2000, DOI 10.1111/1467-9485.00151](https://doi.org/10.1111/1467-9485.00151)), but no longer rests on an inflated international draw rate.

---

## 7. Data schema, join keys, settlement fields

### 7.1 Canonical match record (assembled table)

| Field | Type | Source | Notes |
|---|---|---|---|
| `match_id` | str | derived | `{competition}_{season}_{date}_{home}_{away}` |
| `competition` | cat | meta | `WC2018`, `E0`, `D1`, … |
| `season` | cat | meta | `1819` |
| `date` | date | `Date` | football-data: `DD/MM/YY` |
| `kickoff_utc` | datetime | `Time` (if present) / scrape | PIT gate (§5) |
| `home_team`, `away_team` | str | `HomeTeam`/`AwayTeam` | normalize via alias map |
| `neutral` | bool | Kaggle intl flag / meta | True for most WC |
| `FTHG`, `FTAG` | int | football-data | full-time goals |
| `FTR` | cat | football-data | H/D/A — **settlement (90-min)** |
| `PSCH`,`PSCD`,`PSCA` | float | football-data closing | Pinnacle closing 1X2 — reference price **for seasons ≤ 2024/25 only** (degraded from 2025-07-23, §2.1) |
| `refC_H`,`refC_D`,`refC_A` | float | derived | **closing reference price, season-conditional**: `= PSC*` for season ≤ 2024/25, else `= AvgC*` (or `MaxC*`/`BFEC*` per §2.1) for season ≥ 2025/26. All derived fields below read `refC_*`, never `PSC*` directly. |
| `ref_book` | cat | derived | which book/consensus populated `refC_*` (`pinnacle_close` / `market_avg_close` / `market_max_close` / `betfair_ex_close`) — logs the cutover |
| `PSH`,`PSD`,`PSA` | float | football-data pre-match | optional opening proxy (≤ 2024/25) |
| `AHh`,`PAHH`,`PAHA` | float | football-data (≥2019/20) | native AH/DNB line |
| `MaxC*`,`AvgC*`,`BFEC*` | float | football-data | market max/avg/exchange closing — **sanity for ≤ 2024/25; promoted to the `refC_*` source for ≥ 2025/26** (per §2.1, `AvgC*`/`MaxC*` exclude the stale Pinnacle leg from 2025-07-23) |
| `overround` | float | derived | `1/refC_H + 1/refC_D + 1/refC_A` (NB: a `MaxC*`-sourced `refC_*` understates margin / may sum < 1 — flag, do not treat as fair) |
| `underdog_side` | cat | derived | `argmax(refC_H, refC_A)` |
| `o_dnb_underdog` | float | derived | `o = refC_side·(refC_D−1)/refC_D` (§1.2) |
| `data_vendor`, `snapshot_date` | str/date | meta | provenance |

### 7.2 Join keys and normalization

- **Primary join:** `(competition, season, date, home_team, away_team)`. Team names differ across vendors (football-data vs OddsPortal vs Kaggle) → maintain an explicit alias/crosswalk table; fuzzy-join only with a reviewed mapping, never silent.
- **Date alignment:** football-data uses local match date; reconcile against the Kaggle/RSSSF date to catch cross-midnight kickoffs.
- **Settlement field:** `FTR` (full-time, 90-minute result) is the DNB settlement basis — **extra time and penalties do not count** for a 90-minute DNB. For knockout matches verify the source's `FTR`/`FTHG`/`FTAG` are the 90-minute (regulation) figures, not after-ET; cross-check against RSSSF where a match went to ET.

---

## 8. Data-quality gates

Run before any backtest (the `validate-data` skill is the executor):

1. **Missingness.** Rows lacking the season-conditional closing reference `refC_*` (= `PSCH/PSCD/PSCA` for ≤ 2024/25; `AvgC*`/`MaxC*`/`BFEC*` for ≥ 2025/26, §2.1/§7) cannot be settled as synthetic DNB → flag, count, and decide drop-vs-impute per a stated MAR/MCAR justification (do not silently drop; quantify the dropped fraction and its odds distribution vs retained, since dropped rows may be the extreme-underdog tail). On the 2025/26 segment specifically, treat stale-but-present `PSC*` as missing for reference purposes (the degradation does not null the column).
2. **Duplicates.** De-dupe on the primary join key; investigate any `match_id` collision (rescheduled/abandoned matches).
3. **Overround sanity.** Pinnacle 1X2 overround typically `1.02–1.06` (2–6% margin) for top markets (≤ 2024/25 `PSC*` regime); flag any match with `overround < 1.00` (arbitrage artifact / stale leg) or `> 1.12` (likely a data error or thin market). The threshold band is a *screening* range to be tuned empirically against the realized overround distribution of the assembled table (report the empirical quantiles, do not hard-code 1.02–1.06 as truth). **For the 2025/26+ `AvgC*`/`MaxC*`/`BFEC*` reference the margin profile differs** — an average-consensus overround runs higher than a single sharp book and a max-odds column can sum to ≈ 1 or below — so fit a *separate* screening band per reference regime rather than applying the Pinnacle band post-cutover.
4. **Odds plausibility.** `refC_H, refC_D, refC_A ≥ 1.01` (i.e. `PSC*` ≤ 2024/25, else the non-Pinnacle reference); reciprocal-sum monotonicity. **The draw leg `refC_D` is gated by empirical quantiles, NOT a hard-coded band.** A fixed `[2.6, 5.5]` plausibility window is both a magic number and empirically wrong: against live Pinnacle closing draw odds (`PSCD`) for 2024/25, the upper bound 5.5 is breached by **6–15% of matches in every top division** — E0 57/380 = 15.0% above 5.5 (max 12.25, p95 = 7.10), D1 14.7% (max 18.0), SP1 11.3% (max 11.20, and a low of 2.53 that also clips the 2.6 floor), I1 6.3% (max 8.94) — and these high-draw-odds matches are exactly the lopsided, strong-favorite fixtures with the most extreme underdog price, i.e. the favorite-longshot region this strategy *targets*. A static band would systematically reject the strategy's own target subsample as "data errors" and bias estimation toward coin-flip matches. So flag only the extreme tails of the *realized* `refC_D` distribution **per division-season** (e.g. below the 0.1th / above the 99.9th percentile), carrying the same **report-empirical-quantiles-do-not-hard-code** caveat used for the gate-3 overround band, and re-fit the quantile cut-points separately per reference regime (Pinnacle `PSC*` ≤ 2024/25 vs `AvgC*`/`MaxC*`/`BFEC*` ≥ 2025/26, §2.1) since the consensus-vs-sharp-book margin shape shifts the draw-odds distribution. Draw odds for strong-favorite matches routinely exceed 5.5 and must not be screened out. Evidence: football-data.co.uk live CSVs `E0`/`SP1`/`I1`/`D1` 2024/25 `PSCD` distribution, direct per-division quantile count, accessed 2026-06-16 ([football-data.co.uk/data.php](https://www.football-data.co.uk/data.php), [notes.txt](https://www.football-data.co.uk/notes.txt)).
5. **Settlement consistency.** `FTR` must agree with `sign(FTHG − FTAG)`; cross-check against an independent results source (football-data.org or Kaggle) on a sample.
6. **Synthetic-vs-native DNB reconciliation.** Where both `AHh = 0` native AH odds and synthetic DNB exist, confirm `o_DNB,synthetic ≈ o_AH0` within margin — a direct validation of the §1.2 identity against vendor data.
7. **Look-ahead canary.** `pit-canary` before the first backtest run (§5.3).

All checks emit counts to `logs/` with a ReproLog envelope (git HEAD, pip-freeze SHA-256, dataset checksum, RNG seed) per the CLAUDE.md reproducibility mandate (`emit-repro-log` skill).

---

## Citations

1. football-data.co.uk. *Notes for Football Data* (column dictionary; closing-odds and Asian-Handicap definitions). https://www.football-data.co.uk/notes.txt (accessed 2026-06-16).
2. football-data.co.uk. *Historical Football Results and Betting Odds Data* (Main vs Extra leagues, coverage windows, file scheme). https://www.football-data.co.uk/data.php (accessed 2026-06-16). Carries the verbatim 2025-07-23 Pinnacle-reliability notice quoted in §2.1: *"Since 23/07/2025 Pinnacle's public API for odds delivery has become unreliable meaning their odds are systematically out of date relative to odds for other bookmakers, including both the pre-closing and closing odds. Consequently they should be used with caution when undertaking any betting analyses, and are no longer being included for the calculation of market average and maximum odds."*
3. Cain, M., Law, D., & Peel, D. (2000). The Favourite-Longshot Bias and Market Efficiency in UK Football Betting. *Scottish Journal of Political Economy*, 47(1), 25–36. DOI: [10.1111/1467-9485.00151](https://doi.org/10.1111/1467-9485.00151).
4. Forrest, D., Goddard, J., & Simmons, R. (2005). Odds-setters as forecasters: The case of English football. *International Journal of Forecasting*, 21(3), 551–564. DOI: [10.1016/j.ijforecast.2005.03.003](https://doi.org/10.1016/j.ijforecast.2005.03.003).
5. Constantinou, A. C., & Fenton, N. E. (2012). Solving the Problem of Inadequate Scoring Rules for Assessing Probabilistic Football Forecast Models. *Journal of Quantitative Analysis in Sports*, 8(1). DOI: [10.1515/1559-0410.1418](https://doi.org/10.1515/1559-0410.1418). (Forecast *evaluation* via the Rank Probability Score; **not** an odds-to-probability / de-vig method — retained for the RPS scoring-rule context only.)
6. Constantinou, A. C., Fenton, N. E., & Neil, M. (2012). pi-football: A Bayesian network model for forecasting Association Football match outcomes. *Knowledge-Based Systems*, 36, 322–339. DOI: [10.1016/j.knosys.2012.07.008](https://doi.org/10.1016/j.knosys.2012.07.008).
7. Hegarty, T., & Whelan, K. (2025). Estimating Expected Loss Rates in Betting Markets: Theory and Evidence. *Applied Economics*. DOI: [10.1080/00036846.2025.2507979](https://doi.org/10.1080/00036846.2025.2507979). (Average loss rates are *higher* than the overround implies because favourite-longshot bias loads margin onto longshots.)
8. Hegarty, T., & Whelan, K. (2025). Forecasting Soccer Matches With Betting Odds: A Tale of Two Markets. *International Journal of Forecasting*, 41(2), 803–820. DOI: [10.1016/j.ijforecast.2024.06.013](https://doi.org/10.1016/j.ijforecast.2024.06.013). (Asian-handicap market generates efficient forecasts where the 1X2 market shows favourite-longshot bias; Pinnacle data.)
9. Shin, H. S. (1993). Measuring the Incidence of Insider Trading in a Market for State-Contingent Claims. *The Economic Journal*, 103(420), 1141–1153. DOI: [10.2307/2234240](https://doi.org/10.2307/2234240). (Original Shin model: bias-aware odds-to-probability mapping.)
10. Štrumbelj, E. (2014). On determining probability forecasts from betting odds. *International Journal of Forecasting*, 30(4), 934–943. DOI: [10.1016/j.ijforecast.2014.02.008](https://doi.org/10.1016/j.ijforecast.2014.02.008). (Shin probabilities are the most accurate de-vig method vs. basic normalization and regression.)
11. Lo, A. W. (2002). The Statistics of Sharpe Ratios. *Financial Analysts Journal*, 58(4), 36–52. DOI: [10.2469/faj.v58.n4.2453](https://doi.org/10.2469/faj.v58.n4.2453).
12. Wikipedia. *Asian handicap* (zero/level handicap = stake refund on draw = Draw-No-Bet; quarter handicaps). https://en.wikipedia.org/wiki/Asian_handicap (accessed 2026-06-16).
13. FIFA. *How the FIFA World Cup 26 will work with 48 teams* (104 matches, 12 groups). https://www.fifa.com/en/articles/article-fifa-world-cup-2026-mexico-canada-usa-new-format-tournament-football-soccer (accessed 2026-06-16).
14. Encyclopaedia Britannica. *2026 FIFA World Cup* (format, match counts). https://www.britannica.com/event/2026-FIFA-World-Cup (accessed 2026-06-16).
15. Betfair Developer Program. *What data is provided by the Historical Data service?* (BASIC/ADVANCED/PRO tiers, 2016 coverage, formats). https://support.developer.betfair.com/hc/en-us/articles/360002407732-What-data-is-provided-by-the-Historical-Data-service (accessed 2026-06-16).
16. football-data.org. *Coverage* (12 free competitions incl. World Cup; rate limits). https://www.football-data.org/coverage (accessed 2026-06-16).
17. API-Football (api-sports.io). *Coverage* (1,200+ leagues; free-tier limits). https://www.api-football.com/coverage (accessed 2026-06-16).
18. Jürisoo, M. *International football results from 1872 to 2024* (results + neutral flag, no odds). Kaggle: https://www.kaggle.com/datasets/martj42/international-football-results-from-1872-to-2017 ; canonical GitHub source: https://github.com/martj42/international_results (`results.csv`). Both accessed 2026-06-16. The §6 international/World-Cup draw-rate figures (all-intl D = 22.7%, n = 49,421; competitive-intl D = 21.3%, n = 31,033; WC all-editions D = 22.7%, n = 980; WC 2002–2022 H/D/A = 43.5/22.9/33.6, n = 384) are a **direct H/D/A count** over rows with non-null scores from this file, not a vendor estimate. Note scores are recorded result (extra time included for older knockout editions, penalties excluded), so they bound the 90-minute draw rate from below.

*Methodological standards referenced from the project rule set (not external citations): time-series integrity, walk-forward CV, bootstrap/asymptotic Sharpe CI, multiple-testing control — [rules/quant-project.md](../../../.claude/rules/quant-project.md). Post-hoc power prohibition — Hoenig, J. M., & Heisey, D. M. (2001), The Abuse of Power, The American Statistician 55(1):19–24, DOI [10.1198/000313001300339897](https://doi.org/10.1198/000313001300339897).*

---

## Open questions and assumptions to validate

1. **OddsPortal World Cup depth and legality.** Confirm clean 1X2 closing odds actually exist back to 2002 (not just 2010+), and confirm the scrape is ToS-permissible or substitute a licensed vendor (The Odds API historical). Decide whether 1998 is recoverable to push n from 384 to 448.
2. **Closing reference-column population rate (both regimes).** Verify by direct download what fraction of Main-League rows carry non-null `PSCH/PSCD/PSCA` per season — the "from 2000/01" odds statement covers *some* book, not necessarily Pinnacle closing; community sources put reliable `PSC*` from the late-2010s. Empirically establish the first season with ≥95% `PSC*` coverage rather than assuming it. **Extend to the post-cutover regime:** confirm `AvgC*`/`MaxC*`/`BFEC*` coverage on 2025/26+ (the §2.1 non-Pinnacle reference), and verify that the 2025-07-23 Pinnacle degradation is actually reflected as stale/missing `PSC*` in the downloaded 2025/26 files, not silently carried.
3. **Native AH=0 availability.** `AHh` only exists from 2019/20; for earlier seasons DNB must be synthetic (§1.2). Quantify how many matches permit the synthetic-vs-native reconciliation check (gate 6).
4. **90-minute settlement in knockout matches.** Confirm every vendor's `FTR/FTHG/FTAG` for knockout games is regulation-time, not after-ET, before trusting the DNB push count.
5. **Draw-rate recomputation (partly done; finish on regulation-time `FTR`).** The §6 international/World-Cup figures are now direct counts on the martj42 set (all-intl 22.7%, competitive 21.3%, WC 2002–2022 22.9%), which already shows the international rate is *comparable-to-slightly-lower* than top-club, not higher. Two items remain: (a) reconstruct a 90-minute (regulation) `FTR` for knockout matches so the recorded draw rate is not deflated by extra time, and recompute the group-vs-knockout split on it; (b) recompute EPL/UCL on the assembled football-data table rather than the stated 882/3799, 480/2245 counts. Then test whether any residual difference is large enough to affect domestic→WC transfer (pooling risk §4.4-risk-1, now demoted to second-order).
6. **Underdog definition under near-coin-flips.** Fix the rule for `|refC_H − refC_A|` (season-conditional reference, §5/§7) below a threshold — drop, or assign by tiny odds difference — and justify the threshold empirically (sensitivity sweep), per the no-magic-number mandate.
7. **De-vig method choice.** Decide proportional vs Shin bias-aware normalization ([Štrumbelj 2014, DOI 10.1016/j.ijforecast.2014.02.008](https://doi.org/10.1016/j.ijforecast.2014.02.008); [Shin 1993, DOI 10.2307/2234240](https://doi.org/10.2307/2234240)) for the underdog assignment and edge estimate; the choice interacts with the favorite-longshot region where the strategy lives.
8. **Regime/non-stationarity.** Validate that pooling 2012/13→2024/25 domestic seasons does not mix incompatible margin regimes (Forrest-Goddard-Simmons efficiency drift); prefer walk-forward windows over a single static pool.
