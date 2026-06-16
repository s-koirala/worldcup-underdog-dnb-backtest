# Edge Hypothesis: Favourite-Longshot Bias, Market Efficiency, and World Cup Empirics for an Underdog Draw-No-Bet Strategy

> Research dimension: the *prior* on whether backing the underdog via draw-no-bet (DNB) at the FIFA men's World Cup carries a plausibly non-zero, net-of-cost edge. This document does not run the backtest; it establishes (i) what the favourite-longshot-bias (FLB) literature predicts for the *sign* of underdog returns in 1X2 vs Asian-Handicap/DNB markets, (ii) the efficiency benchmark (Pinnacle closing odds) against which any edge must be measured, (iii) World-Cup-specific deviations from domestic-league base rates, and (iv) an honest assessment feeding the power analysis: is the hoped-for effect even directionally plausible?

## Scope

- Markets: 1X2 (home/draw/away decimal odds) and Asian Handicap 0.0 = "Draw-No-Bet" (DNB). DNB on the away/underdog side is the strategy under test.
- Universe: domestic European leagues (football-data.co.uk / Buchdahl, Pinnacle closing odds) as the estimation set; World Cup finals 2002-2022 (~384 matches with clean 1X2 odds) as the held-out subsample.
- Settlement: DNB / AH 0.0 settles on the **90-minute** result; a 90-minute draw refunds the stake. Extra time and penalties are irrelevant to settlement — material for the World Cup knockout phase (Section 4).
- Standard of evidence: every quantitative claim is sourced to peer-reviewed literature, the cited working papers, or a primary tabulation. Magnitudes are reproduced from the source tables, not paraphrased.

The single most decision-relevant source is **Hegarty & Whelan, "Forecasting Soccer Matches with Betting Odds: A Tale of Two Markets"** — it measures FLB *separately* in the 1X2 and Asian-Handicap markets on the **exact data vendor this project will use** (football-data.co.uk, average closing odds, 84,230 matches, 22 European leagues, 2011/12-2021/22). Its findings constrain the prior more tightly than any World-Cup-only study can, given the small WC sample.

---

## 1. The favourite-longshot bias: definition, canonical magnitude, mechanism

### 1.1 Definition and the foundational racetrack result

The FLB is the empirical regularity that market odds are biased estimates of win probability: **longshots are overbet (returns too low) and favourites are underbet (returns relatively high)**. First documented by Griffith (1949), it is among the most replicated anomalies in empirical economics.

**Snowberg & Wolfers (2010, JPE)** provide the canonical modern measurement on 6,403,712 US horse starts (1992-2001) plus Australian and UK samples:

| Bet type | Rate of return |
|---|---|
| Favourite (every race) | -5.5% |
| Random horse | ≈ -23% (= the track take) |
| Longshots at 100/1 or longer | ≈ -61% |
| Horses at 4/1-9/1 | ≈ -18% (approx. constant over the range) |

The monotone decline of return in odds *is* the bias. Their methodological contribution is to discriminate **risk-love** (neoclassical, Friedman-Savage convex utility) from **misperceptions of probability** (prospect-theory probability weighting, Kahneman-Tversky 1979) using compound bets (exacta/quinella/trifecta). The two are observationally equivalent in win-bet data alone; using the wider choice set they conclude **misperceptions dominate**. They also test and **reject** two folk claims: (i) positive returns on extreme favourites (Thaler-Ziemba limits-to-arbitrage conjecture — not present in their data; consistent with Levitt 2004 that anomalous *pricing* need not imply *profit*); (ii) end-of-day loss-aversion effects (point estimates differ but not significantly).

**Mechanistic takeaway for this project.** If misperceptions (probability overweighting of small p) drive FLB, the bias attaches to the *bettor population's perception*, so it should be strongest where the bettor base is recreational and weakest where it is professional. This prediction is exactly what differs between the 1X2 market (retail) and the Asian-Handicap market (syndicate/sharp) — see Section 3.

### 1.2 FLB in football 1X2 markets

**Cain, Law & Peel (2000, Scottish Journal of Political Economy)** establish that UK fixed-odds football exhibits "the same favourite-longshot bias" as horse racing, in both result (1X2) and correct-score markets, on 2,855 matches. They identify ostensibly profitable trading rules (notably betting low scores / favourites). This is the original football-1X2 FLB reference. Direction: **underdog/longshot bets lose more.**

**Forrest, Goddard & Simmons (2005, International Journal of Forecasting)** compare bookmaker-implied probabilities against a data-rich statistical model (Brier-score evaluation) over English football. Early in their sample the statistical model beats the odds; by the end the **odds beat the model**. Implication: 1X2 odds-setters became *better forecasters* over time even while a pricing bias persists — efficiency of the *forecast* and absence of an *exploitable edge* are distinct properties.

**Angelini & De Angelis (2019, citation 16)** and **Štrumbelj (2014)** (cited by Hegarty-Whelan as the modern soccer-1X2 FLB references) confirm the same direction in large pan-European samples: normalized implied probabilities are **too high for longshots, too low for favourites**.

### 1.3 Worked numeric: what FLB does to underdog 1X2 returns

The 1X2 evidence (Section 3.2 numbers) puts the longshot 90-minute *win-bet* loss rate at roughly 9-10% versus 6% for favourites. A naive underdog 1X2 win bet therefore starts from a return prior of about **-9% to -10%** before any DNB construction. DNB changes the variance and the conditional payoff structure but, as Section 5 shows, does not by itself manufacture positive EV unless the underlying bias is *reverse* in the DNB market — which is the empirical question.

---

## 2. Market efficiency, the sharp benchmark, and closing-line value

### 2.1 Bookmaker odds as probability forecasts; margin removal

**Štrumbelj (2014, *Int. J. Forecasting* 30(4):934-943, DOI [10.1016/j.ijforecast.2014.02.008](https://doi.org/10.1016/j.ijforecast.2014.02.008))** evaluates methods for converting decimal odds into probabilities across 37 competitions and 5 team sports. Finding: **Shin's model** — the insider-trading state-contingent-claims pricing model introduced in **Shin (1992)** (which derives the favourite-longshot bias as an equilibrium pricing outcome) and operationalised for margin removal via the inversion in **Shin (1993)** / Jullien-Salanié (1994) — yields **more accurate** probability forecasts than (a) basic normalization (divide inverse-odds by the overround) or (b) regression. Basic normalization is biased *precisely in the FLB direction* — it understates favourite probability and overstates longshot probability. This is the methodological hinge: **how you strip margin determines whether you "see" the FLB**, and naive normalization bakes the bias into your fair-odds estimate.

> Practical rule for the backtest: do **not** use basic-normalization "fair" probabilities to label favourite vs underdog if the goal is an unbiased EV estimate; use Shin or the AH-implied probability (Section 3). For *defining* the underdog by raw quoted price (higher decimal odds), normalization is irrelevant — the ranking is preserved.

### 2.2 The overround does NOT equal the average bettor loss under FLB

**Hegarty & Whelan, "Estimating Expected Loss Rates in Betting Markets: Theory and Evidence" (2025 revised draft, UCD)** prove a result directly relevant to EV accounting:

- If the market is "strongly efficient" (Thaler-Ziemba 1988: equal expected return across all outcomes of a contest), then `1 − 1/overround` correctly gives the expected loss per bet and normalized probabilities are correct.
- **But if bookmakers set higher margins on lower-probability bets (the FLB), the equally-weighted average loss across the available bets is *strictly higher* than the overround implies.**

Reproduced from their Table 1 (soccer, N = 151,683 matches):

| | Loss rate implied by overround | Realized average loss across all bets |
|---|---|---|
| All seasons | 7.1% | 8.7% (≈ 22% higher) |
| 2024/25 | 5.8% | 7.7% |

Tennis (Table 2, N = 131,283): 5.4% implied vs 7.5% realized (≈ 40% higher; larger because 2 outcomes → wider favourite-longshot probability gap). Crucially, the gap holds **even at Pinnacle** ("realized loss rates at Pinnacle are significantly larger than predicted"), i.e. *the sharpest 1X2 book still prices an FLB.* Their footnote 5 flags the exception that motivates this entire project: **this FLB pattern does *not* apply to Asian-Handicap soccer** (Hegarty & Whelan 2025 / the "Tale of Two Markets" paper, Section 3).

**Consequence for the EV prior.** A World-Cup 1X2 overround of ~5-7% (Section 4.5) *understates* the true equally-weighted loss; the underdog bet, sitting on the high-margin side, loses **more** than the headline overround suggests.

### 2.3 Closing-line value (CLV) as the efficiency yardstick

The professional-practice consensus (Pinnacle, and the trading literature it cites) treats the **closing line at a sharp book as the best available estimate of true probability**; the degree to which your *entry* price beats the *closing* price (CLV) is the leading indicator of long-run edge. Two empirical anchors:

- Pinnacle closing odds are the de-facto sharp benchmark because of high limits, low margin, and a "winners-welcome" policy that lets sharp money move the line into it (this is the same selection mechanism the Tale-of-Two-Markets authors invoke to explain AH efficiency). The Overround paper (citation 6) confirms this directly: across its 10 bookmakers, "**loss rates at Pinnacle … are significantly lower than for the other bookmakers**" (verified verbatim). It separately finds that "**realized loss rates at Pinnacle are significantly larger than predicted rates**" — i.e. even the sharpest 1X2 book prices *some* FLB — but its *level* is below the market-average bookmaker.
- football-data.co.uk supplies **Pinnacle closing 1X2 and AH** columns (the `PSC*`/`PCAHH`/`PCAHA` fields), so the backtest can both (a) use Pinnacle closing odds as the efficient benchmark and (b) measure any opening→closing drift on the underdog side.

> **Benchmark/source distinction (carried through Sections 3-5).** The cited Hegarty-Whelan AH and 1X2 *magnitudes* (1X2 portfolio 7.8%, AH portfolio 3.6%, integer-handicap 3.24%, weak 3.28%, etc.) are computed on football-data.co.uk's **average closing odds across the surveyed bookmakers**, *not* on the Pinnacle-specific columns (verified verbatim, Section 3 / citation 4). Because Pinnacle's loss level is below the market average (preceding bullet), these market-average magnitudes are an **upper bound** on the Pinnacle-specific loss baseline the backtest will actually face. They must **not** be presented as Pinnacle benchmarks; the Pinnacle-specific AH-0.0 loss baseline is to be recomputed on the football-data.co.uk `PCAHH`/`PCAHA` (Pinnacle closing AH) columns before any EV-prior level is asserted (open question 12).

**Implication.** If the underdog-DNB strategy has an edge, it should manifest as **positive CLV** (entering at prices that the closing line subsequently confirms as too long). Absent CLV, any positive backtest P&L is almost certainly variance, not edge. CLV should be a *primary diagnostic* in the backtest, not an afterthought. Note that "beating the close" is itself only a *necessary* condition: Constantinou & Fenton (2013) document arbitrage and odds-bias profits in the *traditional* market that are largely competed away once realistic limits/bans on the sharp side are imposed.

---

## 3. The decisive evidence: FLB in 1X2 vs Asian-Handicap (= DNB family)

DNB is Asian Handicap 0.0. The most directly relevant primary source is **Hegarty & Whelan, "Forecasting soccer matches with betting odds: A tale of two markets" (*Int. J. Forecasting* 41(2):803-820, 2025; working paper MPRA 116925; citation 4)**, because it measures FLB in *both* markets on the *same matches* using the *same data vendor and odds convention* this project will use (average **closing** odds, football-data.co.uk / Buchdahl, 84,230 matches, 22 European leagues, 2011/12-2021/22; AH side N = 168,460 directional bets).

### 3.1 Headline result

> "The implied probabilities for match outcomes from Asian Handicap odds … do **not** exhibit favourite-longshot bias and … are **unbiased** estimates of the win rate for predicted outcomes. … average loss rates for bettors in this market are **lower** than in the home/away/draw market and can be predicted accurately from betting odds under the assumption of market efficiency."

### 3.2 Reproduced magnitudes

**1X2 market (FLB present).** Over a matched probability range, the longshot decile (P̂ ≈ 0.26) loses **9.4%**; the favourite decile (P̂ ≈ 0.48) loses **6.1%** → longshot losses **>50% higher** than favourite losses. Full-portfolio 1X2 loss ≈ **7.8%**.

**Asian-Handicap market (no FLB; weak *reverse* FLB).** Over the same probability range, longshot AH bets lose **3.5%** and favourite AH bets lose **4.1%** — i.e. **the underdog side loses *less***. Their payout regression (Table 5, N = 168,460) gives all decile coefficients **negative** relative to the bottom (longshot) decile, statistically significant only in the top two deciles → "weak evidence for a **reverse** of the favourite-longshot bias … for Asian Handicap bets."

**Ex ante vs ex post (Table 7).** AH realized portfolio loss = **3.6%**, statistically indistinguishable from the efficiency-implied 3.61%. Decomposed (cells and sample sizes reproduced verbatim from MPRA 116925 Table 7):

| AH bet subset | Loss rate | N |
|---|---|---|
| All home + away | 3.63% | 168,460 |
| All bets on the **strong/favourite** team* | **4.17%** | 69,910 |
| All bets on the **weak/underdog** team* | **3.28%** | 69,910 |
| All bets on home | 4.11% | 84,230 |
| All bets on away | 3.16% | 84,230 |

`*` carries the source's Table 7 footnote — verbatim: **"Zero handicap is not considered for strong and weak bets."**

The **underdog (weak-team) side loses ~0.9 pp *less*** than the favourite side (4.17% − 3.28%), and the **away side loses ~0.95 pp less** than the home side (4.11% − 3.16%).

> **CRITICAL INSTRUMENT-MISMATCH CAVEAT — the weak/strong gradient is computed on a sample that *excludes the exact instrument this project trades.*** The strategy under test is Asian Handicap **0.0** (DNB). But the source's Table 7 strong/weak cells (Strong* 4.17%, Weak* 3.28%, both N = 69,910) carry the footnote "*Zero handicap is not considered for strong and weak bets*" (verified verbatim against MPRA 116925, Table 7). The strong/weak split is undefined at a zero handicap — when the handicap is 0.0 neither side is "the strong team" by the handicap, so the authors drop AH-0.0 matches from that decomposition (note the N: 69,910 per side, *below* the 84,230 per side of the home/away rows, which retain the zero-handicap matches and do **not** carry the asterisk). Consequently the **3.28%/4.17% weak/strong gradient does NOT characterize the AH-0.0/DNB line at all** — it is measured on the non-zero-handicap subsample. Treating 3.28% as "the underdog-DNB best case" (as earlier drafts did, and as Sections 3.5/5.3/7 must now avoid) imports a number from a sample that explicitly removes the traded instrument. **The DNB-specific evidence is a different object** — the handicap-type loss gradient of Section 3.3 (RBF 2024), where the *full-refund-capable* line (which includes AH-0.0) is the low-loss end. Its magnitude is quantified separately there (integer-handicap loss ≈ 3.24%) and is the correct re-anchor for the DNB prior; the 3.28% weak-team figure is retained below only as *cross-sectional evidence that the underdog side is the cheaper side within the AH market*, not as the DNB loss level.

> **The two gradients are also *not* independent evidence — they are largely the same domestic phenomenon measured twice.** In domestic league data the away team is the *priced underdog* in the large majority of matches (home advantage makes the home side the favourite by default), so the weak/strong split and the away/home split overlap heavily; treating them as mutually corroborating overstates the evidence. Moreover the away discount is plausibly a **home-advantage-mispricing artifact**: the market under- or over-adjusts for the ~0.4-goal home edge, and that channel is *specific to venued matches*. By the Section 4.2 neutral-venue-compression argument, **the away/home gradient cannot transfer to the (mostly neutral) World Cup** — there is no "away" team at a neutral WC site. **Only the price-based weak/strong gradient (~0.9 pp) is candidate-transferable** to neutral WC venues, and even that (i) is measured on the zero-handicap-excluded subsample per the caveat above, and (ii) is expected to *shrink* under neutral-venue probability compression (Section 4.2, open question 3). The away/home gradient is excluded from the WC transfer prior.

### 3.3 Karl Whelan & Hegarty (2024, *Review of Behavioral Finance* 16(5):904-924, DOI [10.1108/RBF-11-2023-0314](https://doi.org/10.1108/RBF-11-2023-0314))

"Returns on complex bets: evidence from Asian Handicap betting on soccer." Finding: AH loss rates vary **predictably by handicap type** — bettors lose **more** on bets where a refund is *not* possible (half-goal lines that cannot push) and **less** where a half- or full-refund is possible. DNB (AH 0.0) is precisely the "full-refund-on-draw" line — an **integer handicap** that refunds when the result exactly matches the handicap — i.e. the **low-loss** end of this spectrum. They attribute the pattern to gamblers **mis-calculating expected loss on complex (refund-bearing) bets**, not to risk preference — a *behavioural-pricing* edge that, if it survives at the World Cup, would favour the DNB construction specifically.

**This is the correct DNB-specific anchor — quantified.** Because the Section 3.2 weak/strong gradient *excludes* the zero handicap (its footnote), the loss level that actually characterizes the AH-0.0/DNB family is this handicap-type table, not the 3.28% weak-team cell. Reproduced verbatim from RBF 2024 Table 2 (same vendor and convention — *average closing odds across the bookmakers surveyed by football-data.co.uk*, 84,230 matches; "average loss rates from placing an equal amount on all bets, by Asian Handicap type"):

| Handicap type | **Integer** (full-refund possible — includes AH 0.0) | Ends in .25 (half-refund) | Ends in .5 (**no refund**) | Ends in .75 (half-refund) |
|---|---|---|---|---|
| Mean loss rate | **3.24%** | 3.61% | 4.16% | 3.57% |
| N (matches) | 23,730 | 29,250 | 20,762 | 10,488 |

The **integer-handicap loss is 3.24%, the lowest of the four types**; the no-refund half-goal line loses 4.16%, and Table 3 shows the integer-vs-half-goal difference (−0.93 pp) is significant at p < 0.0001. **This 3.24% — not the 3.28% weak-team cell — is the DNB-family loss prior** (full-refund-capable, integer-handicap), and it is the magnitude carried into Sections 3.5/5/7 as the realized-quoted-AH best case for the DNB line. Two caveats attach: (i) the integer bucket pools *all* integer handicaps (0, ±1, ±2, …), not AH-0.0 alone — it is the right *family* object but not the AH-0.0 cell in isolation (re-derive the AH-0.0-only loss from the held-out data, open question 11); (ii) like every magnitude in the cited evidence, 3.24% is a **market-average** figure, not a Pinnacle-specific one (Section 2.3 / 3.4).

### 3.4 Independent corroboration

Whelan's earlier note and the broader AH literature ("weak evidence for a reverse of the favourite-longshot bias operating for Asian Handicap bets"; "Asian Handicap odds … do not exhibit favourite-longshot bias") agree. The mechanism (Section 1.1) is consistent: the AH/DNB market is dominated by **professional syndicates trading at low-margin sharp books such as Pinnacle**, whose perceptions are well-calibrated, so the misperception-driven FLB is absent and the market is forecast-efficient.

> **Do not read the AH magnitudes as Pinnacle figures.** The *mechanism* (sharp/syndicate participation) explains why AH is efficient, and Pinnacle is the canonical exemplar of that participation. But the **measured AH loss magnitudes cited above (3.6% portfolio, 3.24% integer-handicap, 3.28% weak) are market-average closing odds across the surveyed books, not Pinnacle's own AH line** (citation 4 data description, verified verbatim). Pinnacle's specific AH loss baseline is lower still (Section 2.3). The efficiency claim transfers to the mechanism; the loss *level* must be recomputed on the Pinnacle AH columns (open question 12).

### 3.5 Synthesis of the cross-market prior

All AH/DNB magnitudes below are **market-average closing odds** (football-data.co.uk surveyed-book average), *not* Pinnacle-specific; the "sharp" label denotes the market's participant structure (Section 3.4), not the data vendor's price source. Pinnacle's own AH loss level is lower (Section 2.3).

| Property | 1X2 (retail, mkt-avg) | Asian Handicap / DNB (sharp-dominated, mkt-avg) |
|---|---|---|
| FLB direction | **Standard** (underdog loses more) | **None / weak reverse** (underdog loses slightly less) |
| Probability calibration | Biased (need Shin) | Unbiased |
| Portfolio loss rate | ~7.8% | ~3.6% |
| **DNB-family (integer/full-refund) loss** | n/a | **~3.24%** (RBF 2024 Table 2; the AH-0.0-relevant cell) |
| Cross-sectional underdog-vs-favourite (zero-handicap *excluded*) | higher | **lower** (weak 3.28% vs strong 4.17%) |
| Overround predicts loss? | No (understates) | Yes |

**This is the crux.** The naive intuition "FLB ⇒ never back the underdog" is a **1X2 result**. In the DNB family the bias is absent-to-reverse and the *underdog side is the cheaper side*. The hoped-for effect is therefore **directionally plausible** — but with caveats that shrink the transportable evidence:

(i) **The DNB loss level is the ~3.24% integer/full-refund figure (RBF 2024), not the 3.28% weak-team figure.** The 3.28%/4.17% weak/strong gradient is computed on a sample that *excludes the zero handicap* (Table 7 footnote, Section 3.2), i.e. it excludes the exact AH-0.0 instrument the backtest trades; it is retained here only as cross-sectional evidence that the underdog side is the cheaper side *within* the AH market, not as the DNB loss level.

(ii) The favourable cross-sectional price-based gradient (~0.9 pp) is *smaller than the DNB margin/loss itself* (~3.2-4.2%), so the strategy is still **net-negative EV in expectation** on this domestic evidence.

(iii) Of the two domestic gradients, **only the weak/strong (price-based) one is candidate-transferable to neutral WC venues** — the away/home gradient is venue-specific (a home-advantage-mispricing artifact) and is *not* independent corroboration (away ≈ underdog domestically; Section 3.2).

(iv) **Every magnitude here is market-average, hence an upper bound on the Pinnacle-specific loss** the backtest will face (Section 2.3); do not use these as the Pinnacle EV-prior level.

The realistic best case is "lose less," not "win," unless a World-Cup-specific dislocation adds enough edge to cross zero (Section 4-5).

---

## 4. World Cup / international-football specifics

The estimation set is domestic European league football. The held-out target is the World Cup. The following deviations must be carried into the backtest as *covariate shifts* — they are the reasons the domestic prior may not transfer.

### 4.1 Draw rates

All-time World Cup finals 1930-2022 (RSSSF tabulation): **964 matches, 2,720 goals → 2.82 goals/match**, of which **214 are draws → 22.2%** (early tournaments inflate the goal rate; the modern rate is lower — see below).

> **Source-arithmetic note (corrected).** The RSSSF all-time table reports its won/drawn/lost and match counts on a **two-sided (team-match) basis**: 750 wins / 428 draws / 750 losses across 1,928 team-match rows. Because every match contributes *two* rows (one per team), the match-level totals are exactly half: **1,928 / 2 = 964 matches** and **428 / 2 = 214 drawn matches**. The win=loss equality (750 = 750) confirms the double-count. The draw *rate* is invariant to the convention — 214/964 = 428/1,928 = **22.2%** — and the goals/match is **2,720 / 964 = 2.82** (the goal total 2,720 is already match-level, not doubled). The earlier presentation ("428 draws / 1,928 matches" and "2,720/1,928 = ~2.8") mixed a team-match denominator (1,928) with a match-level goal numerator (2,720), which made the goals/match line arithmetically false (2,720/1,928 = 1.41). All three figures now reconcile to the 964-match base.

This 90-minute draw rate is **the refund probability `q` for DNB** (feeding the variance/power calc, Sections 5.2/5.4 and 7) and is somewhat below domestic-league draw rates (~25-28% in many European leagues), so the DNB-refund mechanics transfer reasonably but with a slightly lower push mass at the WC. **The decision-relevant `q` is the modern (2002-2022 held-out) 90-minute draw rate, not the all-time 22.2%; it is re-derived directly from the held-out match data in the backtest (open question 10).** Per-tournament reporting (e.g. 8/48 = 16.7% drawn in the 2018 *group* phase, footballhistory.org) indicates the modern group-stage rate runs below the all-time mark; do not hard-code 22.2% as `q` — it is an all-time anchor, and the held-out estimate governs the power calculation.

Phase split (reported figures, to be re-derived from match data in the backtest): group-stage matches draw ≈ 22% at 90 minutes; the *final round* of the group stage shows a *lower* draw rate (~18%) — consistent with motivation/dead-rubber effects (Section 4.4). **Knockout matches have zero recorded "draws" only because ties are resolved by ET/penalties — but DNB settles at 90 minutes, so a knockout match level after 90' is a DNB *refund*, not a loss.** This is a settlement subtlety the backtest must handle explicitly: ~the same ~22-27% of knockout matches are level at 90' and must be coded as refunds, not as away-team losses.

### 4.2 Neutral venue and the absence of ordinary home advantage

World Cup matches (excluding the host) are at **neutral venues**, so the ~0.4-goal domestic home-field edge (home advantage reduces goals conceded ≈0.2 and adds ≈0.1 scored per the cited tournament-football work) is **largely absent**. Consequences:

- The "home/away" labelling in domestic data is meaningless at neutral WC sites; the **underdog must be defined purely by price** (higher decimal odds / lower implied p), per the project's KEY IDENTITY, not by home/away.
- Removing home advantage **compresses the favourite-underdog probability gap** relative to domestic data, which *mechanically shrinks the room for any FLB* (the Hegarty-Whelan logic: equal-probability contests leave "no room for the bookmaker to apply a favourite-longshot bias"). This *reduces* the expected favourable underdog gradient at the World Cup versus domestic leagues.

### 4.3 Host effect

**Kalwij (2024), "Home advantage for tournament victory: empirical evidence from FIFA World Cups and continental championships"** (*J. Quantitative Analysis in Sports*, DOI [10.1515/jqas-2024-0056](https://doi.org/10.1515/jqas-2024-0056); citation 9) documents a **measurable host-nation advantage** in tournament outcomes (the host is one of the few teams *not* at a neutral venue): ≈ 22 pp for a home team of average Elo strength, scaling with team strength. For 2026 there are **three co-hosts (USA/Canada/Mexico)**, diluting and complicating the classic single-host effect. For the 2002-2022 held-out set, host matches are a small, identifiable subset; treat host games as a **separate stratum** (the underdog vs a host is *not* facing a neutral-venue opponent).

### 4.4 Dead rubbers / motivation

Final-round group matches include fixtures where one or both teams are already qualified or eliminated. Motivation asymmetries (a) raise variance, (b) can systematically help the "underdog" by price when the favourite rests players or plays for a draw, and (c) plausibly explain the *lower* final-round draw rate. This is a **potential source of genuine, World-Cup-specific edge** for an underdog strategy — and a confounder. Tag matches by qualification state at kickoff (point-in-time, no look-ahead per time-series-integrity rules) and analyze as a stratum.

### 4.5 Margin / overround at the World Cup

World Cup match 1X2 markets at sharp books price at **~2-4% overround (Pinnacle)** and **~5-8% (retail, e.g. Bet365)**; two-way (DNB/AH) margins are typically lower than three-way 1X2 (fewer outcomes, sharp-dominated). Take the **DNB margin prior at ~2-4%** (consistent with the AH 3.6% domestic portfolio loss). Per Section 2.2, the *true* equally-weighted loss exceeds the headline overround whenever FLB is present — but in the AH/DNB market FLB is ~absent, so for DNB the overround is approximately the honest loss estimate. **This is favourable for DNB relative to 1X2:** the cost is both lower *and* more accurately knowable.

### 4.6 ET / penalties vs 90-minute settlement

DNB = AH 0.0 settles on the **90-minute** result; ET and penalties **do not affect the bet**. World-Cup-specific facts: ≈38% of knockout matches (1998-2022) go to extra time and ≈22% to penalties; 3/22 finals were decided on penalties. **None of this touches DNB settlement** — but it means the *intuition* "underdogs hang on in knockouts" must be tested at the 90-minute mark, not the final result. A backtest that mistakenly settles DNB on the post-ET result would be a **look-ahead/settlement bug**; flag it for the point-in-time canary.

---

## 5. The DNB construction, variance, and the EV prior — worked numerically

### 5.1 Synthetic DNB identity (from the project brief, re-derived)

For the away/underdog side, given 1X2 decimal odds (H, D, A), construct DNB by staking the unit so that a draw is fully refunded:

- Stake `1/D` on the Draw (returns the 1/D × D = 1 unit if draw → net 0 on the unit after the away-win portion is lost? — re-derive cleanly below).

Clean derivation. Let total stake = 1, split `s_D` on Draw at odds D and `s_A` on Away at odds A, with `s_D + s_A = 1`. Require that a Draw returns exactly the original stake (refund): `s_D · D = 1 ⇒ s_D = 1/D`, hence `s_A = 1 − 1/D = (D−1)/D`. On an Away win the payout is `s_A · A = A(D−1)/D`. Therefore the **effective DNB decimal odds** are

```
O_DNB = A · (D − 1) / D
```

exactly as stated in the KEY IDENTITY. On a Home win both legs lose (stake forfeit). DNB outcomes: Away win → O_DNB; Draw → 1.0 (refund); Home win → 0.

### 5.2 Variance identity and its use in the power calc

For a fair win bet at decimal odds `o` with true win probability `p = 1/o`, the per-unit profit X has E[X]=0 and:

- `Var(X) = E[X²] − 0 = p·(o−1)² + (1−p)·(−1)² = (1/o)(o−1)² + (1−1/o) = (o−1)²/o + (o−1)/o = (o−1)[(o−1)+1]/o = (o−1)·o/o = o − 1.`

So **per-bet variance = o − 1** holds *for a fair straight win bet at odds o* (confirming the brief). **It is the wrong closed form for the DNB bet** — `o − 1` is an *upper bound* on the DNB variance, because the DNB push (a 90-minute draw, probability `q = p_D`) contributes a *zero* deviation where the straight win bet would book a `−1`. The correct DNB variance is the **three-point closed form** (calc doc §6.1), with `b = O_DNB − 1`, `p_W` the underdog-win probability, `p_D` the draw (push) probability, `p_fav = 1 − p_W − p_D`, and `μ = p_W·O_DNB − (1 − p_D)`:

> `Var_DNB = p_W·b² + p_fav − μ²`   (unconditional, per stake placed).

For the live-conditional view (condition on no draw), use the two-outcome variance at `O_DNB` with `q_W = p_W/(1 − p_D)`: `Var_live = q_W·b² + (1 − q_W) − μ_live²`, `μ_live = q_W·O_DNB − 1`.

Worked numbers for the §5.3 example (`O_DNB = 4.053`, basic-de-vig probs `p_W = 0.176, p_D = 0.255, p_fav = 0.569`):

| Quantity | Value | SD |
|---|---|---|
| Three-point **unconditional** DNB variance `Var_DNB` | 2.21 | **1.49** |
| Live-conditional two-outcome variance at `O_DNB` | 2.96 | 1.72 |
| Naive `√(O_DNB − 1)` (straight-win-bet identity) | — | 1.75 |

The naive `√(O_DNB − 1) = 1.75` **overstates** the true unconditional DNB SD (1.49) by **~18%** (matching the calc doc §8.2, where DNB Var 1.59 vs win-bet 2.25). Overstating SD *understates* power, so it is conservative — it does not flip the "low power" conclusion — but it is the wrong identity. **`q` does not enter as a simple multiplier on a per-bet SD: it is embedded in `p_D` (= push mass) inside the three-point form above.** When computing the SD of the *mean* DNB return over `n` matches under i.i.d. (or HAC-adjusted) assumptions, use `SD(mean) = √(Var_DNB / n)` with `Var_DNB` from the three-point form (the unconditional convention, which counts refunds as 0-return draws in `n`), *not* `√((O_DNB − 1)/n)`. For the **power analysis** (separate document), the inputs are: the three-point `Var_DNB` (≈ 2.2 / SD ≈ 1.49 in this example), the refund fraction `q = p_D` (the held-out 2002-2022 estimate, §4.1 — not the all-time 0.22), and the effect size below; flag `√(O_DNB − 1)` as an upper bound only.

### 5.3 Worked EV example (typical WC underdog)

Take a plausible WC group-stage mismatch with sharp 1X2 closing odds H = 1.70, D = 3.80, A = 5.50 (favourite ≈ 59% raw, underdog ≈ 18% raw, draw ≈ 26% raw; overround = 1/1.70+1/3.80+1/5.50 = 0.588+0.263+0.182 = 1.033 ⇒ **3.3% overround**).

- Effective DNB-away odds: `O_DNB = 5.50 · (3.80−1)/3.80 = 5.50 · 2.80/3.80 = 5.50 · 0.7368 = 4.053`.

**De-vig the synthetic DNB price two ways; the unbiased estimate is Shin (per §2.1, this document's designated-primary method).** Both de-vig the *three-way* 1X2 book and form the conditional no-draw away-win probability `q_A* = p_A/(p_A+p_H)` (the calc doc §8.2 establishes Shin must not be run on the draw-dropped under-round residual):

| De-vig | `p_H` | `p_D` | `p_A` | `q_A*` (no-draw) | EV(live) `= q_A*·O_DNB − 1` | EV (unconditional, per stake) |
|---|---|---|---|---|---|---|
| Basic normalization (FLB-biased; **overstates** longshot `p`) | 0.5693 | 0.2547 | 0.1760 | 0.2361 | **−4.3%** | −3.2% |
| **Shin (primary; unbiased)** | 0.5752 | 0.2527 | 0.1721 | 0.2303 | **−6.7%** | −5.0% |

Shin shades the longshot away-win probability *down* (0.1760 → 0.1721, `z = 0.017`), which **worsens** the EV by ~2.4 pp on live bets relative to basic. This is exactly the sign the calc doc §8.2 predicts ("Shin would shade the longshot `p_W` down further, worsening EV"). **The headline EV is therefore sign-robust to the de-vig choice (both negative) but its *level* is materially more negative under the document's own primary method; the basic-normalization −4.3% is the optimistic end of the de-vig family, not the central estimate.** The de-vig method is registered in the multiple-testing family (calc doc §4.6 / open question 4); report Shin as primary and basic/power as pre-registered sensitivities.

**These EVs are on the *synthetic* DNB price, which is not the same object as the realized quoted-AH loss (Section 3.2). Two distinct, additive effects separate them — do not conflate them:**

1. **Margin wedge (price-level effect, dominant).** The synthetic DNB collapses the draw and carries the *full 1X2 margin on both legs*: the synthetic two-way DNB book here is away `4.053` + favourite `H(D−1)/D = 1.70·0.7368 = 1.253`, booksum `1/4.053 + 1/1.253 = 1.045` ⇒ **synthetic DNB margin ≈ 4.5%**. The relevant *realized* quoted-AH-0.0 loss is the **integer/full-refund figure ≈ 3.24%** (RBF 2024 Table 2, Section 3.3) — *not* the 3.28% weak-team cell, which excludes the zero handicap (Section 3.2). The synthetic→quoted improvement is driven mainly by `M_1X2-on-both-legs − M_AH` (the calc doc §8.3 shows this wedge is ~3 pp, not ~1 pp), because the directly-quoted AH-0 book is the sharpest, lowest-margin product. **This margin wedge, not the reverse-FLB gradient, is the dominant reason the realized quoted-AH loss (~3.2%) is smaller than the synthetic-DNB loss.** (All these AH magnitudes are market-average; the Pinnacle-specific AH-0.0 loss is lower still — Section 2.3.)
2. **Cross-sectional reverse-FLB gradient (within the AH market, small).** *Within* the quoted AH market, the underdog side loses *less* than the favourite side — a **~0.9 pp** underdog-favourable gradient (weak 3.28% vs strong 4.17%, Section 3.2). **This gradient is measured on the zero-handicap-excluded subsample** (Table 7 footnote), so it does not directly attach to the AH-0.0 line; it is carried only as the cross-sectional *direction/sign* of within-market underdog favourability, additive in principle to the margin wedge, and is the only component candidate-transferable to the neutral-venue World Cup (Section 4.2; see Section 3.5).

**This is the quantitative heart of the prior:** under the primary (Shin) de-vig, the *synthetic* underdog-DNB EV is about **−5% to −7% per live bet** on this example; under basic normalization it is the optimistic **−4.3%**. Moving to a *directly-quoted, low-margin AH-0 price* removes most of the synthetic margin wedge (~3 pp) and brings the realized loss down toward the **~3.24% integer/full-refund DNB-family loss** (RBF 2024) — within which any reverse-FLB underdog favourability adds a further fraction of a pp (sign from the zero-handicap-excluded weak/strong gradient, magnitude not directly measured on AH-0.0). **In every case the EV is negative.** A positive-EV result at the World Cup would require a **WC-specific dislocation** large enough to cross zero — e.g. systematic underdog mispricing from neutral-venue compression, dead-rubber motivation, or public over-backing of glamour favourites — that does **not** exist in the sharp domestic data.

### 5.4 What would have to be true for EV > 0

1. **Public-money distortion specific to the World Cup.** WC draws enormous recreational volume on big-name favourites; if that pushes favourite prices below fair more than in domestic leagues, underdog DNB gains. This is plausible *at retail books* but the project benchmarks Pinnacle closing odds, where sharp money corrects it — so the edge, if any, is in the **opening→closing drift** (CLV), not the closing line itself.
2. **Neutral venue mispricing.** If books anchor on FIFA ranking / domestic form and under-adjust for the removal of home advantage, mid-tier underdogs facing nominal "favourites" could be systematically too long. Testable via the host/neutral stratification.
3. **Dead-rubber / rotation effects** (Section 4.4) inflating underdog 90-minute non-loss probability beyond the price.

All three are **falsifiable in the backtest** and all three are *small-sample* phenomena in a ~384-match WC set — hence the power problem.

---

## 6. Documented systems, anomalies, and out-of-sample robustness

- **Cain-Law-Peel (2000)** profitable score/result rules: in-sample on 2,855 matches; not robustly replicated out-of-sample; consistent with Levitt (2004) / Snowberg-Wolfers that mispricing ≠ exploitable profit after margin and limits.
- **Constantinou & Fenton (2013, *J. Gambling Business & Economics* 7(2):41-70)** "Profiting from arbitrage and odds biases of the European football gambling market": report arbitrage and odds-bias profits across 14 leagues 2005/06-2011/12. Robustness caveat: the profitable side requires hitting the *best* available odds at the soft/traditional books, where realistic limits and account restrictions (the same "winners get banned" mechanism Hegarty-Whelan invoke) erode the paper edge. The sharp side (Pinnacle/AH) shows **no such bias to exploit** (Section 3) — which is *why* it is the benchmark.
- **Reverse-FLB in AH/DNB** (Hegarty-Whelan 2025, citation 4; Hegarty-Whelan 2024, citation 5): the only documented anomaly *pointing toward* the project's hypothesis. It is small (~1 pp), well-identified, and *behavioural-pricing* in origin (refund-bet miscalculation), giving a clear, testable mechanism rather than folklore. **Two distinct objects must be kept separate:** (a) the cross-sectional weak/strong loss gradient (citation 4 Table 7), which excludes the zero handicap and therefore evidences the *sign* but not the AH-0.0 *level*; and (b) the handicap-type loss gradient (citation 5 Table 2), where the integer/full-refund line — the AH-0.0 family — has the lowest loss (3.24%) and is the instrument-correct DNB magnitude.
- **Out-of-sample discipline:** any rule fit on the domestic set must be validated on the WC held-out set with walk-forward, never k-fold, and registered for multiple-testing (the WC set will be re-used; correct via Hansen SPA / White Reality Check or BH-FDR per the quant rules).

---

## 7. Honest assessment for the power discussion

- **Is the hoped-for effect even directionally plausible? Yes, narrowly.** The "underdog loses more" intuition is a **1X2** fact; in the **DNB/AH family the FLB is absent-to-weakly-reverse and the underdog side is the cheaper side** (cross-sectional weak 3.28% vs strong 4.17% loss). So the strategy is *directionally* in the favourable half of the market. **Caveat 1 (Section 3.2 — instrument mismatch):** that 3.28%/4.17% gradient is computed on the *zero-handicap-excluded* subsample (Table 7 footnote, verified verbatim), so it does **not** characterize the AH-0.0/DNB line; it evidences only the *sign* of within-market underdog favourability. The DNB-specific loss prior is the **integer/full-refund figure ≈ 3.24%** (RBF 2024 Table 2, Section 3.3). **Caveat 2 (Section 3.2 — non-independence):** the domestic weak/strong and away/home gradients are *not* independent (away ≈ underdog domestically), and only the **price-based weak/strong gradient** is candidate-transferable to neutral WC venues — the away/home gradient is a venue-specific home-advantage-mispricing artifact and is dropped from the WC prior. The transportable evidence is thus one gradient (~0.9 pp), expected to shrink under neutral-venue compression, not two reinforcing ones.
- **Is the *level* plausibly EV-positive net of margin? No, on the prior.** The cross-sectional reverse-FLB gradient (~+0.9 pp underdog-favourable, *within* the AH market, and measured off the AH-0.0 instrument) is **smaller than the AH/DNB margin itself**. The realistic level depends on which price is bet and how it is de-vigged (Section 5.3): on the **directly-quoted, low-margin AH-0 price** the realized DNB-family loss is **≈ −3.24%/bet** (the RBF 2024 integer/full-refund figure — the correct DNB anchor, *not* the 3.28% weak-team cell, which excludes the zero handicap); on the **synthetic 1X2-derived DNB price** the loss is materially worse (≈ −4.3% under basic normalization, ≈ −5% to −7% under the primary Shin de-vig) because the synthetic carries the full 1X2 margin on both legs. **The ≈ −3.24% best case is a *quoted-AH integer-handicap* realized loss, not the synthetic-DNB EV; the two differ mainly by the ~3 pp margin wedge.** Note further it is a **market-average** figure: the Pinnacle-specific AH-0.0 loss baseline (lower still — Section 2.3) must be recomputed on the Pinnacle AH columns before the EV-prior level is fixed. EV>0 requires a WC-specific edge of ~3 pp that the sharp benchmark does not contain.
- **Effect size for power:** plan around a **null-to-small-negative** mean DNB return; the *detectable* alternative is at most a few percent. The per-bet variance input is the **three-point DNB variance** `Var_DNB = p_W·b² + p_fav − μ²` (Section 5.2), *not* the straight-win-bet identity `o − 1`: for the §5.3 example the unconditional DNB SD is **≈ 1.49**, whereas `√(O_DNB−1) ≈ √3 ≈ 1.73` overstates it by ~18% (it is an upper bound). Use `SD(mean) = √(Var_DNB/n)` over the live-bet count, with the refund fraction `q = p_D` carried through `p_D` inside `Var_DNB` (not as an external multiplier). Combined with ~384 WC matches, the **power to detect a true small positive edge is low** — quantify formally in the power-analysis step. The honest framing is: this backtest is far more likely to **bound the loss / test the reverse-FLB transfer** than to confirm a positive edge.
- **Primary diagnostic ranking:** (1) CLV on the underdog side (necessary condition for edge); (2) underdog-vs-favourite DNB loss gradient (does the domestic reverse-FLB transfer to the WC?); (3) stratified EV by phase / dead-rubber / host (where any genuine WC edge would live); (4) bootstrap CI on the mean DNB return and on Sharpe (Opdyke/Lo single-strategy; Ledoit-Wolf for favourite-vs-underdog comparison) with HAC SEs.

---

## Citations

> **Verification register (2026-06-16, updated).** DOIs/metadata re-resolved against CrossRef or web search this date: citation 3 (Štrumbelj, CrossRef — corrected DOI), 4 (Tale of Two Markets journal version, web — DOI/vol/pp added), 5 (RBF, CrossRef), 6 (Overround → Applied Economics, web — journal DOI added), 9 (JQAS host paper, web — author Kalwij + magnitude added), 14a (Shin 1992, used for FLB-pricing origin), 14b (Shin 1993, CrossRef — DOI **confirmed correct as 10.2307/2234240**; 10.2307/2234717 verified to be an unrelated *Editorial Note*), 16 (Angelini & De Angelis, CrossRef — new entry).
>
> **Source-table cells now verified verbatim from the working-paper PDFs** (the binary streams were extracted locally this date after the prior round-trip failed): (a) **Citation 4 / MPRA 116925 Table 7** — the strong/weak/home/away cells are confirmed *exactly* as Strong\* 0.0417, Weak\* 0.0328 (both N = 69,910), Home 0.0411, Away 0.0316 (both N = 84,230), Home+Away 0.0363 (N = 168,460), and the table carries the footnote **"*Zero handicap is not considered for strong and weak bets*"** — the basis for the Section 3.2 instrument-mismatch caveat. The odds convention is confirmed verbatim: *"Our measure of betting odds is the average closing odds (posted just before kickoff) across the various online bookmakers surveyed by www.football-data.co.uk"* (market-average, not Pinnacle). (b) **Citation 5 / RBF 2024 Table 2** — integer 0.0324, .25 0.0361, .5 0.0416, .75 0.0357 (N = 23,730 / 29,250 / 20,762 / 10,488); integer-vs-half-goal difference −0.0093, p < 0.0001 (Table 3) — the basis for the Section 3.3 DNB anchor. (c) **Citation 6 / Overround** — soccer all-seasons 7.1% implied vs 8.7% realized (N = 151,683), tennis 5.4% vs 7.5% (N = 131,283), and verbatim *"loss rates at Pinnacle … are significantly lower than for the other bookmakers"* alongside *"realized loss rates at Pinnacle are significantly larger than predicted rates"* — the basis for the Section 2.3 benchmark/source distinction. **Remaining gap:** the *published-version* (journal) table numbering may differ from these working-paper PDFs; confirm each cell against the journal PDF before any manuscript cite (ScienceDirect/Taylor & Francis returned 403 in this environment). The Snowberg-Wolfers RoR schedule retains its original working-text provenance pending a publisher-record round-trip.

1. Snowberg, E., & Wolfers, J. (2010). Explaining the Favorite-Long Shot Bias: Is it Risk-Love or Misperceptions? *Journal of Political Economy*, 118(4), 723-746. DOI: [10.1086/655844](https://doi.org/10.1086/655844). NBER WP w15923: <https://www.nber.org/papers/w15923>. (Verified: full text, JPE header "723 [Journal of Political Economy, 2010, vol. 118, no. 4]"; rate-of-return schedule −5.5% favourite / −61% at 100/1 / ≈−18% at 4-9/1; 6,403,712 US starts 1992-2001; misperceptions favoured.)

2. Cain, M., Law, D., & Peel, D. A. (2000). The Favourite-Longshot Bias and Market Efficiency in UK Football Betting. *Scottish Journal of Political Economy*, 47(1), 25-36. DOI: [10.1111/1467-9485.00151](https://doi.org/10.1111/1467-9485.00151). RePEc: <https://ideas.repec.org/a/bla/scotjp/v47y2000i1p25-36.html>. (Verified citation via RePEc; 2,855 matches; FLB in result and correct-score markets.)

3. Štrumbelj, E. (2014). On determining probability forecasts from betting odds. *International Journal of Forecasting*, 30(4), 934-943. DOI: [10.1016/j.ijforecast.2014.02.008](https://doi.org/10.1016/j.ijforecast.2014.02.008). (Verified via CrossRef: DOI resolves to Elsevier PII S0169207014000533, IJF 30(4):934-943, Štrumbelj; Shin's model > basic normalization for forecast accuracy. The DOI matches the sibling calculations doc, citation 18; the earlier 10.1016/j.ijforecast.2014.01.006 / PII S0169207014000491 was a misattribution — that PII is a different IJF 30(4) article, Prestwich et al.)

4. Hegarty, T., & Whelan, K. (2025). Forecasting soccer matches with betting odds: A tale of two markets. *International Journal of Forecasting*, 41(2), 803-820. DOI: [10.1016/j.ijforecast.2024.06.013](https://doi.org/10.1016/j.ijforecast.2024.06.013). Working paper: *MPRA Paper No. 116925* / CEPR DP 17949, <https://mpra.ub.uni-muenchen.de/116925/>. (Citation metadata **verified via web search 2026-06-16**: IJF 41(2):803-820, PII S0169207024000670. Source magnitudes — 84,230 matches / 168,460 AH bets; 1X2 longshot 9.4% vs favourite 6.1% loss; AH no FLB, weak reverse-FLB, portfolio loss 3.6% — **verified verbatim against the MPRA 116925 working-paper PDF text 2026-06-16**: Table 7 reads Home+Away 0.0363 [N=168,460], Home 0.0411 / Away 0.0316 [N=84,230 each], Strong\* 0.0417 / Weak\* 0.0328 [N=69,910 each], with footnote **"*Zero handicap is not considered for strong and weak bets*"** — i.e. the strong/weak gradient is computed on the non-zero-handicap subsample and does NOT characterize the AH-0.0/DNB line. Odds convention verbatim: *"the average closing odds (posted just before kickoff) across the various online bookmakers surveyed by www.football-data.co.uk"* — **market-average, not Pinnacle.** **Published-version table numbering may differ; confirm each cell against the journal PDF before any manuscript cite (ScienceDirect 403 in this environment).**)

5. Hegarty, T., & Whelan, K. (2024). Returns on complex bets: evidence from Asian Handicap betting on soccer. *Review of Behavioral Finance*, 16(5), 904-924. DOI: [10.1108/RBF-11-2023-0314](https://doi.org/10.1108/RBF-11-2023-0314). (Citation **verified via CrossRef 2026-06-16**; loss-rate cells **verified verbatim against the karlwhelan.com RBF working-paper PDF text 2026-06-16**: Table 2 "average loss rates from placing an equal amount on all bets, by Asian Handicap type" reads integer 0.0324, .25 0.0361, .5 0.0416, .75 0.0357 [N = 23,730 / 29,250 / 20,762 / 10,488]; Table 3 integer-vs-half-goal difference −0.0093 at p < 0.0001. The **integer/full-refund line — which includes DNB = AH 0.0 — has the lowest loss (3.24%)**; behavioural mis-calculation mechanism. Same vendor/convention as citation 4: market-average closing odds, football-data.co.uk. **Confirm against the published RBF tables before any manuscript cite.**)

6. Hegarty, T., & Whelan, K. (2025). Estimating expected loss rates in betting markets: theory and evidence. *Applied Economics*. DOI: [10.1080/00036846.2025.2507979](https://doi.org/10.1080/00036846.2025.2507979). Working paper: <https://www.karlwhelan.com/Papers/Overround.pdf>. (Journal version **verified via web search 2026-06-16**: Applied Economics 2025, Taylor & Francis. Source magnitudes **verified verbatim against the karlwhelan.com Overround working-paper PDF text 2026-06-16**: Table 1 soccer all-seasons overround-implied 7.1% vs realized 8.7% [N=151,683]; Table 2 tennis 5.4% vs 7.5% [N=131,283]; "average loss rates across all bets for soccer are one-fifth higher than implied by the overround formula." On Pinnacle, verbatim: *"loss rates at Pinnacle, a well-known 'sharp' bookmaker, are significantly lower than for the other bookmakers"* AND *"realized loss rates at Pinnacle are significantly larger than predicted rates"* — i.e. Pinnacle's level is below the market average but still prices some FLB. Data are *"average odds … across a wide range of bookmakers"* (market-average). **Published-version table numbering may differ; confirm against the journal version before any manuscript cite (Taylor & Francis 403 in this environment).**)

7. Forrest, D., Goddard, J., & Simmons, R. (2005). Odds-setters as forecasters: The case of English football. *International Journal of Forecasting*, 21(3), 551-564. DOI: [10.1016/j.ijforecast.2005.03.003](https://doi.org/10.1016/j.ijforecast.2005.03.003). (Verified citation via RePEc/ScienceDirect; Brier-score comparison; odds overtake statistical model over time.)

8. Constantinou, A. C., & Fenton, N. E. (2013). Profiting from arbitrage and odds biases of the European football gambling market. *The Journal of Gambling Business and Economics*, 7(2), 41-70. <https://ideas.repec.org/a/buc/jgbeco/v7y2013i2p41-70.html>. (Verified citation; 14 leagues 2005/06-2011/12; arbitrage/odds-bias profits in the traditional market.)

9. Kalwij, A. (2024). Home advantage for tournament victory: empirical evidence from FIFA World Cups and continental championships. *Journal of Quantitative Analysis in Sports*. DOI: [10.1515/jqas-2024-0056](https://doi.org/10.1515/jqas-2024-0056). (Author and finding **verified via web search 2026-06-16**: single author Adriaan Kalwij, De Gruyter/JQAS. Estimated host advantage for tournament victory ≈ **22 pp** for a home team of average Elo, rising/falling with team strength [9 pp at −1 SD Elo, 42 pp at +1 SD]. Pull the exact point estimate and SE from the publisher record before final citation.)

10. RSSSF — FIFA World Cup Final Tournaments 1930-2022, all-time results table. <https://www.rsssf.org/tables/3002f.html>. (Verified 2026-06-16: the table reports **two-sided team-match** totals — 750 W / 428 D / 750 L over 1,928 team-match rows — i.e. **964 matches, 214 drawn = 22.2%**, with **2,720 goals → 2.82 goals/match**. The win=loss equality confirms the double-count. Corroborated independently: 964 matches / 2,720 goals / 2.82 per game [Britannica, Statista, businesstats]. Primary tabulation; cross-check against an independent count and re-derive the modern 2002-2022 90-minute draw rate in the backtest.)

11. Griffith, R. M. (1949). Odds adjustments by American horse-race bettors. *American Journal of Psychology*, 62(2), 290-294. DOI: [10.2307/1418469](https://doi.org/10.2307/1418469). (Foundational FLB reference, cited by Snowberg-Wolfers and Hegarty-Whelan; not independently re-fetched here — verify before quoting page-level claims.)

12. Kahneman, D., & Tversky, A. (1979). Prospect Theory: An Analysis of Decision under Risk. *Econometrica*, 47(2), 263-291. DOI: [10.2307/1914185](https://doi.org/10.2307/1914185). (Theoretical basis for the misperception/probability-weighting mechanism.)

13. Thaler, R. H., & Ziemba, W. T. (1988). Anomalies: Parimutuel Betting Markets: Racetracks and Lotteries. *Journal of Economic Perspectives*, 2(2), 161-174. DOI: [10.1257/jep.2.2.161](https://doi.org/10.1257/jep.2.2.161). (Source of the "strong market efficiency" definition used by Hegarty-Whelan and of the extreme-favourite limits-to-arbitrage conjecture.)

14a. Shin, H. S. (1992). Prices of State Contingent Claims with Insider Traders, and the Favourite-Longshot Bias. *The Economic Journal*, 102(411), 426-435. DOI: [10.2307/2234526](https://doi.org/10.2307/2234526). (Origin of the insider-trading FLB *pricing* model; the FLB is an equilibrium outcome of the bookmaker pricing against informed money.)

14b. Shin, H. S. (1993). Measuring the Incidence of Insider Trading in a Market for State-Contingent Claims. *The Economic Journal*, 103(420), 1141-1153. DOI: [10.2307/2234240](https://doi.org/10.2307/2234240). (Margin-removal / `z`-estimation operationalisation of the 1992 model that Štrumbelj 2014 finds best for forecast accuracy; embeds an FLB-type correction. **DOI verified against CrossRef 2026-06-16**: `10.2307/2234240` resolves to Shin 1993, EJ 103(420):1141-1153. The alternative `10.2307/2234717` was checked and resolves to an unrelated *Editorial Note*, Greenaway, EJ 103(419):1015-1016 — it is **not** the Shin article. This DOI is consistent across both research documents; see the sibling calculations doc citations 15-16 and its open-question 1, which records the same CrossRef verification and correction.)

15. Levitt, S. D. (2004). Why are gambling markets organised so differently from financial markets? *The Economic Journal*, 114(495), 223-246. DOI: [10.1111/j.1468-0297.2004.00207.x](https://doi.org/10.1111/j.1468-0297.2004.00207.x). (Mispricing without exploitable profit; bookmaker-as-skilled-forecaster.)

16. Angelini, G., & De Angelis, L. (2019). Efficiency of online football betting markets. *International Journal of Forecasting*, 35(2), 712-721. DOI: [10.1016/j.ijforecast.2018.07.008](https://doi.org/10.1016/j.ijforecast.2018.07.008). (Verified via CrossRef 2026-06-16: PII S0169207018301134, IJF 35(2):712-721, Angelini & De Angelis. Large pan-European 1X2 sample; corroborates the standard FLB direction — longshots over-bet / lose more — used as supporting evidence for the §1.2 claim.)

> Citations 11-16 are standard, widely-cited works invoked by the primary sources above. Citations 3, 4, 5, 6, 9, 14a, 14b, and 16 were re-resolved against CrossRef on 2026-06-16; the remaining DOIs are reported from the citing papers and well-established records. Re-resolve each DOI through `/cite-add` before the final manuscript per the verification rule.

---

## Open questions and assumptions to validate

1. **Published-version table cells for the Tale-of-Two-Markets paper (citation 4).** The journal version is now resolved — *International Journal of Forecasting* 41(2):803-820 (2025), DOI 10.1016/j.ijforecast.2024.06.013 (verified 2026-06-16). The reproduced loss-rate cells (1X2 9.4%/6.1%; AH 3.28%/4.17%/3.16%/4.11%; portfolio 3.6%/7.8%) are from the verified working-paper text; **re-fetch the published-version tables and confirm each cell verbatim before any manuscript cite (ScienceDirect returned 403 in this environment; journal table numbering may differ from the working paper).**
2. **Exact host-effect estimate for the JQAS paper (citation 9).** Author and headline magnitude now resolved — Kalwij (2024), host advantage ≈ 22 pp for an average-Elo home team (verified 2026-06-16). Pull the exact point estimate and standard error from the publisher record before final citation.
3. **Does the domestic AH reverse-FLB transfer to the World Cup?** The 3.28% (underdog) vs 4.17% (favourite) AH loss gradient is the central transportability assumption. Neutral-venue probability compression (Section 4.2) predicts the gradient *shrinks* at the WC. Test directly on the held-out set; this is effectively the whole edge hypothesis.
4. **CLV availability and the opening→closing drift on the underdog side.** Confirm football-data.co.uk WC coverage carries Pinnacle *opening* and *closing* 1X2 + AH for 2002-2022 (AH columns were sparse in early WC data). If only closing odds exist, CLV cannot be computed for the WC and the edge test weakens to a pure realized-return test.
5. **Settlement correctness (look-ahead canary).** Verify that DNB settles on the **90-minute** result throughout (refund on 90' draw, including knockout matches level at 90'); a pipeline that settles on the post-ET/penalty result is a leak. Inject a pit-canary.
6. **Underdog definition under ties in price.** Define underdog strictly by higher quoted decimal away/team odds (lower implied p) at a fixed timestamp; specify tie-breaking and the exact odds snapshot (open vs close) point-in-time.
7. **Overround/margin distribution at the WC specifically.** Section 4.5 uses domestic/sharp-market priors (~2-4% AH). Recompute the *actual* WC DNB overround per tournament from the data; 2026's 104-match, 48-team, three-host format changes both the mismatch distribution and the host stratum.
8. **Dead-rubber tagging.** Build a point-in-time qualification-state feature (qualified / eliminated / live) at each match kickoff to stratify the final-round group games without look-ahead.
9. **Multiple-testing register.** The WC held-out set will be queried by several research dimensions; register the family and pre-commit the correction (Hansen SPA / White Reality Check, or BH-FDR) before testing.
10. **Goals-per-match drift and the modern draw rate.** The all-time 2.82 goals/match (964 matches, 2,720 goals — §4.1) is inflated by 1930s-1950s tournaments; recompute the modern (2002-2022) 90-minute draw rate `q` and goal rate that actually govern the held-out sample, since `q` feeds the variance/power calc (§5.2/5.4) and is the DNB refund probability. Do not carry the all-time 22.2% draw rate into the power calc; derive `q` from the held-out match data. (The RSSSF all-time table is two-sided/team-match — divide W/D/L counts by 2 to recover match-level counts; see §4.1 source-arithmetic note.)
11. **AH-0.0-only loss vs the integer-handicap bucket (instrument-correct DNB level).** The DNB anchor adopted here is the RBF 2024 integer-handicap loss (3.24%, citation 5 Table 2), but that bucket pools *all* integer handicaps (0, ±1, ±2, …), not the zero handicap alone, and the citation-4 weak/strong gradient explicitly *excludes* the zero handicap (Table 7 footnote). Neither source isolates the AH-0.0 cell. Re-derive the **AH-0.0-only** realized loss (favourite-side and underdog-side) directly on the expanded domestic set from the football-data.co.uk AH columns restricted to handicap = 0, so the DNB EV prior rests on the traded instrument rather than a pooled or zero-excluded proxy.
12. **Pinnacle-specific AH-0.0 loss baseline (benchmark, not market-average).** Every cited AH/1X2 magnitude (1X2 7.8%, AH 3.6%/3.24%/3.28%) is **average closing odds across the surveyed bookmakers**, not Pinnacle's line (citations 4-6 data descriptions, verified verbatim); the Overround paper finds Pinnacle's loss level is *significantly lower* than the market average (§2.3). Recompute the Pinnacle-specific AH-0.0 loss baseline on the football-data.co.uk Pinnacle closing-AH columns (`PCAHH`/`PCAHA`) before asserting any EV-prior *level* against the Pinnacle benchmark; the market-average figures are an upper bound on it, not the benchmark itself.
