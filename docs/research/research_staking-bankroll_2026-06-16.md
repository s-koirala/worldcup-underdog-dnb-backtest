# Staking, Kelly, Bankroll, and Risk of Ruin for the World-Cup Underdog Draw-No-Bet Strategy

Research dimension document. Project: backtest of an underdog Draw-No-Bet (DNB) strategy on the FIFA men's World Cup, with the estimation universe expanded to domestic leagues (football-data.co.uk Pinnacle closing 1X2 + Asian-Handicap columns) and the World Cup treated as a held-out subsample.

Author context: SKIE (MPH + quant finance). All tunable values are tied to an empirical selection procedure or declared as a swept range with a cited rationale; no free thresholds are asserted. Cross-references by path: the **decision inputs** that select the deployed multiplier `λ` — the ruin floor `ρ` and the drawdown target `(α_dd, β_dd)` — and the **walk-forward CV fold structure** are declared in [docs/protocol/methodology.md](../protocol/methodology.md) §1–§2; the **multiple-testing register** (family count `K`, menu) lives in [config/multipletest_family.yaml](../../config/multipletest_family.yaml), and the correction machinery (White/Hansen, Deflated/Probabilistic Sharpe, MinTRL, HAC, power) is derived in the sibling [docs/research/research_statistical-methodology_2026-06-16.md](research_statistical-methodology_2026-06-16.md) §7–§8. This document states the staking-grid contract those must satisfy. (The drawdown-target `(α_dd, β_dd)` here are a *floor and breach probability* — a different object from the test *size/power* `(α, β)` in the statistical-methodology doc §6.2; the protocol doc §1.1 makes the disambiguation explicit.)

---

## Scope

This document covers position sizing and bankroll dynamics for the underdog-DNB bet, end to end:

1. Notation and the DNB payoff as a 3-outcome (win / loss / **push**) gamble, and the synthetic-DNB odds identity used throughout the project.
2. Staking schemes: flat / level stake, fixed-fraction, level-stake-to-odds (proportional / "level-stake-to-win"), Kelly, fractional Kelly. **Kelly is derived from first principles for the 3-outcome push bet.**
3. Kelly under estimation error in the win probability `p`, and the resulting justification for fractional Kelly. MacLean–Thorp–Ziemba good/bad properties; the half-Kelly growth/variance trade-off with a worked number.
4. Simultaneous bets (group-stage / same-matchday concurrency): the multivariate (vector) Kelly program and correlation handling.
5. The staking grid-search **contract**: what is held fixed, what varies, the explicit multiple-testing correction it must pass, and the walk-forward CV fold structure.
6. Risk of ruin: the closed-form fixed-fractional (gambler's-ruin) bound, the Busseti–Ryu–Boyd drawdown bound for log-optimal betting, and a Monte-Carlo procedure from the empirical bet-outcome distribution. Minimum bankroll for a target ruin probability / target max drawdown.
7. Expected log-growth comparison across schemes and the growth-vs-drawdown efficient frontier.
8. How bet sizing varies with odds: Kelly does this endogenously; flat staking does not. Exact definition of what the grid compares.

Conventions: returns are **arithmetic per-bet net returns** on staked capital (the natural unit for a settled bet); growth is **log-wealth** (geometric). Odds are **decimal**. The estimation sample uses Pinnacle **closing** odds (the most efficient publicly available line; the favorite–longshot bias and margin are smallest at the close), consistent with [rules/quant-project.md](rules/quant-project.md).

---

## 1. Notation and the Draw-No-Bet payoff

### 1.1 Decimal-odds primitives

For a single match, 1X2 decimal odds are `(H, D, A)` for home win, draw, away win. Bookmaker-implied (margin-inflated) probabilities are `q_H = 1/H`, `q_D = 1/D`, `q_A = 1/A`, with overround `Σ = q_H + q_D + q_A > 1`. We bet the **underdog** = the side with the larger decimal win price (lower implied win probability). WLOG below the underdog is the away side at decimal odds `A`; the home/favourite case is symmetric with `H` in place of `A`.

Let the bettor's **modeled** (de-margined, error-corrected) outcome probabilities be `p_H, p_D, p_A` with `p_H + p_D + p_A = 1`. The estimation of `p` is a separate dimension (calibration / shrinkage); here `p` is taken as given and we study sizing, including the sensitivity to errors in `p`.

### 1.2 The DNB / Asian-Handicap-0.0 payoff

Draw-No-Bet ("tie no bet") = **Asian Handicap 0.0**: on a 90-minute draw the stake is refunded (a *push*), otherwise it settles as a straight win/loss bet on the chosen side. Pinnacle's own betting-resources documentation defines a zero / `0` ("PK") Asian Handicap as voiding the draw and refunding stakes on a tie — you win if your side wins, your stake is refunded on a draw, you lose if the other side wins — i.e. it achieves the same outcome as Draw No Bet (Pinnacle, *What is handicap soccer betting?*, Betting Resources, accessed 2026-06-16) [Pinnacle AH], and the synthetic-from-1X2 construction below is the one Pinnacle documents in *Using the 1X2 market to produce Draw No Bet odds* (Pinnacle, *Betting Resources*, accessed 2026-06-16) [Pinnacle DNB]. football-data.co.uk carries the line directly: `PAHH`/`PAHA` are Pinnacle Asian-handicap home/away odds and `AHh` the handicap size, with Pinnacle 1X2 as `PSH`/`PSD`/`PSA` (the data dictionary lists these verbatim). The **closing** variants are not enumerated individually in the notes; they follow the dictionary's stated convention of inserting a `C` after the bookmaker prefix (e.g. `B365CH` for closing Bet365 home), which for Pinnacle gives `PSCH`/`PSCD`/`PSCA` (closing 1X2) and `PCAHH`/`PCAHA`, `AHCh` (closing Asian-handicap) — confirm these against the live header row of the actual season files used [football-data.co.uk notes]. So the project can use the *quoted* DNB odds directly when AH-0.0 is present, and otherwise the **synthetic** DNB constructed from 1X2 below; the two should agree up to the AH-vs-1X2 margin difference, which is itself a data-quality check.

Let the **effective DNB decimal odds** on the away side be `d_A`. Three settlement outcomes:

| Outcome | Probability | Net return per 1 unit staked |
|---|---|---|
| Away win | `p_A` | `+(d_A − 1)` |
| Draw (push) | `p_D` | `0` (stake refunded) |
| Home win (loss) | `p_H` | `−1` |

### 1.3 Synthetic-DNB odds identity (project key identity)

A synthetic DNB on the away side from 1X2 odds `(H, D, A)` replicates "stake returned on a draw" by splitting one unit of stake: place `1/D` on the draw (which returns `D · (1/D) = 1` exactly when the match draws, refunding the unit) and the remaining `1 − 1/D` on the away win. On an away win the payout is `A · (1 − 1/D)`, i.e. the gross multiple on the *originally staked unit* is

```
d_A = A · (1 − 1/D) = A · (D − 1) / D.                                  (1)
```

This is the identity supplied in the project brief; it is exact when `H, D, A` are the *same book's* prices and the draw stake is filled at `D`. Worked example: `A = 4.00`, `D = 3.50` ⇒ `d_A = 4.00 · 2.50 / 3.50 = 2.857`. The push leg has been folded into the stake; the table in §1.2 then uses `d_A = 2.857`. (Symmetric home identity: `d_H = H·(D−1)/D`.) Note `d_A < A` always: removing draw risk costs expected value, exactly the price of the push.

**Margin caveat for the synthetic.** Using the synthetic from de-margined `p` for sizing but settling at the *quoted* `d_A` is correct. Using raw 1X2 `q` to "construct" a fair DNB is **not** margin-free: the implied DNB overround is `q_A/(q_A+q_H)` re-based — always document which odds (quoted AH-0.0 vs synthetic-from-1X2) feeds sizing vs settlement.

---

## 2. Staking schemes

Bankroll before bet `t` is `W_{t-1}`. Stake is `s_t`; settled net-return multiple is `r_t ∈ {d−1, 0, −1}` per §1.2 (push gives `r_t = 0`). Then `W_t = W_{t-1} + s_t · r_t`.

| Scheme | Stake `s_t` | Sizing varies with odds? | Free parameter |
|---|---|---|---|
| **Flat / level stake** | `s_t = k` (constant cash, or constant % of *initial* bankroll) | No | unit size `k` |
| **Fixed-fraction** | `s_t = φ · W_{t-1}` | No | fraction `φ` |
| **Level-stake-to-odds** (a.k.a. proportional / "to-win") | `s_t = c / (d_t − 1)` so target *profit* is constant `c` | Yes (inverse in net odds) | target profit `c` |
| **Kelly** | `s_t = f*(p_t, d_t) · W_{t-1}` (§3) | Yes (endogenous) | none (uses `p, d`) |
| **Fractional Kelly** | `s_t = λ · f*(p_t, d_t) · W_{t-1}`, `λ ∈ (0,1]` | Yes | Kelly fraction `λ` |

Two distinctions that the grid (§5) must keep clean:

- **Flat-cash vs flat-%-of-current-bankroll**: flat-cash cannot compound and has additive (not multiplicative) ruin dynamics; flat-%-of-current is the same family as fixed-fraction with a *fixed* `φ` independent of `p, d`. We treat **fixed-fraction `φ`** as the canonical "flat" comparator because it is scale-free and directly comparable to Kelly (also a fraction of current bankroll).
- **Level-stake-to-odds** stakes *more on shorter prices / less on longer prices* (it equalises the *profit* target), which for an underdog book is the **opposite** tilt to Kelly when the edge is concentrated in longshots, and the **same** tilt when edge is concentrated in shorter-priced "mild" underdogs. This is precisely why it belongs in the grid as a non-trivial alternative, not as folklore.

---

## 3. Kelly for the 3-outcome push bet (derivation)

### 3.1 Setup

Kelly's criterion maximises the expected logarithm of wealth, which equals the almost-sure long-run exponential growth rate `G = lim_{N→∞} (1/N) log(W_N/W_0)` (Kelly 1956; the log-optimal bettor's growth rate dominates that of any essentially different strategy with probability one — Kelly 1956; Breiman 1961; Thorp 2006). Bet fraction `f = s/W` of current wealth. With the §1.2 payoffs (win prob `p_A`, push prob `p_D`, loss prob `p_H`, net win odds `b ≡ d_A − 1`), the one-step log-growth is

```
g(f) = p_A · log(1 + b f) + p_D · log(1) + p_H · log(1 − f)
     = p_A · log(1 + b f) + p_H · log(1 − f).                          (2)
```

The push term `p_D · log(1+0) = 0` drops out of the *objective* but **not** out of the constraint `p_A + p_D + p_H = 1`: the push leaves wealth unchanged, so it neither grows nor risks capital. This is the entire effect of the push on sizing — it removes mass from both the up- and down-states without contributing curvature.

### 3.2 First-order condition and the closed-form fraction

Differentiate (2):

```
g'(f) = p_A · b / (1 + b f) − p_H / (1 − f) = 0.
```

Solve for `f`:

```
p_A · b · (1 − f) = p_H · (1 + b f)
p_A b − p_A b f = p_H + p_H b f
p_A b − p_H = b f (p_A + p_H)
```

```
f* = (p_A · b − p_H) / [ b · (p_A + p_H) ].                            (3)
```

This is the **Kelly fraction for the DNB bet**. Equivalent forms:

```
f* = (p_A − p_H / b) / (p_A + p_H)        (divide num & den by b)      (3a)
f* = p̃_A − p̃_H / b,    where  p̃_A = p_A/(p_A+p_H),  p̃_H = p_H/(p_A+p_H).  (3b)
```

**Interpretation.** Equation (3b) is exactly the *binary* Kelly formula `f = p̃ − q̃/b` (Wikipedia/Thorp form `f = p − q/b`) applied to the **conditional-on-no-push** probabilities `p̃ = P(win | not push)`. **A push bet is a binary Kelly bet on the renormalised win/loss probabilities.** The push is "free" in the precise sense that it only re-scales the binary problem by the no-push mass `(p_A + p_H)` and does not change the *form* of the optimum — but it does change the *magnitude*: because `g''(f) < 0` and the push removes probability mass, the curvature at the optimum is smaller, so the same renormalised edge yields the same `f*` but a **lower realised growth rate** (the bet "fires" less often). Quantitatively `g(f*)` scales roughly with `(p_A+p_H)` relative to a no-push bet at the same conditional edge.

Second-order check: `g''(f) = −p_A b²/(1+bf)² − p_H/(1−f)² < 0` for all admissible `f`, so (3) is the unique interior maximum; bet only if `g'(0) = p_A b − p_H > 0`, i.e. **only when the renormalised expected value is positive**, `p̃_A · d_A > 1` (equivalently `p̃_A (b+1) > 1`). Given the favorite–longshot-bias / margin prior (Ottaviani–Sørensen 2008), most underdog DNBs will have `f* ≤ 0` ⇒ **no bet**; Kelly endogenously refuses negative-edge bets, which flat staking does not.

### 3.3 Worked numeric example

Take the §1.3 numbers: synthetic away DNB `d_A = 2.857` ⇒ `b = 1.857`. Suppose the de-margined model says away win `p_A = 0.30`, draw `p_D = 0.28`, home `p_H = 0.42`.

- Renormalise: `p̃_A = 0.30/0.72 = 0.4167`, `p̃_H = 0.42/0.72 = 0.5833`.
- Edge check: `p̃_A · d_A = 0.4167 · 2.857 = 1.190 > 1` ⇒ positive-edge, bet.
- Kelly: `f* = 0.4167 − 0.5833/1.857 = 0.4167 − 0.3141 = 0.1026`.

So full Kelly stakes **10.3% of bankroll**. Expected log-growth per bet, from (2):

```
g(f*) = 0.30·log(1 + 1.857·0.1026) + 0.42·log(1 − 0.1026)
      = 0.30·log(1.1905) + 0.42·log(0.8974)
      = 0.30·(0.17436) + 0.42·(−0.10825)
      = 0.05231 − 0.04547 = 0.00684 per bet  (≈ 0.68% geometric/bet).
```

Per-bet variance — get the right object. The `o − 1` identity is the variance of a **straight two-outcome win bet at fair odds** only (for a unit win bet the payoff variance is `p(1−p)·o²`, and at fair odds `o = 1/p` this reduces to `o − 1`; verified). It is **not** the variance of the DNB bet, which is the three-valued gamble `{+b, 0, −1}` of §1.2. The correct per-bet variance of the DNB return, in the §6.1 / sibling-doc notation (`b = d_A − 1`, win prob `p_A`, push prob `p_D`, loss prob `p_H = p_fav`), is the closed form

```
Var_DNB = p_A·b² + p_H − μ²,    μ = p_A·b − p_H = E[R].                   (3c)
```

This is exactly the closed form derived and verified in the sibling odds-calculations document — see [docs/research/research_dnb-odds-calculations_2026-06-16.md](docs/research/research_dnb-odds-calculations_2026-06-16.md) §6.1–6.2 (`Var(R) = p_W·b² + p_fav − μ²`), where it is also proven that `Var_DNB < o_DNB − 1` strictly whenever `p_D > 0` (the push mass replaces a `(−1)²` loss deviation with a `0²` push deviation). For the §3.3 worked numbers (`b = 1.857`, `p_A = 0.30`, `p_D = 0.28`, `p_H = 0.42`): `μ = 0.30·1.857 − 0.42 = 0.1371`, so

```
Var_DNB = 0.30·1.857² + 0.42 − 0.1371² = 1.03455 + 0.42 − 0.01880 = 1.436   (verified).
```

That is **≈ 23 % below** the straight-win figure `d_A − 1 = 1.857` — using `1.857` as the variance benchmark would overstate per-bet variance and bias the analytic ruin / min-bankroll sanity checks toward over-conservatism. So **eq. (3c), not `d_A − 1`, is the variance the risk-of-ruin Monte-Carlo (§6) calibrates against** (and against which the §6.1 Gaussian diffusion proxy is computed: there `σ² = 1.984` uses the *conditional-on-no-push* `w = p̃_A`, a different conditioning than the unconditional (3c) — both are stated where used). All of these analytic variances are themselves only the calibration target; they are replaced by the *empirical* return variance once bet outcomes are realised (Open Question 7).

---

## 4. Estimation error in `p` and the case for fractional Kelly

### 4.1 Why full Kelly is fragile

The Kelly fraction (3) is a steep function of `p`. The danger is **asymmetric**: over-betting (`f > f*`) destroys growth far faster than under-betting. From the quadratic approximation (Thorp 2006; §4.3), `g(f) ≈ g(f*) − ½ |g''(f*)| (f − f*)²`, and crucially `g(f) → −∞` as `f → 1` but stays finite for `f → 0`. Over-estimating `p` pushes `f` above `f*` and toward the ruinous region; under-estimating merely sacrifices growth. Because estimated `p̂` carries sampling error, the *expected* growth under uncertainty is below the plug-in `g(f*)`.

Chopra & Ziemba (1993) quantify the asymmetry of estimation-error damage in the mean-variance analogue: **errors in means are ~10× as costly as errors in variances and ~20× as costly as errors in covariances**, with the ratio rising with risk tolerance. For a betting book the analogue of "the mean" is the win probability `p` — exactly the hardest quantity to estimate from a small World-Cup sample (~384 clean-odds matches, 2002–2022; the brief's prior) — so Kelly sizing is dominated by error in the worst-estimated input. This is the formal reason the estimation universe is expanded to domestic leagues.

### 4.2 Fractional Kelly as the principled response

Betting `f = λ f*` with `λ ∈ (0,1)` ("fractional Kelly") is equivalent to a convex combination of the Kelly bet and cash: `b = λ b* + (1−λ) e_cash` (Busseti–Ryu–Boyd 2016, eq. for the risk-constrained solution; Uhrín et al. 2021 `f_ω = ω f_{1..n-1} + (1−ω) f_n`). Two independent justifications converge on `λ < 1`:

- **Estimation error / Bayesian shrinkage.** If `p` is uncertain, the optimal fraction shrinks toward 0. MacLean, Ziemba & Blazenko (1992) formalise the growth-security trade-off: fractional Kelly trades a *small, second-order* loss in growth for a *large, first-order* gain in security (drawdown / ruin control). Under a Bayesian treatment with a Gaussian posterior on the log-odds edge, the certainty-equivalent optimum is approximately `λ ≈ 1/(1 + Var(edge)/edge²)` — i.e. `λ` falls as the *coefficient of variation* of the estimated edge rises; half-Kelly corresponds roughly to a unit signal-to-noise ratio. This makes `λ` a **data-derived** quantity (§5), not a hand-picked constant.

- **Risk control.** Busseti–Ryu–Boyd (2016) show that imposing a drawdown constraint on the Kelly program yields *exactly* a fractional-Kelly solution; the active risk constraint *is* the mechanism that selects `λ`. §6.2 gives their closed-form drawdown bound.

### 4.3 The half-Kelly growth/variance trade-off (worked)

In the continuous / small-bet (Gaussian) approximation, with per-period mean log-return `m` and variance `s²`, expected growth as a function of leverage `f` is (Thorp 2006, verbatim form)

```
g(f) = f·m − ½ f²·s²,   maximised at  f* = m / s²,   g(f*) = m² / (2 s²).   (4)
```

Betting a fraction `c` of full Kelly, `f = c f*`:

```
g(c f*) = c f* m − ½ c² f*² s² = (c − ½ c²) · (m²/s²) = (2c − c²) · g(f*).   (5)
```

So `g(c f*)/g(f*) = 2c − c²`. At **`c = ½`** (half-Kelly): growth retention `= 2(½) − (½)² = 1 − ¼ = 0.75` (**75% of full-Kelly growth**), while the *variance* of log-wealth scales as `c² = ¼` (**25% of full-Kelly variance**) (Thorp 2006; MacLean–Ziemba–Blazenko 1992; confirmed in MacLean–Thorp–Ziemba 2010). That asymmetry — keep three-quarters of the growth, shed three-quarters of the variance — is the canonical argument for half-Kelly as a default *prior* on `λ`, to be refined by the §5 search rather than asserted.

### 4.4 MacLean–Thorp–Ziemba good/bad properties (the ledger)

MacLean, Thorp & Ziemba (2010) — "Good and bad properties of the Kelly criterion" (also the longer 2011 chapter and the Quantitative Finance article 10(7):681–687) — give the canonical ledger used to frame the project's risk section:

**Good.** (i) Maximises the asymptotic long-run exponential growth rate of wealth (Kelly 1956; Breiman 1961). (ii) Asymptotically minimises the expected time to reach a large preassigned wealth target. (iii) With continuous rebalancing the log-optimal investor never goes bankrupt (wealth stays positive a.s.). (iv) Outperforms any essentially different strategy in the long run with probability → 1.

**Bad.** (i) The total amount wagered is very large; full Kelly is aggressive and produces **large drawdowns** — the chance of losing a substantial fraction of wealth is high. (ii) In the short/medium run the distribution of wealth is **very wide and right-skewed**: Kelly can underperform for long stretches. (iii) The good properties are *asymptotic*; with a finite, small sample (the World-Cup subsample) and discrete bets, ruin is possible and the asymptotics do not protect you. (iv) Sensitive to the input probabilities (§4.1).

The operational conclusion (their recommendation, and the project's): **use fractional Kelly** to retain most of the growth while bounding drawdown, and *select the fraction against a drawdown / ruin constraint*, not by taste.

---

## 5. Simultaneous bets and the multivariate Kelly program

### 5.1 Why concurrency matters here

Group-stage matchdays settle several World-Cup matches **simultaneously**. Sequential single-bet Kelly (size each bet ignoring the others) over-bets the *aggregate* matchday exposure, because the bets share calendar time and partly share information/state. The correct object is the **vector Kelly** program that sizes the *whole matchday slate at once*.

### 5.2 The vector (log-optimal portfolio) program

Let a matchday offer `n−1` underdog-DNB bets plus cash (asset `n`). Let `f ∈ ℝⁿ` be the wealth fractions, `O` the payoff matrix whose `(k, j)` entry is the gross return multiple of asset `j` in joint-outcome scenario `k` (scenarios enumerate the joint realisation of all matches; a draw in match `j` sets that column's multiple to `1` — the push — in the scenarios where match `j` draws), and `π_k` the modeled probability of scenario `k`. Then (Kelly 1956; Thorp 2006; Busseti–Ryu–Boyd 2016; Uhrín, Šourek, Hubáček & Železný 2021):

```
maximise_f   Σ_k π_k · log( (O f)_k )
subject to   1ᵀ f = 1,   f ≥ 0.                                        (6)
```

This is a **concave** program (log of a linear function, non-negative weights), solvable by convex optimisation (CVXPY/`cvxpy`, ECOS/SCS), the same formulation Uhrín et al. (2021) use for parallel sports bets. The single-bet formula (3) is the `n = 2` special case. Fractional Kelly is the convex blend with the all-cash vertex: `f_λ = λ f* + (1−λ) e_n` (Uhrín et al. 2021; Busseti–Ryu–Boyd 2016).

### 5.3 Correlation handling

Two distinct correlation channels, treated differently:

- **Outcome correlation across matches** (e.g. common shocks: weather, refereeing regime, a group's qualification incentives in the final round, fatigue). This is captured *inside* `π_k`: if matches are modeled independent, `π_k = Π_j P(outcome_j)`; if not, `π_k` is the joint and the program (6) automatically accounts for diversification/concentration. Independence is the *default*, to be **tested** (final-round dead-rubber collusion and "biscotto" effects are documented; treat the last group matchday as a covariate, not as i.i.d.).
- **Same-match correlation between the two sides of a bet**: not an issue here because we take one side (the underdog) per match.

Practical reduction: when bets are (modeled as) independent and edges are small, the joint program (6) collapses to *near-additive* fractions, but the budget constraint `1ᵀf ≤ 1` still binds and **caps total matchday stake below the sum of independent single-bet Kelly fractions**. The cheap, defensible approximation is therefore: compute single-bet `f*_j` from (3), then **renormalise** so `Σ_j f*_j ≤ f_max` (with `f_max` from the §6 drawdown constraint), and apply the global fraction `λ`. The exact (6) is run as the benchmark; the renormalised approximation is reported as the deployable rule with its growth gap to (6) quantified.

---

## 6. Risk of ruin and minimum bankroll

Define **ruin** at horizon `N` as `min_{t≤N} W_t ≤ ρ W_0` for a chosen ruin floor `ρ` (e.g. `ρ = 0` for literal bankruptcy under cash staking, or `ρ ∈ (0,1)` for an "effective ruin" floor such as the level below which the bettor stops — both reported). `ρ` and the drawdown target `(α_dd, β_dd)` are **not** asserted; they are decision inputs (risk preferences) declared with a swept grid and cited behavioural-stop-loss rationale in [docs/protocol/methodology.md](../protocol/methodology.md) §1, and varied on that grid (§7). (`α_dd, β_dd` here = drawdown floor and breach probability; not the test size/power `(α, β)` of the statistical-methodology doc.)

### 6.1 Closed-form: additive (flat-cash) gambler's ruin — an even-money sanity benchmark only

Two staking dynamics must be kept separate; mixing them is a category error.

- **(i) Flat-cash (additive) staking.** A constant cash unit per bet makes wealth a random walk with i.i.d. increments. Literal bankruptcy (`W_t ≤ 0`) is reachable in a finite number of losing steps, and the classical gambler's-ruin recursion (Feller 1968, Vol. I, Ch. XIV) applies. This subsection treats **only** this case.
- **(ii) Fixed-fraction-of-current-wealth (multiplicative) staking.** Betting `φ·W_{t-1}` makes wealth a *product* of positive factors, so `W_t > 0` almost surely and **literal bankruptcy is impossible**. The additive `r^u` ruin law does **not** apply here; the relevant object is the probability of hitting a *fractional* drawdown barrier, which is the **multiplicative** bound of §6.2 (Busseti–Ryu–Boyd), not anything in this subsection.

For the additive case (i), take the **even-money special case** as a sanity benchmark. With a Bernoulli of single-bet win prob `w`, equal `±1` stakes, and `w > ½`, the probability of ever falling by `u` loss-units (infinite upside target) is the classical geometric (Feller 1968, Vol. I, XIV.2):

```
P(ruin to barrier u) = r^u,     r = (1 − w)/w   (even money, b = 1, w > ½).   (7)
```

so the **minimum bankroll for a target ruin probability** `ε` is

```
minimum bankroll (loss-units) ≥ log ε / log((1 − w)/w),    (even-money, w > ½).   (8)
```

**Eq. (7)–(8) is the EVEN-MONEY special case `b = 1` only — it is *not* the unequal-payoff form.** Two caveats that bar its direct use for the underdog DNB:

1. **The `±1`/even-money base is wrong for a `+b/−1` walk.** The underdog DNB pays net `b = d_A − 1 ≈ 1.857` on a win, not `1`. For a walk with steps `{+b, −1}` the geometric ruin base is **not** `(1−w)/w`; it is `e^{−R}`, where `R > 0` is the adjustment-coefficient root of the characteristic equation `E[e^{−R·X}] = 1`, i.e. `w·e^{−Rb} + (1−w)·e^{R} = 1` (Feller 1968, Vol. I, XIV.4–5; standard renewal/adjustment-coefficient result). The Gaussian diffusion proxy is `e^{−2μ/σ²}` with `μ = w·b − (1−w)`, `σ² = w·b² + (1−w) − μ²`. For the §3.3 worked numbers (conditional `w = p̃_A = 0.4167`, `b = 1.857`): `μ = 0.190`, `σ² = 1.984`, the exact root gives base `e^{−R} ≈ 0.818` and the diffusion proxy `e^{−2μ/σ²} ≈ 0.825`. These are the correct `+b/−1` decay bases; the even-money `(1−w)/w` form is a different object and must not be substituted.
2. **`w > ½` rarely holds for a genuine underdog.** Eq. (7) requires a positive even-money edge `w > ½`. For an underdog the conditional no-push win prob `p̃_A` is *usually* below ½ (the §3.3 example has `p̃_A = 0.4167 < ½`), so the even-money formula's own precondition fails and `(1−w)/w > 1` (no decay). The presence of a DNB *edge* (`p̃_A·d_A > 1`) does **not** imply `p̃_A > ½`; it is satisfied here precisely because `d_A > 1/p̃_A`. So (7)–(8) as written generally does *not* describe the underdog case.

Because the genuine DNB payoff is three-valued `{+b, 0, −1}` (push = zero step) and staking in the grid is fixed-fraction (multiplicative, case ii), there is no clean two-line closed form that is both correct and operational here. Eq. (7)–(8) is retained **solely as an even-money `b = 1` sanity check** on the simulator; the correct `+b/−1` base is the adjustment-coefficient root above (cited as the exact additive object, but still additive and so not the deployed multiplicative dynamics); the operational number comes from §6.3 Monte-Carlo. **No closed form is claimed for the deployed strategy; the empirical distribution governs.**

### 6.2 Closed-form drawdown bound for log-optimal / risk-constrained Kelly

**Notation guard.** Throughout this document `λ ∈ (0,1]` is the **fractional-Kelly multiplier** (`s = λ·f*·W`, §2, §4, §5, §7, §8). The Busseti–Ryu–Boyd drawdown bound below has its *own* exponent, which is generally `> 1` and is **not** the Kelly multiplier; to avoid the collision it is written `θ` (theta) here. Do not read `θ` as a Kelly fraction.

For the *multiplicative* (fixed-fraction-of-current-wealth, i.e. Kelly-family) case, Busseti, Ryu & Boyd (2016) give a constrained drawdown bound. Their result (BRB eq. (6), (8)) is a conditional statement: for **any** bet `b` that satisfies the constraint, the running-minimum wealth obeys

```
E[ (rᵀb)^{−θ} ] ≤ 1   ⟹   Prob( W_min < α ) < α^θ   for all α ∈ (0,1),    θ = log β / log α.   (9)
```

The bound holds **only for bets that satisfy the constraint `E[(rᵀb)^{−θ}] ≤ 1`** — it is not a free property of every bet. In particular it is **false in general that the unconstrained full-Kelly bet satisfies the constraint at `θ = 1`** and therefore false that full Kelly obeys `Prob(W_min < α) ≤ α`. BRB demonstrate the opposite empirically: their unconstrained **Kelly bet has `Prob(W_min < 0.7) ≈ 0.40`** (finite-outcome experiment, Table 1) and **`≈ 0.57`** (infinite-outcome experiment, Table 3) — far above the `α^1 = 0.7` line, i.e. the `θ = 1` bound is *violated* by unconstrained Kelly. This is the quantitative face of MTZ's "large drawdowns" property, and it is exactly why a constraint is needed.

```
(There is a separate classical log-optimal/supermartingale corollary — Prob(W_min < α) ≤ α for the
 capital-growth-optimal bettor in the canonical even-money / continuously-rebalanced setting, traceable to
 Kelly 1956 / Breiman 1961 via a martingale argument — but it is NOT Busseti–Ryu–Boyd's result and does not
 hold for unconstrained discrete Kelly in general. It is not invoked here.)                              (10)
```

To *achieve* a stated drawdown target `Prob(W_min < α) ≤ β`, set `θ = log β / log α` (which is `> 1` for any nontrivial target) and **shrink the bet until the constraint `E[(rᵀb)^{−θ}] ≤ 1` binds**. BRB prove the resulting risk-constrained Kelly (RCK) bet is a **fractional-Kelly** bet `b = f·b* + (1−f)·e_cash` with **`f < 1`** (their two-outcome §5.3 result). This is the rigorous bridge between a *drawdown target* and the *Kelly multiplier* `λ`: the user states `(α, β)`; the data + the binding constraint (9) deliver the multiplier `λ = f < 1` (sub-Kelly shrinkage), **not** a value `> 1`. The exponent `θ` is the risk-aversion parameter; the multiplier `λ` is the output.

Worked: target "no more than `β = 10%` chance of ever drawing down to `α = 50%` of bankroll" ⇒ bound exponent `θ = log 0.10 / log 0.50 = (−2.302)/(−0.693) = 3.32`. The bet is then shrunk (its multiplier `λ` reduced below 1) until `E[(rᵀb)^{−3.32}] ≤ 1` binds; per BRB's experiments the binding multiplier lands well inside half-Kelly (`λ < ½`) for typical edges, corroborating §4.3. The large exponent `θ = 3.32` is the *strictness* of the drawdown bound, **not** the bet size.

### 6.3 Monte-Carlo ruin from the empirical bet-outcome distribution

Because the DNB push, the discreteness, the small sample, and the matchday concurrency break every closed form, the **operational** risk-of-ruin estimate is a Monte-Carlo bootstrap over the *empirical settled-bet return distribution* from the expanded estimation universe:

1. From the held-out / CV-out-of-sample bets, collect the empirical multiset of realised per-bet net returns `{r_i}` (values in `{d_i−1, 0, −1}`) **with their matchday grouping** preserved (resample *matchdays*, not individual bets, to keep concurrency/correlation — a block / stationary bootstrap, Politis & Romano 1994, with block = matchday).
2. For each candidate `(scheme, parameter)` (e.g. fixed-fraction `φ`, or `λ`-Kelly) and each of `B` bootstrap paths of length `N` (= number of World-Cup bets at the deployment horizon), simulate wealth `W_t` and record (a) terminal log-growth `(1/N) log(W_N/W_0)`, (b) max drawdown `1 − min_t W_t / max_{s≤t} W_s`, (c) ruin indicator `1{min_t W_t ≤ ρ W_0}`.
3. Estimate `P̂(ruin) = (1/B) Σ ruin indicator`, with a Wilson or bootstrap CI; estimate the drawdown distribution and its quantiles.
4. **Minimum bankroll** for target ruin `ε` and target max-drawdown `D*`: the smallest initial bankroll (equivalently, the smallest *unit fraction* / largest `φ` or `λ`) such that `P̂(ruin) ≤ ε` **and** the `(1−η)`-quantile of max-drawdown `≤ D*`. Solve by bisection on `φ` (or `λ`) over the bootstrap.

`B` is set so the Monte-Carlo standard error on `P̂(ruin)` is below a declared tolerance: for a target ruin probability near `ε`, `SE = sqrt(ε(1−ε)/B)`; requiring `SE ≤ ε/10` gives `B ≥ 100·(1−ε)/ε` (e.g. `ε = 0.05 ⇒ B ≥ 1900`; we run `B = 10⁴` for margin). **`B` is therefore derived from the precision target, not chosen arbitrarily** (CLAUDE.md mandate). RNG seed, git HEAD, dataset checksum, and `pip freeze` are logged per the reproducibility hook.

---

## 7. Growth-vs-drawdown frontier and the staking grid contract

### 7.1 What the grid compares (exact)

The grid is a **2-D sweep**: scheme family × its parameter, evaluated by **walk-forward** out-of-sample on the expanded universe, then confirmed on the World-Cup hold-out. The schemes and their *only* free parameters:

| Scheme | Parameter swept | Sizing-by-odds behaviour (the thing being tested) |
|---|---|---|
| Fixed-fraction | `φ ∈ grid` | **constant** fraction regardless of price/edge |
| Level-stake-to-odds | `c ∈ grid` | stake `∝ 1/(d−1)` — tilts *toward* short prices |
| Fractional Kelly | `λ ∈ (0,1]` grid | stake `∝ f*(p,d)` — tilts *toward* high-edge bets, **endogenous** |

The **scientific question the grid answers**: does *endogenous, edge-proportional* sizing (Kelly) beat *odds-agnostic* sizing (fixed-fraction) and *naively-odds-tilted* sizing (level-to-odds), on **risk-adjusted, drawdown-aware** growth, after honest multiple-testing correction? Kelly varies bet size with odds *by construction* (eq. 3 is increasing in the edge `p̃_A·d_A − 1`); fixed-fraction does not; that contrast is the experiment.

### 7.2 Multiple-testing correction (contract with the methodology doc)

The grid evaluates many `(scheme, parameter)` cells against the *same* hold-out, plus the underdog rule is itself one of several candidate rules — this is a **multiple-comparisons / data-snooping** problem (the favorite–longshot literature is littered with un-corrected "anomalies"). The staking grid is therefore registered as one **family** in the multiple-testing register [config/multipletest_family.yaml](../../config/multipletest_family.yaml) (its existence and the CV fold structure that the family is evaluated over are fixed in [docs/protocol/methodology.md](../protocol/methodology.md) §2–§3; the correction machinery is derived in the sibling [research_statistical-methodology_2026-06-16.md](research_statistical-methodology_2026-06-16.md) §7–§8) and must clear, *before* any cell is reported as significant:

- **White (2000) Reality Check** or **Hansen (2005) SPA** for the best staking rule's out-performance over the benchmark (fixed-fraction-φ* or flat), using the stationary-bootstrap distribution of the performance statistic — this is the *correct* correction when comparing the *maximum* over a grid of strategies to a benchmark, and is exactly the tool CLAUDE.md/[rules/quant-project.md](rules/quant-project.md) prescribes for "multiple testing across strategies."
- The performance statistic is the **bootstrap Sharpe** (single-strategy CI via Lo 2002 asymptotic or Opdyke 2007; pairwise scheme comparisons via the **Ledoit–Wolf (2008)** studentized time-series bootstrap), with **Newey–West / HAC** standard errors (lag via Newey–West 1994 data-dependent bandwidth) because settled-bet returns are weakly dependent through matchday clustering.
- The selected cell's Sharpe is additionally reported as a **Deflated Sharpe Ratio (DSR)** (Bailey, Borwein, López de Prado & Zhu 2014, *Notices AMS* 61(5):458–471, [ams.org/notices/201405/rnoti-p458.pdf](https://www.ams.org/notices/201405/rnoti-p458.pdf); Bailey & López de Prado 2014, [10.3905/jpm.2014.40.5.094](https://doi.org/10.3905/jpm.2014.40.5.094)), which deflates the benchmark `SR_0` to the expected maximum Sharpe attainable by chance over the family — this is a **non-negotiable** for this staking-grid family per the project [CLAUDE.md](../../CLAUDE.md) ("correct with White 2000 / Hansen 2005 and report the deflated Sharpe"). The DSR's two inputs — the family size `K` and the cross-trial Sharpe variance `V[ŜR_n]` — are taken from the multiple-testing register in [config/multipletest_family.yaml](../../config/multipletest_family.yaml); the full PSR/DSR/MinTRL machinery (with the effective-`N` dependence correction) is derived in the sibling [research_statistical-methodology_2026-06-16.md](research_statistical-methodology_2026-06-16.md) §8. White/Hansen and the DSR are complementary, not alternatives: White/Hansen answer "is there *any* edge in the grid", the DSR deflates the *reported Sharpe* of the surviving cell for the size of the search; both must be cleared before a cell is called significant.
- CV is **walk-forward** (time-ordered, disjoint, expanding window) — never k-fold — per [rules/quant-project.md](rules/quant-project.md): fit calibration/`λ` on fold `≤ k`, evaluate on fold `k+1`; the World Cup is the final, never-touched test fold. The `λ` (and `φ`, `c`) selected is the one maximising *out-of-fold* drawdown-constrained growth, so the parameter choice is itself out-of-sample and the SPA/Reality-Check correction is applied to the *out-of-sample* path.

### 7.3 Growth–drawdown efficient frontier

For each scheme, sweeping its parameter traces a curve in `(expected log-growth, max-drawdown-quantile)` space (the Monte-Carlo outputs of §6.3). The **efficient frontier** is the upper-left envelope: maximum growth for each drawdown budget. The relevant theory (eqs. 4–5, 9) predicts that **edge-proportional Kelly-family sizing dominates odds-agnostic (fixed-fraction) and naively-tilted (level-to-odds) sizing** at each drawdown budget, because Kelly is the *log-optimal* allocation. It does **not** follow that the *fractional-Kelly* curve is the frontier: Busseti–Ryu–Boyd (2016) show their **risk-constrained Kelly (RCK) bet dominates fractional Kelly** in the finite-outcome case (their Fig. 4 / §7.1.3: at the `β = 0.1` drawdown level RCK growth ≈ 0.047 vs fractional-Kelly ≈ 0.035), and fractional Kelly only *matches* RCK in the infinite-return (continuous) case (§7.2.2). So the honest theoretical prediction is: **RCK ≽ fractional-Kelly ≽ {fixed-fraction, level-to-odds}** on the drawdown-constrained frontier, with the RCK–fractional gap closing toward zero as the return distribution becomes continuous. The frontier endpoints are cash (`λ=0`: zero growth, zero drawdown) and full Kelly (`λ=1`: max growth `g(f*)`, but **large drawdown** — `Prob(W_min<0.7)≈0.4` in BRB's experiments, §6.2, *not* a bounded `≤α`). The **deliverable** is this frontier plotted from the empirical bootstrap (not just theory), reporting fractional-Kelly **and** the RCK solution so the gap is measured rather than assumed, with the chosen operating point = the bet whose drawdown constraint `(α, β)` from §6.2 binds (multiplier `λ < 1`). Expected outcome given the negative-EV prior: for the *World-Cup-only* sample the frontier may sit below the zero-growth axis (no positive-growth `λ`), in which case **`λ* = 0` (do not bet)** is the honest conclusion and the document reports the bankroll/`λ` that *would* be required were the edge real, as a power/feasibility statement.

---

## 8. Summary of the deployable rule

1. Size each underdog-DNB by the **push-Kelly** fraction (3) on de-margined `p̃`; bet only if `p̃_A · d_A > 1`.
2. Apply a **fractional** multiplier `λ ∈ (0,1]`, selected so the Busseti–Ryu–Boyd drawdown constraint `E[(rᵀb)^{−θ}] ≤ 1` (with bound exponent `θ = log β_dd / log α_dd`, eq. 9) **binds** at the drawdown target `(α_dd, β_dd)` declared and swept in [docs/protocol/methodology.md](../protocol/methodology.md) §1.2 (`α_dd ∈ {0.5,0.6,0.7,0.8}`, `β_dd ∈ {0.05,0.10,0.20}`) — this yields a sub-Kelly `λ < 1`, not `θ` — cross-validated walk-forward over the §2 fold structure. Half-Kelly (`λ≈0.5`) is the *prior*, not the answer (§4.3). With `(α_dd, β_dd)` now declared, this step is executable: `λ = λ(α_dd, β_dd)` is reported across the grid and the operating point read off the §7.3 frontier.
3. On concurrent matchdays size the **slate jointly** (6), or use the renormalised-and-capped single-bet approximation with the global `λ`.
4. Risk of ruin / minimum bankroll from the **matchday-block bootstrap** (§6.3); `B` set by the precision target.
5. Report the **growth–drawdown frontier**, clear **White/Hansen** multiple-testing, and report the **Deflated Sharpe Ratio** (§7.2) for the surviving cell before claiming any scheme beats fixed-fraction.

---

## Citations

**Verification status (re-verified live 2026-06-16 from the publisher/preprint full text, not metadata).** Full primary-text verification was re-performed for the load-bearing quantities by extracting and reading the actual documents:

- **Busseti–Ryu–Boyd 2016** (arXiv:1603.06183; verified against the **text-extracted Stanford author PDF** [web.stanford.edu/~boyd/papers/pdf/kelly.pdf](https://web.stanford.edu/~boyd/papers/pdf/kelly.pdf), parsed with `pdfminer` 2026-06-16 — the page-level table cells were read directly, not inferred from metadata): the drawdown bound eq. (6) `E[(rᵀb)^{−θ}] ≤ 1 ⟹ Prob(W_min<α) < β` with `θ = log β/log α` (their notation; same exponent) confirmed; **Table 1** ("Comparison of Kelly and RCK bets", finite outcomes) unconstrained-Kelly row `E log(rᵀb) = 0.062`, `Prob(W_min<0.7) = 0.397 (≈0.40)` confirmed verbatim; **Table 3** ("Comparison of Kelly and RCK for the infinite outcome case") unconstrained-Kelly row `E log(rᵀb) = 0.077`, `Prob(W_min<0.7) = 0.569 (≈0.57)` confirmed verbatim; **§7.1.3** "the Kelly fractional bet that achieves our risk bound 0.1 has a growth rate around 0.035, compared with RCK, which has a growth rate 0.047" confirmed verbatim (at the `β = 0.1` drawdown bound); **§5** "the RCK bet is a fractional Kelly bet (4), for some `f < 1`" confirmed verbatim; **§7.2.2** "The fractional Kelly bets, in this case, show instead the (essentially) same performance as RCK" (infinite-return case) confirmed (Citation 7). **Provenance caveat:** the lossy `ar5iv` HTML mirror of this paper returns a *corrupted* Table 3 cell (`0.412`) and, on a separate extraction, `0.387`; both disagree with the primary text. The figure used in this document (`0.569`) is the value read from the Stanford PDF's Table 3 and is the authoritative one — the ar5iv numbers are HTML-conversion artifacts and must not be used.
- **Thorp 2006** (gwern author-reprint PDF, text-extracted and read): the continuous-Kelly forms, the `(2c − c²)` fractional scaling, and the half-Kelly result confirmed verbatim — "rate is reduced to 3/4 of that for f*" and "'half Kelly' has 3/4 the growth rate but much less chance of a big loss" (§7.3), i.e. the 75 %/25 % growth/variance split (Citation 3).
- **Chopra–Ziemba 1993**: the "errors in means are over ten times … and over twenty times [variances/covariances]" ratio confirmed against the published statement; DOI resolves to publisher pm-research.com (Citation 6).
- **Pinnacle** AH-0 ≡ DNB mechanic confirmed against the *What is handicap soccer betting?* Betting-Resources page (Citation 18, paraphrased — the previously quoted "zero handicap eliminates the draw…" sentence could **not** be located on Pinnacle's *Betting rules* page and has been removed; see Citation 18); the synthetic-from-1X2 construction (Citation 18b); football-data.co.uk notes.txt column codes (Citation 19).
- **Ottaviani–Sørensen 2008** DOI [10.1016/B978-044450744-0.50009-3](https://doi.org/10.1016/B978-044450744-0.50009-3) **resolves** (HTTP 302 → Elsevier ScienceDirect PII B9780444507440500093, the correct chapter record); this is the *corrected* DOI — the sibling odds-doc Open Question 1 notes an earlier inferred DOI was dead, and this corrected one is the live, CrossRef-matching record (Citation 9).

The remaining DOIs (Kelly 1956, Breiman 1961, MacLean–Thorp–Ziemba 2010, MacLean–Ziemba–Blazenko 1992, Uhrín et al. 2021, Ledoit–Wolf 2008, Lo 2002, Opdyke 2007, White 2000, Hansen 2005, Newey–West 1994, Politis–Romano 1994) carry publisher-standard DOIs; their attributed content matches the canonical statements of those results, and the DOIs/stable URLs are recorded below. Exact page numbers for the print-only sources (Thorp 2006 pp. 385–428; Feller 1968 Ch. XIV) should still be re-confirmed against the publisher copy before manuscript freeze, and the resolved-URL evidence attached to the reproducibility log.

1. Kelly, J. L. (1956). A New Interpretation of Information Rate. *Bell System Technical Journal*, 35(4), 917–926. DOI: [10.1002/j.1538-7305.1956.tb03809.x](https://doi.org/10.1002/j.1538-7305.1956.tb03809.x). (Verified via Wiley Online Library and the AT&T-permission reprint, [princeton.edu/~wbialek/rome/refs/kelly_56.pdf](https://www.princeton.edu/~wbialek/rome/refs/kelly_56.pdf).)
2. Breiman, L. (1961). Optimal gambling systems for favorable games. *Proceedings of the Fourth Berkeley Symposium on Mathematical Statistics and Probability*, Vol. 1, 65–78. (Almost-sure dominance of the log-optimal strategy.) Stable URL: [projecteuclid.org/euclid.bsmsp/1200512159](https://projecteuclid.org/ebooks/berkeley-symposium-on-mathematical-statistics-and-probability/Proceedings-of-the-Fourth-Berkeley-Symposium-on-Mathematical-Statistics-and/chapter/Optimal-Gambling-Systems-for-Favorable-Games/bsmsp/1200512159).
3. Thorp, E. O. (2006). The Kelly Criterion in Blackjack, Sports Betting, and the Stock Market. In S. A. Zenios & W. T. Ziemba (Eds.), *Handbook of Asset and Liability Management*, Vol. 1, pp. 385–428. North-Holland/Elsevier. ISBN 978-0-444-50875-1. (Continuous-Kelly `g(f)=fm−½f²s²`, `f*=m/s²`, `g(f*)=m²/2s²`, fractional-Kelly `g(cf*)=(2c−c²)g(f*)`, half-Kelly 75%/25%.) Full-text verified against the author reprint, accessed 2026-06-16: the continuous Brownian treatment (§3) and the "case for fractional Kelly" §7.3 confirm half-Kelly retains `g=0.75` (in units of `m²/2s²`). Author reprint: [gwern.net/doc/statistics/decision/2006-thorp.pdf](https://gwern.net/doc/statistics/decision/2006-thorp.pdf).
4. MacLean, L. C., Thorp, E. O., & Ziemba, W. T. (2010). Long-term capital growth: the good and bad properties of the Kelly and fractional Kelly capital growth criteria. *Quantitative Finance*, 10(7), 681–687. DOI: [10.1080/14697688.2010.506108](https://doi.org/10.1080/14697688.2010.506108). (Good/bad-properties ledger; fractional-Kelly recommendation.)
5. MacLean, L. C., Ziemba, W. T., & Blazenko, G. (1992). Growth versus Security in Dynamic Investment Analysis. *Management Science*, 38(11), 1562–1585. DOI: [10.1287/mnsc.38.11.1562](https://doi.org/10.1287/mnsc.38.11.1562). (Growth-security trade-off; fractional-Kelly justification.)
6. Chopra, V. K., & Ziemba, W. T. (1993). The Effect of Errors in Means, Variances, and Covariances on Optimal Portfolio Choice. *The Journal of Portfolio Management*, 19(2), 6–11. DOI: [10.3905/jpm.1993.409440](https://doi.org/10.3905/jpm.1993.409440) (DOI resolves to publisher pm-research.com, accessed 2026-06-16). (Errors in means ~10× variances, ~20× covariances.)
7. Busseti, E., Ryu, E. K., & Boyd, S. (2016). Risk-Constrained Kelly Gambling. *The Journal of Investing*, 25(3), 118–134; preprint arXiv:1603.06183. DOI: [10.3905/joi.2016.25.3.118](https://doi.org/10.3905/joi.2016.25.3.118); arXiv: [arxiv.org/abs/1603.06183](https://arxiv.org/abs/1603.06183). Verified by **text extraction of the Stanford author PDF** [web.stanford.edu/~boyd/papers/pdf/kelly.pdf](https://web.stanford.edu/~boyd/papers/pdf/kelly.pdf) (`pdfminer`, 2026-06-16) — table cells read from the primary text, not from the lossy `ar5iv` HTML mirror (which corrupts the Table 3 cell to `0.412`/`0.387`; do not use). (Conditional drawdown bound, their eq. (6)/(8): `E[(rᵀb)^{−θ} ] ≤ 1 ⟹ Prob(W_min<α)<α^θ`, with `θ = log β/log α`; the bound holds **only** for bets satisfying the constraint. Their unconstrained **Kelly** bet has growth `0.062`, `Prob(W_min<0.7) = 0.397 (≈0.40)` (Table 1, finite outcomes) and growth `0.077`, `Prob(W_min<0.7) = 0.569 (≈0.57)` (Table 3, infinite outcomes) — i.e. full Kelly does **not** satisfy the `θ=1` bound. RCK ⇒ fractional Kelly `b = f·b*+(1−f)e_cash`, `f<1` (§5.3, verbatim "for some f < 1"). RCK **dominates** fractional Kelly in the finite-outcome case (Fig. 4, §7.1.3: fractional-Kelly growth `0.035` vs RCK `0.047` at risk bound `β=0.1`) and shows "(essentially) the same performance as RCK" in the infinite-return case (§7.2.2).)
8. Uhrín, M., Šourek, G., Hubáček, O., & Železný, F. (2021). Optimal sports betting strategies in practice: an experimental review. *IMA Journal of Management Mathematics*, 32(4), 465–489; preprint arXiv:2107.08827. DOI: [10.1093/imaman/dpaa029](https://doi.org/10.1093/imaman/dpaa029); arXiv: [arxiv.org/abs/2107.08827](https://arxiv.org/abs/2107.08827). (Multivariate Kelly `max E[log(Of)] s.t. 1ᵀf=1`; fractional Kelly `f_ω=ωf+(1−ω)f_cash`; empirical: full Kelly → 100% ruin without edge, flat staking inferior, fractional Kelly best risk-adjusted.)
9. Ottaviani, M., & Sørensen, P. N. (2008). The Favorite-Longshot Bias: An Overview of the Main Explanations. In D. B. Hausch & W. T. Ziemba (Eds.), *Handbook of Sports and Lottery Markets*, pp. 83–101. North-Holland/Elsevier. DOI: [10.1016/B978-044450744-0.50009-3](https://doi.org/10.1016/B978-044450744-0.50009-3) (verified to resolve 2026-06-16: HTTP 302 → Elsevier ScienceDirect PII B9780444507440500093; this is the *corrected* chapter DOI — the sibling odds-doc records that an earlier inferred DOI `…0.50007-1` returned 404). Open-access mirror: [web.econ.ku.dk/sorensen/papers/FLBsurvey.pdf](https://web.econ.ku.dk/sorensen/papers/FLBsurvey.pdf). (Negative-EV prior for longshot/underdog betting.)
10. Ledoit, O., & Wolf, M. (2008). Robust performance hypothesis testing with the Sharpe ratio. *Journal of Empirical Finance*, 15(5), 850–859. DOI: [10.1016/j.jempfin.2008.03.002](https://doi.org/10.1016/j.jempfin.2008.03.002). (Studentized time-series bootstrap for pairwise Sharpe comparison.)
11. Lo, A. W. (2002). The Statistics of Sharpe Ratios. *Financial Analysts Journal*, 58(4), 36–52. DOI: [10.2469/faj.v58.n4.2453](https://doi.org/10.2469/faj.v58.n4.2453). (Asymptotic single-strategy Sharpe CI.)
12. White, H. (2000). A Reality Check for Data Snooping. *Econometrica*, 68(5), 1097–1126. DOI: [10.1111/1468-0262.00152](https://doi.org/10.1111/1468-0262.00152). (Best-of-grid vs benchmark, bootstrap reality check.)
13. Hansen, P. R. (2005). A Test for Superior Predictive Ability. *Journal of Business & Economic Statistics*, 23(4), 365–380. DOI: [10.1198/073500105000000063](https://doi.org/10.1198/073500105000000063). (SPA, less conservative than Reality Check.)
14. Newey, W. K., & West, K. D. (1994). Automatic Lag Selection in Covariance Matrix Estimation. *The Review of Economic Studies*, 61(4), 631–653. DOI: [10.2307/2297912](https://doi.org/10.2307/2297912). (Data-dependent HAC bandwidth.)
15. Politis, D. N., & Romano, J. P. (1994). The Stationary Bootstrap. *Journal of the American Statistical Association*, 89(428), 1303–1313. DOI: [10.1080/01621459.1994.10476870](https://doi.org/10.1080/01621459.1994.10476870). (Block/stationary bootstrap for the matchday-resampling ruin Monte-Carlo.)
16. Feller, W. (1968). *An Introduction to Probability Theory and Its Applications*, Vol. I, 3rd ed., Ch. XIV (Random Walk and Ruin Problems). Wiley. ISBN 978-0-471-25708-0. (Classical gambler's-ruin / fixed-stake ruin probability.)
17. Opdyke, J. D. (2007). Comparing Sharpe ratios: So where are the p-values? *Journal of Asset Management*, 8(5), 308–336. DOI: [10.1057/palgrave.jam.2250084](https://doi.org/10.1057/palgrave.jam.2250084). (Single-strategy Sharpe inference under non-normal, dependent returns.)
18. [Pinnacle AH] Pinnacle, *What is handicap soccer betting?* (Betting Resources, official-vendor). Defines a `0` / zero ("PK") Asian Handicap: the bet wins if the backed side wins, the **stake is refunded on a draw**, and loses if the other side wins — explicitly stated to "achieve the same outcome as a Draw No Bet," i.e. AH-0.0 ≡ DNB with stake refunded on a 90-minute tie. URL: [pinnacle.com/betting-resources/en/betting-strategy/what-is-handicap-soccer-betting/x9h2kx3zfzndmtef](https://www.pinnacle.com/betting-resources/en/betting-strategy/what-is-handicap-soccer-betting/x9h2kx3zfzndmtef), accessed 2026-06-16. (Official-vendor definitional source — evidence tier: official documentation — for the DNB ≡ AH-0.0 push payoff. Paraphrased, not quoted: the audit confirmed no verbatim "zero handicap eliminates the draw…" sentence is present on Pinnacle's separate *Betting rules* page [pinnacle.com/en/future/betting-rules](https://www.pinnacle.com/en/future/betting-rules), so that earlier quotation has been removed; the substantive AH-0 ≡ DNB mechanic is corroborated by this Betting-Resources page and by the *Draw No Bet* article 18b.)
18b. [Pinnacle DNB] Pinnacle, *Using the 1X2 market to produce Draw No Bet odds* (Betting Resources). Official explanation of constructing a synthetic DNB by covering the stake with the draw-leg profit so net profit on a draw is zero (the §1.3 identity). URL: [pinnacle.com/en/betting-articles/betting-strategy/draw-no-bet/7k9jslj7nu2gf2tn](https://www.pinnacle.com/en/betting-articles/betting-strategy/draw-no-bet/7k9jslj7nu2gf2tn), accessed 2026-06-16. (Official-vendor source for the synthetic-DNB-from-1X2 construction.)
18c. Third-party explainer (evidence tier 5, **not** affiliated with or endorsed by Pinnacle — site carries an explicit disclaimer to that effect): *What is Asian Handicap 0?* URL: [pinnacleoddsdropper.com/blog/asian-handicap-0](https://www.pinnacleoddsdropper.com/blog/asian-handicap-0), accessed 2026-06-16. Retained only as a secondary corroboration; the definitional claim rests on [Pinnacle AH] (18) above, not on this site.
19. football-data.co.uk. Notes for Football Data (column definitions): the data dictionary lists `PSH/PSD/PSA` (Pinnacle 1X2), `PAHH/PAHA` (Pinnacle Asian-handicap), `AHh` (handicap size) verbatim, and states the general convention that **closing** odds insert a "C" after the bookmaker prefix (e.g. `B365CH`). The closing Pinnacle columns `PSCH/PSCD/PSCA`, `PCAHH/PCAHA`, `AHCh` follow that convention but are not individually enumerated in notes.txt, so they must be confirmed against the live header row of each season's CSV. URL: [football-data.co.uk/notes.txt](https://www.football-data.co.uk/notes.txt), accessed 2026-06-16. (Data dictionary for the estimation universe and the DNB/synthetic columns.)

---

## Open questions and assumptions to validate

1. **Quoted vs synthetic DNB margin gap.** Validate that quoted AH-0.0 (`PCAHH/PCAHA`) and the 1X2-synthetic DNB (eq. 1) agree up to a small, stable margin difference; if they diverge, decide which feeds *settlement* (always the quoted, tradable line) vs *sizing*. The draw-leg fill at exactly `D` in eq. (1) assumes no separate draw-market margin — quantify the error.
2. **Independence of concurrent matches.** Test the default `π_k = Π_j P(·)` against final-round dead-rubber / collusion ("biscotto") effects before trusting the renormalised single-bet approximation (§5.3); if dependent, run the full vector program (6).
3. **Stationarity of edge across universes.** The expanded domestic-league universe is the estimation set; the World Cup is held out. Validate that the *edge* and the *return distribution* are exchangeable enough to transfer (block-bootstrap two-sample tests on the realised-return distributions); if not, the §6.3 ruin estimates calibrated on leagues understate World-Cup tail risk.
4. **Choice of `λ` prior.** Half-Kelly is the documented default (§4.3) but the Bayesian shrinkage `λ ≈ 1/(1+CV²)` (§4.2) should be made fully explicit with a posterior on the edge from the calibration model, rather than asserting `λ=0.5`; the CV-selected `λ` must be reported with a bootstrap CI.
5. **Ruin floor `ρ` and drawdown target `(α_dd, β_dd)`.** These are decision inputs (risk preferences), not data. They are declared in [docs/protocol/methodology.md](../protocol/methodology.md) §1 with a stated rationale (prospect-theory threshold-type stop-loss / disposition-effect evidence) and a **swept grid** (`α_dd ∈ {0.5,0.6,0.7,0.8}`, `β_dd ∈ {0.05,0.10,0.20}`, `ρ ∈ {0.0,0.5}`), with the frontier reported across the range so the operating point is transparent. Remaining check: confirm the grid bounds against the realised drawdown distribution once league bets are settled, and that the chosen operating cell's CV-selected `λ` carries a bootstrap CI (Open Question 4).
6. **Negative-EV prior dominating.** If the corrected (White/Hansen) analysis cannot reject the no-edge null, the honest output is `λ*=0` (do not bet). Pre-commit to reporting this rather than searching for a surviving cell — the multiple-testing register exists precisely to prevent that.
7. **Per-bet variance proxy.** Resolved in-line (§3.3): the calibration target is the **three-outcome DNB variance** `Var_DNB = p_A·b² + p_H − μ²` (eq. 3c; = 1.436 at the worked numbers), **not** the straight-win-bet `o−1` identity (= 1.857), which holds only for a two-outcome win bet at fair odds and overstates DNB variance by ≈23 % (cross-checked against the sibling odds-doc §6.1–6.2 closed form). Remaining caveat: even eq. (3c) assumes the modeled `p`; with margin and mis-calibrated `p` the realised variance differs, so the Monte-Carlo uses the *empirical* return variance, and the gap between the analytic eq.-(3c) benchmark and the realised second moment is documented as a calibration diagnostic.
8. **Transaction-cost / liquidity at the close.** Pinnacle closing lines are used for efficiency, but capacity and the ability to actually transact at the close (especially the draw leg of the synthetic) must be modeled per [rules/quant-project.md](rules/quant-project.md) reporting requirements (transaction-cost model, capacity estimate).
