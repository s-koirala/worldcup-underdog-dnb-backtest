# Draw-No-Bet and Odds Calculations: Conversions, Underdog Identification, Synthetic DNB Derivation, De-vigging, EV, Variance, and Kelly Staking

Project: [worldcup-underdog-dnb-backtest](../../README.md). Quant-project rules apply (time-series integrity, no look-ahead, HAC inference, bootstrap CIs, multiple-testing correction). This document is the *calculations* research pillar: it fixes every odds/DNB identity the pipeline depends on, derives them from first principles, and verifies each method against primary sources. All odds are **decimal** unless stated. Settlement is on the **90-minute result** (regulation + stoppage, excluding extra time / penalties), per the official rules cited in §10.

## Scope

Covered, with derivations and worked numbers:

1. Odds-format conversions (decimal / fractional / American / implied probability) and the overround.
2. Underdog identification in the 1X2 market; failure of the American +/- sign; price-gap thresholds and how to select them without a magic number.
3. No-arbitrage synthesis of DNB from 1X2 for home- and away-underdog cases; proof that effective DNB odds `= W·(D−1)/D`; equivalence to Asian Handicap 0.0; reconciliation with a bookmaker-quoted DNB price and the margin gap.
4. De-vigging methods (basic/proportional, Shin 1992/1993, odds-ratio (Cheung), logarithmic/power (Buchdahl), additive) with formulas, attribution, and comparison.
5. EV decomposition of a DNB underdog bet under overround; the exact positive-EV condition.
6. Return distribution and variance of a DNB bet (win / push / loss); closed form; comparison to the straight win bet (`Var = o−1`).
7. Kelly stake for the 3-outcome (win/push/loss) DNB lottery; closed form `f*`.
8. End-to-end worked numeric examples.
9. The 90-minute settlement convention and its effect on knockout-stage labelling.

Notation. For a single match the 1X2 decimal odds are `H` (home win), `D` (draw), `A` (away win). Inverse (raw implied) prices are `r_H = 1/H`, `r_D = 1/D`, `r_A = 1/A`. The **booksum** is `Π = r_H + r_D + r_A`; the **overround / margin** is `M = Π − 1 ≥ 0`. Fair (de-vigged) probabilities are `p_H, p_D, p_A` with `Σ p = 1`. The "underdog win odds" is `W ∈ {H, A}` for the side identified as the longshot.

---

## 1. Odds-format conversions

A decimal odd `o` is the gross return per unit staked (stake included): a 1-unit winning bet returns `o`, i.e. profit `o − 1`. The conversions are algebraic identities (no citation required beyond the definition; the canonical reference text is Buchdahl's *Wisdom of the Crowd*, football-data.co.uk, and the Pinnacle betting-resources glossary):

| From → To | Formula |
|---|---|
| Decimal `o` → raw implied prob `r` | `r = 1/o` |
| Raw implied prob `r` → decimal | `o = 1/r` |
| Decimal `o` → fractional `f/d` | `f/d = o − 1` (express `o−1` as a fraction in lowest terms) |
| Fractional `f/d` → decimal | `o = f/d + 1` |
| Decimal `o` → American `Am` | `Am = +100·(o − 1)` if `o ≥ 2`;  `Am = −100/(o − 1)` if `o < 2` |
| American `Am` → decimal (`Am>0`) | `o = 1 + Am/100` |
| American `Am` → decimal (`Am<0`) | `o = 1 + 100/|Am|` |

The **raw implied probability** `r = 1/o` is *not* a fair probability: across the three 1X2 outcomes `Σ r = Π = 1 + M > 1`. The excess `M` is the bookmaker's margin (vig / overround / juice). Recovering fair probabilities requires removing `M` (§4).

Worked conversion. Decimal `o = 3.40` ⇒ `r = 1/3.40 = 0.2941`; fractional `= 2.40 = 12/5`; American `= +240`. Decimal `o = 1.45` ⇒ `r = 0.6897`; fractional `= 0.45 = 9/20`; American `= −100/0.45 = −222.2`.

---

## 2. Underdog identification in the 1X2 market

### 2.1 Definition adopted

The strategy backs the side with the **higher decimal win price** (equivalently the **lower raw implied win probability** `r = 1/o`). In a two-team match this is the side with `max(H, A)`. Because `o ↦ 1/o` is strictly decreasing, "higher decimal odds" and "lower implied win probability" are the *same* ordering; there is no ambiguity in the binary home-vs-away comparison. The label uses **closing** odds, which are computable at kickoff and are the most efficient pre-match price (Štrumbelj 2014 finds bookmaker prices, especially closing, are well-calibrated probability forecasts), satisfying the no-look-ahead constraint.

### 2.2 Why the American +/- sign is unreliable here

In a **two-outcome** market the American sign is a clean favourite/underdog flag: the favourite is priced `< 2.0` decimal (negative American), the underdog `> 2.0` (positive American), and the `o = 2.0` / `±100` point is the pivot. In the **three-way** 1X2 market the draw absorbs probability mass, so *all three* selections can carry plus-money (decimal `> 2.0`, positive American) simultaneously. Example: `H = 2.60, D = 3.30, A = 2.90` ⇒ American `+160 / +230 / +190`. Every sign is positive; the "+/- as underdog flag" heuristic returns no information. The correct discriminant is purely the **relative** order of `H` vs `A` (or `r_H` vs `r_A`), never the sign relative to the fixed `±100` pivot. The pivot is meaningful only after the draw is removed — which is exactly what DNB / Asian Handicap 0.0 does (§3): in the de-drawed two-outcome book the `2.0` pivot is restored.

### 2.3 Price-gap thresholds and empirical selection

A *strength-of-underdog* filter — bet only when the underdog is "enough of" an underdog — is a tunable. Per project policy (no magic numbers) the threshold is not asserted; it is *selected*. Candidate gap statistics, all computable at kickoff:

- Raw odds ratio `g = W / W_fav` (favourite win odds in the denominator), `g ≥ 1`.
- De-vigged win-probability gap `Δ = p_fav,win − p_dog,win` (fair probabilities from §4).
- Fair DNB-implied probability of the underdog `p_dog^DNB = p_dog / (p_dog + p_fav)` (the two-way conditional, draw removed; see §3.4).

Selection protocol (executed in the staking/edge pillars, recorded here as the calculations contract):

1. Define the bettable set as `{matches : g ≥ τ}` for a grid of `τ`.
2. Choose `τ` by **walk-forward** cross-validation on the *expanded domestic-league universe* (football-data.co.uk Pinnacle closing 1X2, §4/§9), never k-fold (time-series integrity). Objective = out-of-sample mean DNB log-return or deflated Sharpe.
3. Report a **bootstrap CI** on the selected-`τ` performance and treat the `τ`-grid as one member of the multiple-testing family (White 2000 reality check / Hansen 2005 SPA; deflated Sharpe of Bailey & López de Prado 2014) so the threshold search does not manufacture a spurious edge.

Prior expectation. The favourite-longshot bias (Ottaviani & Sørensen 2008; Cain, Law & Peel 2000 for fixed-odds football; Snowberg & Wolfers 2010 for the mechanism) implies the *longshot* side is on average **over**priced relative to its true chance, so a larger gap `τ` should, if anything, *worsen* underdog EV. The CV is therefore expected to favour small/no positive gap, or to confirm a negative-EV prior; the deliverable quantifies this rather than presuming it.

---

## 3. Synthetic Draw-No-Bet from 1X2

### 3.1 Construction (away underdog)

Goal: replicate "back the away side, draw refunds the stake" from the three 1X2 prices, with total stake normalised to 1 unit. The draw must be perfectly hedged so that a draw returns exactly the unit stake (a push). Split the unit stake:

- `s_D = r_D = 1/D` on the draw (the **draw hedge**);
- `s_A = 1 − s_D = (D − 1)/D` on the away win.

Outcome ledger (net return per unit total stake; "net" = gross payout, with stake recovered as part of decimal odds):

| 90-min result | Draw leg pays | Away leg pays | Total gross | Net profit |
|---|---|---|---|---|
| Away win | 0 (loses) | `s_A·A = A(D−1)/D` | `A(D−1)/D` | `A(D−1)/D − 1` |
| Draw | `s_D·D = (1/D)·D = 1` | 0 (loses) | `1` | `0` (push — stake refunded) |
| Home win | 0 | 0 | `0` | `−1` (full loss) |

The draw leg is a **perfect hedge**: staking `1/D` at decimal `D` returns exactly `1` on a draw, so the combined position returns the entire unit stake on a draw — the defining DNB behaviour. Therefore the **effective DNB decimal odds on the away underdog** are

> **`o_DNB = A·(D − 1)/D`.**

### 3.2 Construction (home underdog)

By symmetry (hedge the draw with `1/D`, put the rest on home):

> **`o_DNB = H·(D − 1)/D`.**

In both cases, with the generic underdog win price `W ∈ {H, A}`:

> **`o_DNB = W·(D − 1)/D`  =  `W·(1 − r_D)`,**  since `(D−1)/D = 1 − 1/D = 1 − r_D`. ∎

### 3.3 No-arbitrage / replication proof

The DNB payoff is a contingent claim paying `o_DNB` on {underdog win}, `1` on {draw}, `0` on {favourite win}. The 1X2 market spans the three Arrow-Debreu states (win/draw/loss) with prices `r_W = 1/W, r_D = 1/D, r_fav = 1/W_fav`. Any state-contingent payoff is uniquely replicated by holding `payoff_state × r_state`-worth of each elementary claim, and by the law of one price its cost equals the sum of replication costs. The DNB claim normalised to unit cost requires, on the win and draw states only (the loss state pays 0, costs 0):

- Draw state must pay `1`: hold quantity `q_D` of the draw claim with `q_D·D = 1 ⇒ q_D = 1/D`, costing `q_D = 1/D = s_D`.
- Win state pays `o_DNB`: the remaining budget `1 − s_D = (D−1)/D` is staked on the win claim at price `1/W`, delivering `[(D−1)/D]·W` in the win state.

Hence `o_DNB = W(D−1)/D` is the unique no-arbitrage replication value; any quoted DNB price differing from it (after equalising margin) is an arbitrage against the 1X2 book. ∎ This is the standard complete-market replication argument (Arrow 1964; state-contingent-claims framing as used by Shin 1992, 1993).

### 3.4 Equivalence to Asian Handicap 0.0 (and to the conditional 1X2)

Asian Handicap 0.0 ("level ball" / "draw no bet") applies a 0-goal handicap to both teams; a level (drawn) 90-minute result voids the bet and the **stake is refunded**, identical to DNB (Pinnacle betting rules; Buchdahl / industry guides). The two markets have the same three settlement outcomes (win / void / lose) and are therefore the same instrument. football-data.co.uk supplies the Asian-Handicap columns (`PAHH/PAHA` Pinnacle pre-match AH home/away at line `AHh`; `PCAHH/PCAHA` Pinnacle **closing** AH home/away at closing line `AHCh` — header confirmed against a current-season CSV, §9) but carries **no native DNB column** (verified against the downloaded CSV header, §9); when the quoted line `AHh = 0` (resp. `AHCh = 0`), the AH price *is* the DNB price; otherwise DNB must be synthesised from 1X2 as above.

The fair (de-vigged) DNB-implied win probability removes the draw and renormalises the two win states:

> `p_W^DNB = p_W / (p_W + p_fav,win) = p_W / (1 − p_D)`.

Under a *fair* 1X2 book (`Σ p = 1`, no margin), the fair DNB odds equal `1/p_W^DNB = (1 − p_D)/p_W`, and one can verify `o_DNB = W(D−1)/D` reduces to this only when the book is margin-free — in general the synthetic price carries the *1X2* margin (§3.5).

### 3.5 Reconciliation with a bookmaker-quoted DNB / AH-0 price; the margin gap

The synthetic price `o_DNB = W(D−1)/D` inherits whatever margin the bookmaker baked into the *three* 1X2 prices, **including the draw leg**. A directly quoted AH-0 / DNB market is a *two-outcome* book whose margin the bookmaker sets independently and which is typically **lower** (two-way Asian markets are the sharpest, lowest-margin products at books such as Pinnacle). Consequently:

- Synthetic-DNB booksum (two-way, after collapsing the draw) carries margin from `Π_1X2 = 1 + M_1X2`.
- Quoted AH-0 booksum `r_W^{AH} + r_fav^{AH} = 1 + M_AH`, with usually `M_AH < M_1X2`.

So the quoted DNB price is generally **better (higher)** than the synthetic one, because the draw-leg hedge in the synthetic construction effectively pays the 1X2 margin twice (once on the draw price `D`, once on the win price `W`). The pipeline should therefore prefer the **quoted** AH-0 price when available (lower implied cost) and use the synthetic `W(D−1)/D` only as a fallback/cross-check, flagging the `M_1X2 − M_AH` wedge in the edge accounting. Numeric reconciliation is in §8.3.

---

## 4. De-vigging: recovering fair probabilities

The booksum carries margin `M = Π − 1`. Several inversions exist; they differ in *how* they attribute the margin across outcomes, which matters precisely because the favourite-longshot bias means the margin is **not** spread uniformly.

### 4.1 Basic / proportional (multiplicative) normalisation

Divide each inverse price by the booksum:

> `p_i = r_i / Π = (1/o_i) / Σ_j (1/o_j)`.

This spreads the margin in proportion to each raw price — i.e. it assumes the *same* proportional overround on every outcome. It cannot represent the favourite-longshot bias (it preserves the raw odds ranking and ratios), and is the baseline against which the others are judged (Štrumbelj 2014; Clarke, Kovalchik & Ingram 2017). Attribution: folklore baseline; stated as the "basic" method in the CRAN `implied` package and Buchdahl.

### 4.2 Shin (1992, 1993) — insider-trading model

Shin models the book as set by a bookmaker facing a fraction `z` of *insider* (informed) money plus uninformed money, and prices to break even in expectation. The recovered fair probabilities satisfy (Jullien & Salanié 1994 closed form, as restated by Štrumbelj 2014 and Kızıldemir, Akın & Alkan 2024):

> `p_i = [ √(z² + 4(1 − z)·r_i²/Π) − z ] / [ 2(1 − z) ]`,  with `r_i = 1/o_i`, `Π = Σ_j r_j`,

and `z ∈ [0,1)` chosen so that `Σ_i p_i = 1` (fixed-point iteration from `z₀ = 0`; Štrumbelj 2014/2016). `z` is interpretable as the proportion of informed (insider) trade and is reported as a diagnostic. **Two-outcome closed form** (applicable to the *quoted* DNB / AH-0 two-way book — see the applicability note below): with `π₊ = r_1 + r_2` and `π₋ = r_1 − r_2`,

> `z = [ (Π − 1)(π₋² − π₊) ] / [ π₊·(π₋² − 1) ]`  (Jullien & Salanié 1994; Štrumbelj 2016 analytic `n = 2` solution).

> **Applicability note (verified numerically).** Shin requires the input book to be *over*-round (`Π > 1`). It applies to the three-way 1X2 book and to a **quoted** two-way AH-0/DNB book, but **not** to a draw-dropped 1X2 residual (`r_W + r_fav < 1`, under-round), which makes the `n=2` closed form return an invalid `z < 0`. To de-vig the synthetic DNB, run Shin (or power/basic) on the full 1X2 book and form the conditional `q_W = p_W/(1 − p_D)`; reserve the `n=2` Shin form for the directly quoted AH-0 market. See §8.2.

Shin de-vigging **endogenously produces** the favourite-longshot bias (longshots shaded relative to favourites), which is its principal advantage over basic normalisation and the reason Štrumbelj (2014) finds it the more accurate probability forecast on soccer odds. Primary sources: Shin (1992) DOI [10.2307/2234526](https://doi.org/10.2307/2234526); Shin (1993) DOI [10.2307/2234240](https://doi.org/10.2307/2234240).

### 4.3 Odds-ratio method — Cheung (2015), in Buchdahl

Define the odds ratio between a true probability `p` and the bookmaker probability `x` it maps to, held constant across outcomes by a single constant `c`:

> `OR(x, p) = [x(1 − p)] / [p(1 − x)]`,  and the inversion solving `x = c·p / (1 − p + c·p)` for the `p` that makes `Σ x_i = Π` (equivalently `Σ p_i = 1`).

A single `c` is fitted (uniroot / Solver). The odds-ratio map applies a *disproportionate*, longshot-shortening margin, weaker on longshots than the logarithmic method (Buchdahl, *Wisdom of the Crowd*). Attribution: Keith Cheung (2015), popularised by Joseph Buchdahl.

### 4.4 Logarithmic / power method — Buchdahl

A common exponent `n` (with `n < 1`) maps true to bookmaker probabilities:

> `x_i = p_i^{n}`,  choose `n` so that `Σ_i x_i = Π` (then `p_i = x_i^{1/n}` renormalised);

equivalently, working from raw prices, `p_i ∝ r_i^{1/n}`. Because `n<1`, longshots (`small p`) are shortened more than favourites — again reproducing the favourite-longshot bias. The CRAN `implied` package labels this `power`; Buchdahl calls it the logarithmic method (Vovk & Zhadanov 2009 and Clarke et al. 2017 also study the power transform). Clarke, Kovalchik & Ingram (2017) report the power method universally outperforms plain multiplicative on their multi-sport data and, unlike Shin/additive, never returns probabilities outside `[0,1]` when applied in reverse.

### 4.5 Additive method — Clarke et al. (2017)

Subtract an equal share of the margin from each raw price:

> `p_i = r_i − M/n`  (`n` = number of outcomes, `M = Π − 1`).

Simple but can yield **negative** probabilities for strong favourites/longshots and does not, by itself, model the favourite-longshot bias correctly; for a two-outcome book it coincides with Shin (Clarke et al. 2017). Use as a sensitivity check only.

### 4.6 Comparison and project choice

| Method | Margin attribution | Models FLB? | Range-safe? | Primary source |
|---|---|---|---|---|
| Basic / multiplicative | proportional | No | Yes | baseline (Štrumbelj 2014) |
| Additive | equal absolute | No | No (can go <0) | Clarke et al. 2017 |
| Shin 1992/93 | insider-driven, FLB | Yes | mostly (reverse can exceed 1) | Shin 1992, 1993; Jullien–Salanié 1994 |
| Odds-ratio (Cheung) | longshot-shortening | Yes | Yes | Cheung 2015 / Buchdahl |
| Logarithmic / power | longshot-shortening | Yes | Yes | Buchdahl; Vovk–Zhadanov 2009; Clarke et al. 2017 |

Project default: **Shin** for the primary fair-probability estimate (best soccer-odds calibration per Štrumbelj 2014, and its two-outcome closed form is exactly the DNB book), with **power** and **basic** as pre-registered sensitivity analyses. The de-vig method is part of the analysis family and is registered for multiple-testing accounting. The reported `z` (Shin) is logged per match.

---

## 5. Expected-value decomposition of a DNB underdog bet under overround

Let `p_W, p_D, p_fav` be the *true* probabilities (`Σ = 1`) of underdog-win / draw / favourite-win. A unit DNB stake on the underdog returns `o_DNB` on a win, `1` on a draw (push), `0` on a loss. Net profit per unit:

> `E[π] = p_W·(o_DNB − 1) + p_D·(0) + p_fav·(−1)`
> `     = p_W·o_DNB − p_W − p_fav`
> `     = p_W·o_DNB − (1 − p_D)`,  since `p_W + p_fav = 1 − p_D`.

Substituting the synthetic DNB price `o_DNB = W(1 − r_D)` and writing the bookmaker's *raw* implied win price `r_W = 1/W` so `W = 1/r_W`:

> `E[π] = (p_W / r_W)·(1 − r_D) − (1 − p_D)`.

**Gross-return form.** The conditional (no-draw) win probability is `q_W = p_W/(1 − p_D)`. Then

> `E[π] = (1 − p_D)·[ q_W·o_DNB − 1 ]`,

so the DNB bet has positive EV **iff** the bracket is positive, treating it as a two-outcome bet on the conditional `q_W` at price `o_DNB`:

> **Positive-EV condition:  `q_W · o_DNB > 1`,  i.e.  `o_DNB > 1/q_W = (1 − p_D)/p_W`.**

Decomposition into *fair price* + *edge*. Write the fair DNB odds `o_DNB^{fair} = (1 − p_D)/p_W = 1/q_W`. Then

> `E[π] = (1 − p_D)·q_W·(o_DNB − o_DNB^{fair}) / o_DNB^{fair} = (1 − p_D)·[ o_DNB / o_DNB^{fair} − 1 ]`.

The bet wins iff the *offered* DNB price exceeds the *fair* DNB price; the size of the edge is the proportional price gap scaled by the no-draw probability `(1 − p_D)`. Under a positive 1X2 margin `M_1X2 > 0` and the favourite-longshot bias, `o_DNB` (synthetic) is *below* `o_DNB^{fair}` for longshots — the margin and the FLB both push the bracket negative — which is the structural source of the **negative-EV prior** for underdog DNB (Cain, Law & Peel 2000; Ottaviani & Sørensen 2008). The edge is testable: estimate `p_W, p_D` by Shin de-vigging (§4.2) on a held-out universe and compare to the offered price; report with HAC/Newey-West SEs and a bootstrap CI on mean return.

---

## 6. Return distribution and variance of a DNB bet

### 6.1 Three-point return distribution

Per unit stake, net return `R`:

| Outcome | Prob | Net return `R` |
|---|---|---|
| Underdog win | `p_W` | `b ≡ o_DNB − 1` |
| Draw (push) | `p_D` | `0` |
| Loss | `p_fav = 1 − p_W − p_D` | `−1` |

Mean (from §5): `μ = E[R] = p_W·b − p_fav = p_W·o_DNB − (1 − p_D)`.

Second moment: `E[R²] = p_W·b² + p_D·0 + p_fav·1 = p_W·b² + p_fav`.

Variance (closed form):

> **`Var(R) = p_W·b² + p_fav − μ²`,  with `b = o_DNB − 1`, `p_fav = 1 − p_W − p_D`.**

Fully expanded in terms of `o ≡ o_DNB`:

> `Var(R) = p_W(o−1)² + (1 − p_W − p_D) − [p_W·o − (1 − p_D)]²`.

### 6.2 Comparison to the straight win bet (`Var = o − 1`)

**The benchmark `Var = o − 1` is the variance of a FAIR straight win bet.** For a fair straight win bet at decimal `o` (win prob `p = 1/o`, so `μ = 0`; no draw, no push):

> `Var_winbet(fair) = p·(o−1)² + (1−p)·(−1)² = (1/o)(o−1)² + (1 − 1/o) = (o−1)²/o + (o−1)/o = (o−1)`.

So `Var_winbet(fair) = o − 1` (the project's stated identity). It is a *fair-bet* benchmark, not a generic upper bound: the DNB closed form `Var(R) = p_W·b² + p_fav − μ²` is **not** universally below `o_DNB − 1`. At an arbitrarily *mispriced* DNB price the inequality can reverse — e.g. `p_W = 0.70, p_D = 0.22` (`p_fav = 0.08`) at `o_DNB = 6.60` gives `μ = 3.84`, `Var_DNB = p_W·b² + p_fav − μ² = 0.70·5.60² + 0.08 − 3.84² = 7.29 > o_DNB − 1 = 5.60` (the large positive `μ` from gross over-pricing inflates `p_W·b²` faster than `μ²` removes it). The claim therefore holds only when the two bets are compared on a like-for-like basis: either (i) the DNB is priced **fairly** (`μ = 0`), or (ii) the DNB is compared to a fair win bet sharing the *same* odds and the same no-draw view. Without one of those restrictions the comparison is not meaningful.

**Exact result at the fair DNB price.** Take the DNB at its own fair price `o_DNB = (1 − p_D)/p_W` (so `μ = 0`, §5). Then `b = o_DNB − 1` and `Var_DNB(fair) = p_W·b² + p_fav` (the `−μ²` term vanishes). The difference against the same-odds fair win bet is closed-form:

> `Var_winbet(fair) − Var_DNB(fair) = (o_DNB − 1) − [p_W·b² + p_fav]`. Substituting `o_DNB = (1 − p_D)/p_W`, `b = (1 − p_D)/p_W − 1 = (1 − p_D − p_W)/p_W = p_fav/p_W`, and `p_fav = 1 − p_W − p_D`, the algebra collapses to
>
> **`Var_winbet(fair) − Var_DNB(fair) = p_D · p_fav / p_W`  (≥ 0, with `p_fav = 1 − p_W − p_D`).**

This is non-negative for any valid `(p_W, p_D, p_fav)` with `p_W > 0`, and **strictly positive iff `p_D > 0` and `p_fav > 0`**. Verified symbolically (SymPy `factor`) and by Monte-Carlo over the full probability simplex (500,000 Dirichlet draws: max absolute error `1.9e−9`; difference `≥ 0` in every draw; zero violations of `Var_DNB(fair) < o_DNB − 1`). The same simulation at *arbitrary* mispriced odds produces violations in ≈45% of draws, confirming the inequality is a fair-price (or same-view) statement, not a general one. This resolves open question 5. The reduction `p_D·p_fav/p_W` is the push mass `p_D` times the favourite-loss probability `p_fav` it sits beside, scaled by `1/p_W`: at the fair price the draw mass that would have been a `(−1)` loss contributes `0` deviation instead, and the magnitude is exactly this product.

**Same-odds, same-view comparison.** The other valid framing fixes the odds at the offered `o_DNB` and compares the DNB `(p_W, p_D, o_DNB)` against a fair straight win bet at the *same* `o_DNB` whose win probability is the conditional no-draw probability `q_W = p_W/(1 − p_D)`. This isolates the push effect from the mispricing-driven `μ`; it is the framing used in the §8.2 worked number (DNB at the offered price vs a fair win bet at the same odds). It does **not** reduce to a single tidy expression and is not universally signed at arbitrary `(p_W, p_D, o_DNB)` — only the fair-price identity above is. Treat §8.2's −29% as a worked instance of this framing, not a general bound.

Practically: at a fair (or same-view) price, DNB trades a lower payout (`o_DNB = W(D−1)/D < W`) for **lower variance and a non-zero push probability**, improving the geometric (Kelly) growth profile relative to the straight win bet at the same underlying view. The improvement is `p_D·p_fav/p_W` per unit variance at the fair price. This is quantified in §8.

---

## 7. Kelly stake for the DNB (win / push / loss) lottery

### 7.1 Derivation

Kelly (1956) maximises expected log growth. With fraction `f` of bankroll on a unit-priced DNB bet whose return is `R ∈ {b, 0, −1}` (probs `p_W, p_D, p_fav`), the growth function is

> `g(f) = p_W·ln(1 + f·b) + p_D·ln(1 + f·0) + p_fav·ln(1 − f)`
> `     = p_W·ln(1 + f·b) + p_fav·ln(1 − f)`  (the push term `ln(1) = 0`).

First-order condition `g'(f) = 0`:

> `p_W·b/(1 + f·b) − p_fav/(1 − f) = 0`
> `⇒ p_W·b·(1 − f) = p_fav·(1 + f·b)`
> `⇒ p_W·b − p_fav = f·b·(p_W + p_fav)`.

> **`f* = (p_W·b − p_fav) / [ b·(p_W + p_fav) ]`,  with `b = o_DNB − 1`, `p_fav = 1 − p_W − p_D`, `p_W + p_fav = 1 − p_D`.**

Equivalently `f* = [p_W·(o_DNB − 1) − (1 − p_W − p_D)] / [(o_DNB − 1)(1 − p_D)]`. Bet only when `f* > 0`, i.e. when `p_W·b > p_fav` ⇔ `p_W·o_DNB > 1 − p_D` — the **same positive-EV condition as §5**, as expected (Kelly is positive exactly when EV is positive).

### 7.2 Sanity checks and the push effect

- **No-push limit** (`p_D → 0`, `p_fav = 1 − p_W`): `f* = (p_W·b − (1−p_W)) / [b·1] = p_W − (1−p_W)/b = [p_W(b+1) − 1]/b = (p_W·o − 1)/(o − 1)`, the textbook two-outcome Kelly `f* = (p·o − 1)/(o − 1) = edge/odds`. ✓
- **Push raises Kelly leverage relative to a same-edge two-outcome win bet**: the denominator carries the factor `(1 − p_D) < 1`, and the push removes downside mass, so for a fixed positive edge the push-adjusted `f*` is larger than the naive two-outcome `f*` evaluated at `(p_W, o_DNB)` ignoring the push — because part of the "non-win" probability returns the stake rather than losing it. This is the staking-side manifestation of the §6 variance reduction.

The project uses **fractional Kelly** (a fraction `λ·f*`, `0 < λ ≤ 1`) with `λ` selected by walk-forward CV on the expanded universe (not asserted), entered into the staking multiple-testing family alongside flat and fixed-fraction staking. Full-Kelly is reported only as the upper envelope; the negative-EV prior implies `f* ≤ 0` for many matches, in which case the stake is **zero** (no short side in a DNB market).

---

## 8. End-to-end worked numeric examples

### 8.1 Synthetic DNB from 1X2 (away underdog)

1X2 closing odds `H = 1.80, D = 3.60, A = 4.50` (away is the longshot: `A = 4.50 > H = 1.80`). Booksum `Π = 1/1.80 + 1/3.60 + 1/4.50 = 0.5556 + 0.2778 + 0.2222 = 1.0556`, margin `M = 5.56%`.

- Stake split: `s_D = 1/D = 0.2778` on draw; `s_A = (D−1)/D = 2.60/3.60 = 0.7222` on away.
- **Effective DNB odds**: `o_DNB = A(D−1)/D = 4.50 × 0.7222 = 3.250`. (Check: `W(1 − r_D) = 4.50 × (1 − 0.2778) = 4.50 × 0.7222 = 3.250`. ✓)
- Ledger per unit: away win → `0.7222 × 4.50 = 3.250` gross (`+2.250` profit); draw → `0.2778 × 3.60 = 1.000` gross (push, `0`); home win → `0` (`−1`).

### 8.2 De-vig and EV/variance/Kelly on the DNB book

De-vig the full **three-way** 1X2 book (the object that actually carries the margin) and read off the unconditional probabilities, then evaluate the DNB bet. Basic (multiplicative) 1X2 de-vig: `p_W = r_A/Π = 0.2222/1.0556 = 0.2105`, `p_D = 0.2778/1.0556 = 0.2632`, `p_fav = 0.5556/1.0556 = 0.5263`. (Shin would shade the longshot `p_W` *down* further, worsening EV; basic is shown for transparency and is the conservative-against-the-strategy choice here.)

> **Caveat on applying Shin to the DNB book.** Shin (§4.2) requires an *over*-round two-way book (booksum `> 1`). Merely *dropping* the draw from the 1X2 prices and renormalising the two win prices yields an **under-round** residual (here `r_A + r_H = 0.7778 < 1`); feeding that into the Shin `n=2` closed form returns an out-of-range `z = −0.21` and a degenerate solution. Shin's two-way form is therefore the right tool **only for the quoted AH-0 / DNB market** (which has its own margin `> 0`, §8.3), not for a draw-dropped 1X2 residual. For the synthetic DNB the correct route is to de-vig the *three-way* 1X2 book (basic / Shin / power) and form `q_W = p_W/(1 − p_D)` from the resulting fair probabilities.

- **EV** (per unit, basic probs, synthetic `o_DNB = 3.250`):
  `μ = p_W·o_DNB − (1 − p_D) = 0.2105 × 3.250 − (1 − 0.2632) = 0.6842 − 0.7368 = −0.0526`.
  ⇒ **−5.3% EV per unit** — negative, consistent with paying the 1X2 margin on both legs (matches the §5 prior).
- Positive-EV check: need `o_DNB > (1 − p_D)/p_W = 0.7368/0.2105 = 3.500`; offered `3.250 < 3.500` ⇒ fails ⇒ negative EV. The *fair* DNB price is `3.500`; the synthetic price `3.250` is `7.1%` short of fair — that gap is the embedded vig.
- **Variance**: `b = 2.250`. `Var = p_W·b² + p_fav − μ² = 0.2105×5.0625 + 0.5263 − (−0.0526)² = 1.0657 + 0.5263 − 0.0028 = 1.589`. Compare a fair straight win bet at the same `o = 3.250`: `Var = o − 1 = 2.250`. Here the DNB variance is lower, `2.25 → 1.59` (−29%), SD `= 1.261`. This is the same-odds / same-view comparison of §6.2, *not* a general bound: at arbitrarily mispriced odds `Var_DNB` can exceed `o − 1` (§6.2 counterexample). The clean, always-signed statement is the fair-price identity `Var_winbet(fair) − Var_DNB(fair) = p_D·p_fav/p_W`; for these probabilities at the fair price `o_DNB = 3.500` it gives `(0.2632×0.5263)/0.2105 = 0.658`, i.e. `Var_DNB(fair) = 2.500 − 0.658 = 1.842`.
- **Kelly**: `f* = (p_W·b − p_fav)/[b(p_W + p_fav)] = (0.2105×2.250 − 0.5263)/[2.250×(0.2105+0.5263)] = (0.4737 − 0.5263)/(2.250×0.7368) = −0.0526/1.658 = −0.0317`. `f* < 0` ⇒ **do not bet** (no edge), confirming the EV sign.

### 8.3 Reconciliation: synthetic vs quoted AH-0 / DNB (margin gap)

Suppose the book *also* quotes AH-0 directly at sharp two-way prices `away 3.40, home 1.40`. Quoted two-way booksum `= 1/3.40 + 1/1.40 = 0.2941 + 0.7143 = 1.0084`, so `M_AH = 0.84%`. The **quoted** away DNB price `3.40 > 3.250` synthetic, because the AH-0 book carries `0.84%` margin vs the synthetic's `~5.6%` (the synthetic pays the 1X2 margin on both the win and draw legs). EV at the quoted price: `μ = 0.2105×3.40 − 0.7368 = 0.7157 − 0.7368 = −0.0211` (−2.1%, still negative but materially less bad). **Lesson for the pipeline**: always prefer the quoted AH-0 column when present; use the synthetic `W(D−1)/D` only as fallback and log the `M_1X2 − M_AH` wedge in edge accounting (§3.5).

### 8.4 A positive-EV illustration (to exercise the formulas)

If the true probabilities were `p_W = 0.30, p_D = 0.26, p_fav = 0.44` while the offered DNB price is `o_DNB = 3.40` (i.e. the bettor's model disagrees with the book): fair DNB `= (1−0.26)/0.30 = 2.467`; offered `3.40 > 2.467` ⇒ positive edge. `μ = 0.30×3.40 − 0.74 = 1.020 − 0.74 = +0.280` (+28%). `b = 2.40`, `Var = 0.30×5.76 + 0.44 − 0.0784 = 1.728 + 0.44 − 0.078 = 2.090`, SD `1.446`. Kelly `f* = (0.30×2.40 − 0.44)/[2.40×(0.30+0.44)] = (0.72 − 0.44)/(2.40×0.74) = 0.28/1.776 = 0.1577` ⇒ stake `15.8%` full-Kelly (use fractional in practice). This is illustrative; the empirical prior (§2.3, §5) is that such edges do **not** systematically exist for underdog DNB.

---

## 9. Data dictionary linkage (football-data.co.uk)

Verified against a downloaded current-season football-data.co.uk CSV header (the `notes.txt` data dictionary documents the AH codes but lags the live headers — it lists `PAHH/PAHA` and the line `AHh` but not the closing variants, which are present in the actual CSV; codes below are read directly from the `2324/E0.csv` header row):

- **Pinnacle closing 1X2**: `PSCH` (home), `PSCD` (draw), `PSCA` (away) — the "C" denotes closing; pre-match are `PSH/PSD/PSA` (also `PH/PD/PA`). These feed the synthetic DNB and the de-vig. (`notes.txt`: "PSH and PH = Pinnacle home win odds", etc.; closing variants carry the "C".)
- **Asian Handicap, pre-match**: line `AHh` = handicap on the home team (recorded since 2019/20, per `notes.txt`); prices `B365AHH/B365AHA` (Bet365), `PAHH/PAHA` (Pinnacle — `notes.txt`: "PAHH = Pinnacle Asian handicap home team odds", "PAHA = Pinnacle Asian handicap away team odds"); `MaxAHH/MaxAHA`, `AvgAHH/AvgAHA` = market max/avg.
- **Asian Handicap, closing**: closing line `AHCh`; prices `B365CAHH/B365CAHA`, `PCAHH/PCAHA` (Pinnacle closing — prefix "PC", not "PSC"); `MaxCAHH/MaxCAHA`, `AvgCAHH/AvgCAHA`. When `AHCh = 0` (resp. pre-match `AHh = 0`) the AH price *is* the quoted DNB (§3.4); the closing line/price pair is the no-look-ahead object used by the pipeline.
- **No native DNB column exists** in the dataset (the CSV header carries no DNB/`TNB` field); DNB on the World Cup and league data is either the quoted `AHCh = 0` price or the synthetic `W(D−1)/D` from 1X2. This is the operational reason the synthetic identity is load-bearing for the backtest.

Estimation universe: domestic leagues (Pinnacle closing 1X2 + AH) as the powered sample; the World Cup (~384 matches, 2002–2022; 104 matches in 2026) is the held-out subsample (per README/CLAUDE.md).

---

## 10. The 90-minute settlement convention and knockout-stage labelling

**Settlement rule.** 1X2, Draw-No-Bet, and Asian-Handicap markets settle on the **result at the end of normal time = 90 minutes + injury/stoppage time, excluding extra time, penalty shootout, and golden goal**, unless a market is explicitly labelled "to qualify" / "to lift the trophy" (Pinnacle betting rules; Betfair football 90-minute rule; William Hill football settlement guide). The DNB *push* is triggered by a **90-minute draw**, regardless of who advances after extra time/penalties.

**Implication for knockout-stage labelling (no look-ahead, settlement integrity).**

1. The bet outcome is `{underdog wins in 90' / draw in 90' (push) / favourite wins in 90'}`. A match that is `1–1` after 90 minutes and decided on penalties is a **push** for DNB, even though the tournament records a "winner."
2. The dataset's *match result* field must be the **90-minute** score (`FTHG/FTAG` in football-data.co.uk are full-time = 90' + stoppage, which is correct; extra-time/penalty results live in separate fields and must be excluded).
3. World Cup group-stage matches cannot be drawn-decided beyond 90' (no ET), so labelling is unambiguous; **knockout** matches require explicit handling: use the 90-minute result for settlement, never the post-ET/penalty progression. Mislabelling a penalty-decided `1–1` as an underdog win/loss would inject look-ahead-style settlement error and bias the backtest.
4. 2026 format note: the expansion to 48 teams / 104 matches changes the *count* and the group structure but not the 90-minute settlement convention; knockout rounds still use ET/penalties for progression only, not for 1X2/DNB settlement.

---

## Citations

Verified against primary sources. DOIs / stable URLs were CrossRef-round-tripped during research and re-checked in audit; the one exception found — Ottaviani–Sørensen (2008), ref 13 — had a dead DOI that has since been corrected and re-verified (see open question 1). Where a paywalled article was used, the DOI resolves to the publisher record.

1. Arrow, K. J. (1964). The Role of Securities in the Optimal Allocation of Risk-bearing. *Review of Economic Studies* 31(2): 91–96. DOI [10.2307/2296188](https://doi.org/10.2307/2296188). (State-contingent-claims / complete-markets replication framework.)
2. Bailey, D. H., & López de Prado, M. (2014). The Deflated Sharpe Ratio: Correcting for Selection Bias, Backtest Overfitting, and Non-Normality. *Journal of Portfolio Management* 40(5): 94–107. DOI [10.3905/jpm.2014.40.5.094](https://doi.org/10.3905/jpm.2014.40.5.094).
3. Buchdahl, J. *Using the Wisdom of the Crowd to Find Value in a Football Match Betting Market* (updated). football-data.co.uk. URL [https://www.football-data.co.uk/The_Wisdom_of_the_Crowd_updated.pdf](https://www.football-data.co.uk/The_Wisdom_of_the_Crowd_updated.pdf). (Odds-ratio, logarithmic/power, differential-margin methods; overround definition.)
4. Cain, M., Law, D., & Peel, D. (2000). The Favourite-Longshot Bias and Market Efficiency in UK Football Betting. *Scottish Journal of Political Economy* 47(1): 25–36. DOI [10.1111/1467-9485.00151](https://doi.org/10.1111/1467-9485.00151).
5. Cheung, K. (2015). Odds-ratio method for converting bookmaker odds to probabilities (Sports Trading Network blog), as documented in the CRAN `implied` package and Buchdahl (see refs 3, 11).
6. Clarke, S., Kovalchik, S., & Ingram, M. (2017). Adjusting Bookmaker's Odds to Allow for Overround. *American Journal of Sports Science* 5(6): 45–49. DOI [10.11648/j.ajss.20170506.12](https://doi.org/10.11648/j.ajss.20170506.12). (Multiplicative vs additive vs Shin vs power; range-safety.)
7. football-data.co.uk. Data dictionary / notes. URL [https://www.football-data.co.uk/notes.txt](https://www.football-data.co.uk/notes.txt) (Pinnacle 1X2 `PSH/PSD/PSA`, AH `PAHH/PAHA`, line `AHh`; closing variants not listed in notes). Closing-column codes (`PSCH/PSCD/PSCA`; AH closing line `AHCh`; `PCAHH/PCAHA`, `B365CAHH/B365CAHA`) confirmed against the live CSV header `https://www.football-data.co.uk/mmz4281/2324/E0.csv`. No native DNB column in either source.
8. Jullien, B., & Salanié, B. (1994). Measuring the Incidence of Insider Trading: A Comment on Shin. *The Economic Journal* 104(427): 1418–1419. DOI [10.2307/2235458](https://doi.org/10.2307/2235458) (verified via CrossRef). (Non-linear inversion / closed form for Shin probabilities.)
9. Kelly, J. L., Jr. (1956). A New Interpretation of Information Rate. *Bell System Technical Journal* 35(4): 917–926. DOI [10.1002/j.1538-7305.1956.tb03809.x](https://doi.org/10.1002/j.1538-7305.1956.tb03809.x). (Kelly criterion / log-optimal growth.)
10. Kızıldemir, M., Akın, E., & Alkan, A. (2024). A Family of Solutions Related to Shin's Model for Probability Forecasts. Cambridge Open Engage preprint. DOI [10.33774/coe-2024-dwb6t](https://doi.org/10.33774/coe-2024-dwb6t). (Restates Shin `n=2` closed form, eqs. 2.3–2.5; `n≥3` extensions. Note: preprint, not peer-reviewed — used only to corroborate the Jullien–Salanié closed form already in refs 8, 14, 16.)
11. Lindstrøm, J. (2023). `implied`: Convert Between Bookmaker Odds and Probabilities (R package, CRAN, v0.5). URL [https://cran.r-project.org/web/packages/implied/](https://cran.r-project.org/web/packages/implied/). (Reference implementation and attributions: basic, Shin, `or`=Cheung 2015, `power`=Buchdahl logarithmic, additive=Clarke, `bb`=Fingleton–Waldron.)
12. Lo, A. W. (2002). The Statistics of Sharpe Ratios. *Financial Analysts Journal* 58(4): 36–52. DOI [10.2469/faj.v58.n4.2453](https://doi.org/10.2469/faj.v58.n4.2453). (Sharpe-ratio asymptotic SE; used in edge inference.)
13. Ottaviani, M., & Sørensen, P. N. (2008). The Favorite-Longshot Bias: An Overview of the Main Explanations. In *Handbook of Sports and Lottery Markets* (Elsevier), ch. 9, pp. 83–101. DOI [10.1016/B978-044450744-0.50009-3](https://doi.org/10.1016/B978-044450744-0.50009-3) (verified via CrossRef: title, authors Marco Ottaviani & Peter Norman Sørensen, container *Handbook of Sports and Lottery Markets*, pp. 83–101; ScienceDirect PII B9780444507440500093). Open-access working-paper mirror: [https://web.econ.ku.dk/sorensen/papers/FLBsurvey.pdf](https://web.econ.ku.dk/sorensen/papers/FLBsurvey.pdf).
14. Pinnacle. Betting rules (soccer match-market settlement: 90 minutes incl. stoppage, excl. extra time/penalties). URL [https://www.pinnacle.com/en/future/betting-rules](https://www.pinnacle.com/en/future/betting-rules). (Corroborated by Betfair *Football – 90 Minute Rule*, [https://support.betfair.com/app/answers/detail/10264](https://support.betfair.com/app/answers/detail/10264-football---90-minute-rule/).)
15. Shin, H. S. (1992). Prices of State Contingent Claims with Insider Traders, and the Favourite-Longshot Bias. *The Economic Journal* 102(411): 426–435. DOI [10.2307/2234526](https://doi.org/10.2307/2234526).
16. Shin, H. S. (1993). Measuring the Incidence of Insider Trading in a Market for State-Contingent Claims. *The Economic Journal* 103(420): 1141–1153. DOI [10.2307/2234240](https://doi.org/10.2307/2234240) (verified via CrossRef).
17. Snowberg, E., & Wolfers, J. (2010). Explaining the Favorite-Long Shot Bias: Is It Risk-Love or Misperceptions? *Journal of Political Economy* 118(4): 723–746. DOI [10.1086/655844](https://doi.org/10.1086/655844).
18. Štrumbelj, E. (2014). On Determining Probability Forecasts from Betting Odds. *International Journal of Forecasting* 30(4): 934–943. DOI [10.1016/j.ijforecast.2014.02.008](https://doi.org/10.1016/j.ijforecast.2014.02.008). (Shin > basic normalisation for soccer; fixed-point `z`.)
19. Vovk, V., & Zhdanov, F. (2009). Prediction with Expert Advice for the Brier Game. *Journal of Machine Learning Research* 10: 2445–2471. URL [https://jmlr.org/papers/v10/vovk09a.html](https://jmlr.org/papers/v10/vovk09a.html). (Power-transform basis for the logarithmic de-vig; as cited by Clarke et al. 2017.)

---

## Open questions and assumptions to validate

1. **DOI status.** Shin (1992) `10.2307/2234526`, Shin (1993) `10.2307/2234240`, and Jullien–Salanié (1994) `10.2307/2235458` were each **verified against CrossRef** (`api.crossref.org/works/<doi>`) during this research; an earlier inferred Shin-1993 DOI (`…/2234717`) was found to resolve to an unrelated editorial note and was corrected. **Ottaviani–Sørensen (2008) required a DOI correction:** the originally recorded chapter DOI `10.1016/B978-044450744-0.50007-1` returned HTTP 404 on both CrossRef and doi.org (it did not resolve to any record); the correct chapter DOI is `10.1016/B978-044450744-0.50009-3` (chapter 9, pp. 83–101, PII B9780444507440500093), now CrossRef-verified and used in ref 13. The earlier preamble/self-attestation that *all* DOIs were confirmed during research did **not** hold for this entry and is retracted for it. The remaining non-`10.2307/*` DOIs in the reference list (Bailey–LdP, Štrumbelj, Lo, Cain–Law–Peel, Snowberg–Wolfers, Clarke et al., Arrow, Kelly, Kızıldemir) are publisher DOIs independently confirmed correct via CrossRef during the audit; all should still be round-tripped through `/cite-add` before the CITATION.cff commit, and the corrected Ottaviani–Sørensen DOI re-checked at that point.
2. **Cheung (2015) primary citation.** The odds-ratio method's only stable attribution is the CRAN `implied` docs and Buchdahl's PDF; the original Sports Trading Network blog URL was not located. Either locate the primary blog post or cite via Buchdahl/Lindstrøm as secondary, and flag in the edge doc.
3. **Quoted-vs-synthetic DNB availability.** Confirm coverage and snapshot date of football-data.co.uk `AHCh = 0` (closing) / `AHh = 0` (pre-match) rows vs the synthetic-only fraction across leagues and World Cup years; the §3.5 margin wedge `M_1X2 − M_AH` should be measured empirically, not assumed, and its sign/magnitude reported. Note the closing AH line/price columns (`AHCh`, `PCAHH/PCAHA`, `B365CAHH/B365CAHA`) are present in the live CSV but not all documented in `notes.txt`, and `AHh`/`AHCh` are only populated from 2019/20 onward — pre-2019/20 league rows and all World Cup years before that depend on the synthetic `W(D−1)/D` route.
4. **De-vig method selection.** Shin is the pre-registered primary, but the choice (Shin vs power vs basic) must be entered in the multiple-testing register and its effect on the estimated edge reported as a sensitivity, since the favourite-longshot shading directly moves the underdog `p_W` and hence the EV sign.
5. **Push variance reduction, exact form — RESOLVED.** §6.2 now derives the clean identity `Var_winbet(fair) − Var_DNB(fair) = p_D·p_fav/p_W` (at the fair DNB price, `μ = 0`), verified symbolically and by 500k-draw Monte-Carlo over the full simplex (max abs error `1.9e−9`, zero sign violations). The earlier unqualified "`Var_DNB` strictly `< o−1` whenever `p_D > 0`" was corrected: it fails for arbitrarily mispriced odds (≈45% of random draws; e.g. `p_W=0.70, p_D=0.22, o=6.60` gives `Var_DNB=7.29 > o−1=5.60`) and is valid only at the fair price or in the same-odds/same-view comparison. The variance/staking module should still carry the unit test asserting the identity (`p_D·p_fav/p_W`) against simulation and asserting the violation behaviour at mispriced odds as a regression guard.
6. **Kelly under estimation error.** The §7 `f*` assumes known `(p_W, p_D)`; with Shin-estimated probabilities on a small World Cup sample, `f*` is itself a noisy estimate. Validate fractional-Kelly `λ` by walk-forward CV and consider a shrinkage/Bayesian estimate of `p` before staking (the project's Bayesian-workflow skill applies).
7. **90-minute field integrity.** Confirm that the World Cup data source records the 90-minute score separately from extra-time/penalty outcomes for knockout matches; build a unit test asserting that any penalty-decided match labels as a DNB push.
8. **Favourite-longshot bias magnitude in football DNB specifically.** Cain–Law–Peel (2000) and Ottaviani–Sørensen (2008) establish the bias for 1X2 and horse racing; its transmission into the *two-way DNB/AH-0* book (where the draw is removed) is not directly cited and should be estimated on the expanded universe before drawing EV conclusions.
