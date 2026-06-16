# Statistical Inference and Validation Methodology for the World-Cup Underdog Draw-No-Bet Backtest

Research dimension: statistical inference and validation methodology.
Project: backtest of an underdog Draw-No-Bet (DNB) strategy on the FIFA men's World Cup, with the estimation universe expanded to domestic leagues (football-data.co.uk) and the World Cup held out as a subsample.
Date: 2026-06-16. Author dimension: SKIE.

## Scope

This document specifies, with verified primary-source citations, the full inference and validation apparatus for evaluating a betting strategy whose per-bet payoff is a non-Gaussian, possibly serially dependent, heavy-tailed random variable observed in a small sample. It covers: (i) performance-metric definitions and formulas; (ii) bootstrap confidence intervals on the Sharpe ratio and pairwise Sharpe comparison; (iii) HAC standard errors; (iv) multiple-testing control across staking and strategy variants; (v) Deflated/Probabilistic Sharpe Ratio and minimum track-record length to correct grid-search selection bias; (vi) pre-data power analysis with the post-hoc-power prohibition; (vii) walk-forward time-ordered validation and a point-in-time leakage canary; (viii) assumption checks (stationarity, independence, distributional form). Every tunable quantity is tied to an empirical-selection rule, never a magic number, per the project's parameter-selection mandate.

It does NOT re-derive the betting economics. Two facts are imported as priors and used quantitatively below:

- **Favorite-longshot bias (FLB).** In fixed-odds soccer markets the expected return on longshots is systematically below that on favorites; backing the underdog therefore carries a negative-EV prior before any edge. Documented for European football betting by [Angelini & De Angelis (2019)](https://doi.org/10.1016/j.ijforecast.2018.07.008) (41 bookmakers, 11 leagues, 11 years; "strong favourite–longshot bias") and surveyed across markets by [Ottaviani & Sørensen (2008)](https://www.sciencedirect.com/science/article/pii/B9780444507440500093).
- **Aggregate cross-bookmaker odds efficiency (a distinct claim from closing-line efficiency).** [Angelini & De Angelis (2019)](https://doi.org/10.1016/j.ijforecast.2018.07.008) test, in a Mincer–Zarnowitz framework over 41 bookmakers, 11 European leagues, 11 years, the efficiency of the *mean-across-bookmakers* and *best/maximum-across-bookmakers* odds **at a single snapshot**; they find mean-market odds largely efficient and best-odds inefficient in some leagues. This is a cross-sectional aggregate-odds result, **not** evidence about closing-line dynamics, line movement, or closing-line value, and is not used as such below.
- **Closing-line efficiency (intertemporal).** That the closing line is the most accurate available probability estimate — because late price formation incorporates more information than the open — is supported in soccer markets by [Štrumbelj (2014)](https://doi.org/10.1016/j.ijforecast.2014.02.008) (Shin-corrected closing odds are accurate probability forecasts) and by [Hegarty & Whelan (2025)](https://doi.org/10.1016/j.ijforecast.2024.06.013), who show the Asian-handicap market — the project's exact DNB instrument — generates efficient forecasts for the same matches via a Shin-type odds-to-probability mapping. The narrower industry claim that **Pinnacle** closing odds are the *sharpest* low-margin benchmark and that beating them (positive CLV) predicts profit is treated here as a **market-microstructure prior / working assumption**, not as a peer-reviewed finding, and is labelled as such wherever it is used. This motivates **closing-line value (CLV)** as a leading indicator of edge (Section 2.9), evaluated against the closing line rather than industry blogs.

### Notation and the unit of analysis

Let bet $i$ ($i=1,\dots,n$) have **net profit per unit stake** $R_i$. For a clean win bet at decimal odds $o_i$:

$$
R_i = \begin{cases} o_i - 1 & \text{bet wins (prob. } p_i)\\ -1 & \text{bet loses} \end{cases}
$$

For the synthetic DNB on the away (underdog) side, with 1X2 decimals $(H,D,A)$, the project's key identity gives effective DNB decimal odds

$$
o^{\text{DNB}} = \frac{A(D-1)}{D},
$$

and the three-outcome payoff (stake refunded on a 90-minute draw) is

$$
R_i = \begin{cases}
o^{\text{DNB}}-1 = \dfrac{A(D-1)}{D}-1 & \text{away win} \\[4pt]
0 & \text{draw (stake refunded)} \\[4pt]
-1 & \text{home win.}
\end{cases}
$$

The **per-bet variance of a fair win bet** at odds $o$ is $\operatorname{Var}(R)=o-1$ (derivation in Section 2.10), the load-bearing quantity for the power analysis. All inference is conducted on the sequence $\{R_i\}$ ordered by match kickoff time; the ordering is what makes serial-dependence and look-ahead controls meaningful.

---

## 1. The four statistical hazards this design must survive

1. **Small $n$.** World-Cup-only clean-odds sample $\approx 384$ matches (2002–2022, 64/tournament for the 32-team era; 2026 expands to 104). This is underpowered (Section 6) and is the reason the estimation universe is expanded to domestic leagues with the World Cup held out.
2. **Non-normality.** The per-bet $R_i$ is a discrete, **positively** skewed, heavy-tailed variable (a large positive payoff with small probability against a high-probability $-1$ floor — the structural signature of a longshot/underdog stake). A direct moment computation over realistic de-vig'd underdog 1X2 vectors gives per-bet skewness in the $+0.4$ to $+2.4$ range (never negative); see Sections 2.7 and 8.4. (The *compounded equity curve* under fractional staking can carry a different, possibly negative, skew; each moment below states the object it is computed on — the unit of analysis is the per-bet sequence $\{R_i\}$ unless stated otherwise.) Gaussian Sharpe inference is invalid; skewness/kurtosis corrections ([Bailey & López de Prado 2014, eq. 4](https://doi.org/10.3905/jpm.2014.40.5.094); [Lo 2002](https://doi.org/10.2469/faj.v58.n4.2453); [Mertens 2002](https://www.elmarmertens.com/research/)) are mandatory.
3. **Serial dependence.** Bets cluster in time (tournament windows, league rounds); staking schemes (Kelly, fixed-fraction) make $R_i$ path-dependent. IID bootstraps and OLS standard errors understate uncertainty; block/stationary bootstraps ([Politis & Romano 1994](https://doi.org/10.1080/01621459.1994.10476870)) and HAC SEs ([Andrews 1991](https://doi.org/10.2307/2938229); [Newey & West 1994](https://doi.org/10.2307/2297912)) are required.
4. **Selection bias / data snooping.** Multiple staking schemes, side definitions, odds sources, and underdog thresholds are tried. Reporting the best without correction inflates the apparent Sharpe ([Bailey et al. 2014, Notices AMS](https://www.ams.org/notices/201405/rnoti-p458.pdf); [White 2000](https://doi.org/10.1111/1468-0262.00152); [Hansen 2005](https://doi.org/10.1198/073500105000000063); [Romano & Wolf 2005](https://doi.org/10.1111/j.1468-0262.2005.00615.x)).

---

## 2. Performance-metric definitions and formulas

All metrics are defined on net-profit-per-stake $R_i$; "per bet" is the natural frequency since bets are not equally spaced in time.

### 2.1 ROI / yield per bet

$$
\widehat{\text{ROI}} = \frac{1}{n}\sum_{i=1}^{n} R_i = \bar R, \qquad \text{(equivalently total P\&L} / \text{total staked for unit stakes).}
$$

This is the sample mean of $R_i$; "yield" is the same quantity expressed in percent. With *variable* stakes $w_i$, the staked-weighted yield is $\sum_i w_i R_i / \sum_i w_i$, which is **not** $\bar R$ and must be reported as such. ROI is the parameter of interest; everything else quantifies its uncertainty.

### 2.2 Hit / win ratio

$$
\widehat{\text{hit}} = \frac{\#\{i: R_i>0\}}{n}.
$$

For DNB, refunds ($R_i=0$) are excluded from both numerator and denominator (the convention must be stated; an alternative counts them as half-wins, which changes the number). Hit ratio alone is uninformative about profitability because payoff magnitudes differ across odds; it is reported only jointly with ROI and average odds.

### 2.3 Sharpe ratio (per bet and annualized)

Per-bet (excess return over the risk-free per-bet rate $r_f\approx 0$ for within-event horizons):

$$
\widehat{SR} = \frac{\bar R - r_f}{\hat\sigma_R}, \qquad \hat\sigma_R^2 = \frac{1}{n-1}\sum_{i=1}^n (R_i-\bar R)^2 .
$$

**Annualization.** Multiplying a per-bet SR by $\sqrt{\#\text{bets/yr}}$ is valid only under IID returns. [Lo (2002, eq. 7)](https://doi.org/10.2469/faj.v58.n4.2453) shows that under stationary, autocorrelated returns the correct $q$-period scaling factor is

$$
SR(q) = \eta(q)\,SR, \qquad \eta(q)=\frac{q}{\sqrt{\,q + 2\sum_{k=1}^{q-1}(q-k)\rho_k\,}},
$$

with $\rho_k$ the order-$k$ autocorrelation of returns; $\eta(q)=\sqrt q$ only when all $\rho_k=0$. We report per-bet SR as primary and any annualization with the $\eta(q)$ correction and the estimated $\rho_k$ stated.

### 2.4 Sortino ratio

Replaces total volatility with downside deviation below a target $\tau$ (here $\tau=0$, capital-preservation target):

$$
\widehat{\text{Sortino}} = \frac{\bar R - \tau}{\widehat{DD}_\tau}, \qquad
\widehat{DD}_\tau = \sqrt{\frac{1}{n}\sum_{i=1}^{n}\big(\min(R_i-\tau,0)\big)^2}.
$$

The denominator divides by $n$ (not the count of below-target observations) — the lower partial moment convention; the divisor choice must be stated because the alternative inflates the ratio.

### 2.5 Maximum drawdown (MaxDD)

On the cumulative equity curve $E_t = \prod_{i\le t}(1+f R_i)$ for fractional stake $f$ (or additive $E_t=\sum_{i\le t}R_i$ for unit stakes),

$$
\text{MaxDD} = \max_{t}\left(\frac{\max_{s\le t} E_s - E_t}{\max_{s\le t} E_s}\right).
$$

MaxDD is a sample maximum and is severely biased downward (optimistic) in small samples; report it with the path's length and treat it descriptively, never as a tested statistic.

### 2.6 Turnover and capacity

Turnover per period = total stake placed / bankroll. For unit-stake flat betting over a tournament of $m$ bets on a bankroll $B$, turnover $= m/B$. Capacity is the maximum stake before the bet itself moves the closing line; for World-Cup underdog DNB on Pinnacle this is liquidity-bounded and must be estimated from observed bet-limit data, not assumed.

### 2.7 Sharpe standard error and confidence interval (asymptotic)

**IID-Gaussian baseline** ([Lo 2002, eq. 9](https://doi.org/10.2469/faj.v58.n4.2453)): $\operatorname{Var}(\widehat{SR}) \approx (1 + \tfrac12 SR^2)/T$. This is **invalid here** (returns are non-normal). The non-normality-robust SE used as the PSR/DSR engine — primary source [Bailey & López de Prado 2014, eq. 4](https://doi.org/10.3905/jpm.2014.40.5.094), with the moment-corrected form also in [Lo 2002](https://doi.org/10.2469/faj.v58.n4.2453) and the IID-non-normal correction noted by [Mertens 2002](https://www.elmarmertens.com/research/) — is

$$
\widehat{\sigma}(\widehat{SR}) = \sqrt{\frac{1 - \hat\gamma_3\,\widehat{SR} + \tfrac{\hat\gamma_4-1}{4}\,\widehat{SR}^{\,2}}{T-1}},
$$

where $\hat\gamma_3$ is sample skewness and $\hat\gamma_4$ is sample kurtosis (non-excess; Gaussian $\gamma_4=3$, so $(\gamma_4-1)/4=1/2$ recovers the Gaussian term). The two higher moments push the SE in **opposite** directions for this strategy. The skew enters as $-\hat\gamma_3\,\widehat{SR}$; per-bet underdog DNB returns are **positively** skewed ($\hat\gamma_3>0$, the small-probability large-gain / $-1$-floor structure — see hazard 2 and the moment check in Section 8.4), so this term *lowers* the denominator and hence the robust SE relative to the Gaussian formula (e.g. at $\widehat{SR}=0.045$ the radicand multiplier is $0.987$ at $\hat\gamma_3=+0.6$ vs $1.014$ at $-0.6$). The skew contribution is therefore *favorable* to the bettor's Sharpe inference. Excess kurtosis ($\hat\gamma_4>3$, also expected) enters as $+\tfrac{\hat\gamma_4-1}{4}\widehat{SR}^2$ and **inflates** the SE; it is the dominant adverse moment. Because the moments act in opposite directions, the net Gaussian-vs-robust direction must be argued from the kurtosis term, not the skew: with small per-bet $\widehat{SR}$ the linear-in-$\widehat{SR}$ skew term is first-order and the quadratic kurtosis term second-order, so the favorable skew can dominate at the per-bet horizon — the robust SE must be computed, not signed a priori. (This is the per-bet object; a negatively skewed compounded equity curve would reverse the skew term's effect, which is why the object each moment is computed on is stated explicitly.)

### 2.8 Opdyke (2007) non-IID Sharpe distribution

[Opdyke (2007)](https://doi.org/10.1057/palgrave.jam.2250084) derives the asymptotic distribution of the Sharpe ratio under the weakest conditions (stationary and ergodic, permitting serial correlation and time-varying volatility) and shows it nests the Lo (2002) and Mertens results as special cases; this is the appropriate large-sample reference for the serially dependent, heteroskedastic betting series, and is the analytic complement to the Ledoit–Wolf bootstrap (Section 4).

### 2.9 Closing-line value (CLV)

Let $o_i^{\text{bet}}$ be the odds taken and $o_i^{\text{close}}$ the closing (Pinnacle) odds on the same selection. The **odds-ratio CLV** (no-vig where available) is

$$
\text{CLV}_i = \frac{o_i^{\text{bet}}}{o_i^{\text{close}}} - 1,
$$

and the **probability-form CLV** uses implied probabilities $\pi=1/o$ after removing the bookmaker margin (overround) $\Omega = \sum_{\text{outcomes}}1/o - 1$; the Shin de-vig of [Štrumbelj (2014)](https://doi.org/10.1016/j.ijforecast.2014.02.008) is preferred to proportional normalization because it accounts for the FLB-generating insider component. Mean positive CLV over many bets is, under closing-line efficiency ([Štrumbelj 2014](https://doi.org/10.1016/j.ijforecast.2014.02.008); [Hegarty & Whelan 2025](https://doi.org/10.1016/j.ijforecast.2024.06.013) for the Asian-handicap/DNB market specifically), a leading indicator of genuine edge and has far more statistical power per bet than realized ROI because it is not gated by the binary match outcome. The treatment of Pinnacle's closing line as the *sharpest* benchmark against which CLV is measured is a market-microstructure working assumption (not attributed to Angelini & De Angelis 2019, which concerns cross-bookmaker aggregate odds at a snapshot, not closing-line dynamics). **Caveat for this project:** the synthetic DNB closing line must be reconstructed from the *closing* 1X2 columns (`PSCH/PSCD/PSCA`) via the same $o^{\text{DNB}}=A(D-1)/D$ identity, or from the closing Asian-Handicap-0 columns, never from opening odds — using opening odds as "closing" is a silent look-ahead error.

### 2.10 Worked variance identity (load-bearing for power)

For a fair win bet at decimal odds $o$ with win probability $p=1/o$ (fair $\Rightarrow$ $E[R]=0$):

$$
E[R] = p(o-1) + (1-p)(-1) = \tfrac{1}{o}(o-1) - (1-\tfrac1o) = 0,
$$
$$
\operatorname{Var}(R) = E[R^2] = p(o-1)^2 + (1-p)(1)^2 = \tfrac1o(o-1)^2 + (1-\tfrac1o) = (o-1).
$$

Hence **$\operatorname{Var}(R)=o-1$** and $\operatorname{SD}(R)=\sqrt{o-1}$ exactly, for a fair single win bet. Underdog bets have large $o$, hence large per-bet variance, hence (Section 6) large required $n$. For DNB at effective odds $o^{\text{DNB}}$ with a draw mass $d=1/D$ refunded, the variance is reduced relative to the equivalent straight win bet: $\operatorname{Var}(R^{\text{DNB}}) = (1-d)\,\operatorname{Var}(R \mid \text{not draw})$ scaled by the conditional win probability — this variance reduction is the statistical rationale for DNB over a straight win bet and is quantified empirically per odds bucket rather than assumed.

---

## 3. Bootstrap confidence intervals on the Sharpe ratio

### 3.1 Why bootstrap, and which one

The asymptotic SE (2.7) is a large-$T$ approximation; with $n$ in the hundreds and heavy tails, coverage is poor. Bootstrap CIs are used as the primary interval, with the asymptotic SE as a cross-check. Because $\{R_i\}$ is serially dependent, an IID (Efron) resample destroys the dependence and understates variance; a **block** or **stationary** bootstrap is required.

### 3.2 Stationary bootstrap (Politis–Romano 1994)

[Politis & Romano (1994)](https://doi.org/10.1080/01621459.1994.10476870) resample blocks of **geometric random length** with mean $1/p$, wrapping the series circularly. The resulting pseudo-series is strictly stationary (unlike the fixed-block bootstrap of Künsch, whose concatenation is non-stationary), which is the property that makes it the default for dependent data here. Algorithm per replication $b$:

1. Draw a start index uniformly on $\{1,\dots,n\}$.
2. With probability $1-p$ keep the next consecutive observation; with probability $p$ jump to a new uniform start. Wrap at $n\to 1$.
3. Continue until the pseudo-series has length $n$; compute $\widehat{SR}^{*b}$.

Repeat $B$ times. The block-length parameter $p$ (equivalently expected block $1/p$) is **not** chosen by hand.

### 3.3 Block-length selection (Politis–White 2004)

[Politis & White (2004)](https://doi.org/10.1081/ETC-120028836), with the [Patton, Politis & White (2009) correction](https://doi.org/10.1080/07474930802459016), give a data-driven optimal expected block length minimizing the MSE of the long-run-variance estimator. The optimal stationary-bootstrap block is

$$
\hat b_{\text{SB}}^{\text{opt}} = \left(\frac{2\,\hat g^2}{\hat D_{\text{SB}}}\right)^{1/3} n^{1/3},
$$

with $\hat g$ and $\hat D_{\text{SB}}$ estimated from the flat-top-lag-window autocovariance sequence of $\{R_i\}$ (their eqs. for $\hat g=\sum_k |k|\hat\gamma_k$ and $\hat D$). This is the mandated selector: report $\hat b_{\text{SB}}^{\text{opt}}$ and the implied $p=1/\hat b$ with the estimated autocovariances, satisfying the no-magic-number rule. (Common code defaults such as $b=5$ — see [Ledoit & Wolf 2008](https://doi.org/10.1016/j.jempfin.2008.03.002) implementations — are acceptable *only* as a sensitivity comparison, never as the headline choice.)

### 3.4 Bootstrap CI construction

Two intervals are reported:

- **Studentized (bootstrap-$t$)** — first-order-accurate-plus, the recommended interval for an asymmetric statistic. Form $t^{*b}=(\widehat{SR}^{*b}-\widehat{SR})/\hat\sigma^{*b}$ where $\hat\sigma^{*b}$ is the within-replicate HAC SE (Section 4); the $1-\alpha$ CI is $[\widehat{SR}-\hat\sigma\, q^*_{1-\alpha/2},\ \widehat{SR}-\hat\sigma\, q^*_{\alpha/2}]$ with $q^*$ the bootstrap quantiles of $t^{*b}$.
- **BCa** (bias-corrected and accelerated) as a robustness check.

$B$ is chosen so the Monte-Carlo SE of the $\alpha$-quantile is negligible relative to the CI width; $B=10{,}000$ for final reporting is justified by requiring Monte-Carlo error $<$ 1% of the interval half-width (verify post hoc), not by convention.

---

## 4. Pairwise strategy comparison: Ledoit–Wolf (2008) studentized bootstrap

When comparing two strategies (e.g. DNB-underdog vs. straight-win-underdog, or two staking schemes), the object is the **difference of Sharpe ratios** $\Delta = SR_1 - SR_2$ on the *same* matches (dependent samples). [Ledoit & Wolf (2008)](https://doi.org/10.1016/j.jempfin.2008.03.002) provide the canonical test.

**Estimand and delta-method SE.** With moment vector $\nu=(\mu_1,\mu_2,\gamma_1,\gamma_2)$ where $\mu_k=E[r_k]$, $\gamma_k=E[r_k^2]$, the Sharpe is $f(\nu)=$ written in these moments and $\Delta=f_1-f_2$. By the delta method, if $\sqrt T(\hat\nu-\nu)\xrightarrow{d}N(0,\Psi)$ then $\sqrt T(\hat\Delta-\Delta)\xrightarrow{d}N(0,\nabla f'\Psi\nabla f)$, and

$$
\operatorname{SE}(\hat\Delta) = \sqrt{\frac{\nabla f(\hat\nu)'\,\hat\Psi\,\nabla f(\hat\nu)}{T}},
$$

where $\hat\Psi$ is a **HAC kernel estimate** of the long-run covariance (Ledoit–Wolf use a prewhitened kernel; see Section 5) — this is what makes the test robust to the non-IID, heavy-tailed returns that break the Jobson–Korkie/Memmel normal test.

**Studentized circular-block bootstrap.** The studentized statistic is $\hat\Delta/\operatorname{SE}(\hat\Delta)$; its sampling distribution is approximated by the **circular block bootstrap** applied jointly to the bivariate series $(r_{1i},r_{2i})$ (preserving cross- and serial dependence), recomputing $\hat\Delta^{*b}$ and its HAC SE per replicate. The two-sided $p$-value is the bootstrap tail probability of $|\,\hat\Delta^{*b}-\hat\Delta\,|/\operatorname{SE}^{*b} \ge |\hat\Delta|/\operatorname{SE}$; declare the Sharpes different iff the studentized bootstrap CI for $\Delta$ excludes 0. Reference implementations use $B=1000$, block $b=5$; the block length here must instead come from the Politis–White (2004) selector (Section 3.3), with $b=5$ retained only as sensitivity.

This test is for **one pair**. With many strategies the family-wise procedures of Section 5 supersede it.

---

## 5. HAC standard errors

HAC SEs appear in three places: (i) testing whether mean ROI $\bar R>0$; (ii) the long-run-variance plug-in for Sharpe SEs; (iii) the $\hat\Psi$ inside Ledoit–Wolf. The HAC estimator of the long-run variance of $\{R_i\}$ is

$$
\hat J = \hat\gamma_0 + 2\sum_{k=1}^{n-1} w\!\left(\frac{k}{S_n}\right)\hat\gamma_k, \qquad \hat\gamma_k=\frac1n\sum_{i}(R_i-\bar R)(R_{i-k}-\bar R),
$$

with kernel $w(\cdot)$ and bandwidth $S_n$. The two mandated data-dependent bandwidth rules:

- **[Newey & West (1994)](https://doi.org/10.2307/2297912)** — nonparametric, MSE-optimal automatic lag selection (Bartlett kernel by default): the bandwidth is chosen from a pilot estimate of $\sum_k k\hat\gamma_k$ via their plug-in $S_n = c\,(\text{ratio})^{2/(2q+1)} n^{1/(2q+1)}$; the lag truncation is computed, not fixed. (Note: the Newey–West 1994 DOI `10.2307/2297912` is the same numeral string carried in the project rules file — confirmed correct here.)
- **[Andrews (1991)](https://doi.org/10.2307/2938229)** — parametric plug-in: assume an AR(1) pilot, derive the optimal bandwidth in closed form for the Quadratic-Spectral (QS) kernel (which Andrews shows is asymptotically MSE-optimal among PSD kernels), $S_n^{\text{QS}} = 1.3221\,(\hat\alpha(2)\,n)^{1/5}$ with $\hat\alpha(2)$ a function of the fitted AR coefficients.

Either is acceptable; we report Andrews-QS as primary (PSD-guaranteed, optimal kernel) and Newey–West-Bartlett as cross-check. **Prewhitening** (fit a low-order VAR, apply HAC to residuals, recolor) is applied per Andrews–Monahan to reduce bias at the serial-dependence levels expected from tournament clustering.

---

## 6. Pre-data power analysis (and the post-hoc-power prohibition)

### 6.1 The prohibition

[Hoenig & Heisey (2001)](https://doi.org/10.1198/000313001300339897) prove that power computed *after* observing the data, from the observed effect, is a deterministic monotone transform of the $p$-value and conveys no independent information; "observed power" cannot be used to interpret a non-significant result. Therefore **all** power calculation here is **pre-data**, using a *plausible* (literature-anchored, not observed) ROI edge.

### 6.2 Required-$n$ formula

Testing $H_0:\mu_R=0$ vs $H_1:\mu_R=\delta$ (the plausible per-bet ROI edge) at two-sided level $\alpha$ and power $1-\beta$, with per-bet SD $\sigma_R$:

$$
n = \frac{(z_{1-\alpha/2}+z_{1-\beta})^2\,\sigma_R^2}{\delta^2}.
$$

Using the variance identity $\sigma_R^2 \approx o-1$ (Section 2.10) makes the per-bet SD explicit in the odds. A finite-sample / heavy-tail inflation factor and a **serial-dependence inflation** enlarge $n$; the Gaussian $n$ above is a *lower bound*.

The correct serial-dependence multiplier for a **mean / ROI** test is the **long-run-variance design effect**

$$
\kappa = \frac{\hat J}{\hat\gamma_0} = 1 + 2\sum_{k\ge 1}\Big(1-\tfrac{k}{n}\Big)\hat\rho_k,
$$

where $\hat J$ is the HAC long-run variance of $\{R_i\}$ from Section 5, $\hat\gamma_0$ the sample variance, and $\hat\rho_k=\hat\gamma_k/\hat\gamma_0$ the sample autocorrelations. The design-effect-inflated requirement is then

$$
n_{\text{required}} = \kappa\,\frac{(z_{1-\alpha/2}+z_{1-\beta})^2\,\sigma_R^2}{\delta^2}.
$$

Positive autocorrelation (the expected sign under tournament/round clustering) gives $\kappa>1$ and correctly **enlarges** $n$ — e.g. an AR(1) with $\rho=0.1$ over $n=384$ yields $\kappa\approx1.22$, a 22% increase in required sample.

Do **not** use the Sharpe-annualization scalar $\eta(q)$ of Section 2.3 as this multiplier. $\eta(q)$ time-aggregates a per-period Sharpe over $q$ periods; it is the wrong statistical object for a required-$n$ formula on a mean test. Numerically the two diverge by orders of magnitude in the wrong direction: for the same AR(1) $\rho=0.1$ and $q=n=384$, $\eta(q)^{-2}\approx 0.0032$ (which would *shrink* $n$ by ~300×), whereas the LRV design effect $\kappa\approx1.22$ (which correctly enlarges it). $\eta(q)$ is retained strictly for Sharpe annualization in Section 2.3. (Ref: [Lo 2002, eq. 7](https://doi.org/10.2469/faj.v58.n4.2453) for the $\eta(q)$ time-aggregation object; the HAC long-run variance $\hat J$ and its data-dependent bandwidth follow [Newey & West 1994](https://doi.org/10.2307/2297912), Section 5.)

### 6.3 Worked numbers (SD $=\sqrt{o-1}$)

Take a typical underdog effective DNB price $o=2.6 \Rightarrow \sigma_R=\sqrt{2.6-1}=\sqrt{1.6}=1.265$. Two-sided $\alpha=0.05\Rightarrow z=1.960$; power $0.80\Rightarrow z=0.8416$; so $(z_{1-\alpha/2}+z_{1-\beta})^2=(2.8016)^2=7.849$.

| Plausible edge $\delta$ (ROI) | $n=7.849\,\sigma_R^2/\delta^2$ | Interpretation |
|---|---|---|
| +2% ($\delta=0.02$) | $7.849\times1.6/0.0004 = 31{,}396$ bets | far beyond any WC sample |
| +5% ($\delta=0.05$) | $7.849\times1.6/0.0025 = 5{,}023$ bets | beyond WC; feasible only in expanded league universe |
| +10% ($\delta=0.10$) | $7.849\times1.6/0.01 = 1{,}256$ bets | still > WC-only $384$ |

At a longer price $o=4.0\Rightarrow\sigma_R^2=3.0$: a +5% edge needs $7.849\times3.0/0.0025 = 9{,}419$ bets. These $n$ are the **Gaussian, $\kappa=1$ lower bound**; the realized requirement is the table value $\times\,\hat\kappa$ (Section 6.2), so positive serial dependence ($\hat\kappa>1$, e.g. $\approx1.22$ at AR(1) $\rho=0.1$) pushes every cell up by that factor. **Conclusion:** the World-Cup-only sample ($\approx 384$) is powered only to detect implausibly large edges ($\delta\gtrsim 18\%$); this is the quantitative justification for expanding to the domestic-league universe and holding out the World Cup, exactly the project's stated mitigation. The expanded universe must reach the $\sim10^3$–$10^4$ scale above to have 80% power against a plausible single-digit-percent edge.

---

## 7. Multiple testing across staking schemes and strategy variants

The grid (side definition $\times$ staking scheme $\times$ underdog-threshold $\times$ odds source) generates $K$ candidate strategies. Selecting the best and reporting its naive $p$-value is invalid. Which correction applies depends on the question:

| Goal | Method | When it applies | Citation |
|---|---|---|---|
| Is the **best** strategy better than a benchmark (e.g. no-bet / market)? | **White Reality Check** (stationary-bootstrap max statistic) | composite null $\max_k E[f_k]\le 0$; benchmark-relative | [White (2000)](https://doi.org/10.1111/1468-0262.00152) |
| Same, but robust to many poor/irrelevant alternatives (more power) | **Hansen SPA** (studentized, recentered) | preferred default for strategy screening | [Hansen (2005)](https://doi.org/10.1198/073500105000000063) |
| **Which** strategies beat the benchmark (identify the set), FWER-controlled | **Romano–Wolf stepdown** | want a rejected set, exploit dependence | [Romano & Wolf (2005)](https://doi.org/10.1111/j.1468-0262.2005.00615.x) |
| Tolerate a controlled fraction of false discoveries (exploratory) | **Benjamini–Hochberg FDR** | many hypotheses, FDR not FWER | [Benjamini & Hochberg (1995)](https://doi.org/10.1111/j.2517-6161.1995.tb02031.x) |

**BH procedure.** Order $p_{(1)}\le\dots\le p_{(K)}$; reject $H_{(1)},\dots,H_{(k^*)}$ where $k^*=\max\{k: p_{(k)}\le \tfrac{k}{K}q\}$, controlling FDR at $q$. Under positive dependence among test statistics (expected here) BH controls FDR (Benjamini–Yekutieli give the dependence-robust variant).

**Operational policy.** White/Hansen answer "is there *any* edge in the grid"; Romano–Wolf answers "which ones"; BH is the exploratory fallback. The family of strategies tested is **pre-registered as a register** (the count $K$ and the menu) before fitting, so the correction denominator is honest — this is also the input $N$ to the Deflated Sharpe Ratio (Section 8).

---

## 8. Deflated and Probabilistic Sharpe Ratio (selection-bias correction)

### 8.1 Probabilistic Sharpe Ratio (PSR)

[Bailey & López de Prado (2014)](https://doi.org/10.3905/jpm.2014.40.5.094) define the probability that the *true* Sharpe exceeds a benchmark $SR_0$, given the observed $\widehat{SR}$ and the higher moments:

$$
\widehat{\text{PSR}}(SR_0) = \Phi\!\left(\frac{(\widehat{SR}-SR_0)\sqrt{T-1}}{\sqrt{\,1 - \hat\gamma_3\,\widehat{SR} + \tfrac{\hat\gamma_4-1}{4}\,\widehat{SR}^{\,2}\,}}\right),
$$

with $\Phi$ the standard-normal CDF, $\hat\gamma_3$ skewness, $\hat\gamma_4$ kurtosis (non-excess), $T$ the number of returns. The denominator is exactly the non-normality-robust Sharpe SE of Section 2.7 — PSR is a one-sided test using that SE. The two higher moments move PSR in opposite directions: positive skew (the per-bet underdog DNB case, $\hat\gamma_3>0$) shrinks the denominator and therefore *raises* PSR for a given $\widehat{SR}$, while fat tails ($\hat\gamma_4>3$) enlarge the denominator and *lower* PSR. In generic statements about a *negatively* skewed return stream the skew term lowers PSR — that generic claim is correct, but it does not describe this strategy's per-bet returns, whose skew is positive. For underdog DNB the binding adverse moment is excess kurtosis, not skew.

### 8.2 Deflated Sharpe Ratio (DSR)

DSR sets $SR_0$ to the **expected maximum** Sharpe attainable by chance after $N$ independent trials, thereby deflating for selection bias:

$$
\widehat{\text{DSR}} = \widehat{\text{PSR}}\big(SR_0^\star\big), \qquad
SR_0^\star = \sqrt{\operatorname{V}[\widehat{SR}_n]}\left[(1-\gamma_e)\,\Phi^{-1}\!\Big(1-\tfrac1N\Big) + \gamma_e\,\Phi^{-1}\!\Big(1-\tfrac{1}{N e}\Big)\right],
$$

where $\operatorname{V}[\widehat{SR}_n]$ is the **variance of the Sharpe ratios across the $N$ trials**, $\gamma_e\approx0.5772$ the Euler–Mascheroni constant, $e$ Euler's number, and $\Phi^{-1}$ the normal quantile. The two inputs $N$ and $\operatorname{V}[\widehat{SR}_n]$ come directly from the multiple-testing register of Section 7 (count and spread of the strategy grid) — this is the formal link between the snooping correction and the Sharpe report. A strategy with high $\widehat{SR}$ but $\widehat{\text{DSR}}<0.95$ is not credible after accounting for the search.

### 8.3 Minimum Track Record Length (MinTRL)

The smallest $T$ at which $\widehat{SR}$ is statistically greater than $SR_0$ at confidence $1-\alpha$ ([Bailey & López de Prado 2014](https://doi.org/10.3905/jpm.2014.40.5.094)):

$$
\text{MinTRL} = 1 + \left(1 - \hat\gamma_3\,\widehat{SR} + \tfrac{\hat\gamma_4-1}{4}\,\widehat{SR}^{\,2}\right)\left(\frac{z_{1-\alpha}}{\widehat{SR}-SR_0}\right)^2 .
$$

This is the Sharpe-space analogue of the Section 6 power calc and gives a second, moment-aware lower bound on required sample size; it should be reported alongside the count-based $n$. The backtest-overfitting framing and the related minimum-backtest-length result are in [Bailey, Borwein, López de Prado & Zhu (2014, Notices AMS)](https://www.ams.org/notices/201405/rnoti-p458.pdf).

### 8.4 Worked PSR

Suppose the expanded-universe underdog-DNB backtest yields per-bet $\widehat{SR}=0.045$, $T=5000$, $\hat\gamma_3=+0.6$ (positive, the correct sign for per-bet underdog DNB — verified by direct moment computation over realistic de-vig'd 1X2 vectors, which gives skew in $[+0.4,+2.4]$), $\hat\gamma_4=4.5$, against $SR_0=0$. Denominator $=\sqrt{1-(+0.6)(0.045)+\tfrac{4.5-1}{4}(0.045)^2}=\sqrt{1-0.027+0.00177}=\sqrt{0.97477}=0.9873$. Numerator $=0.045\sqrt{4999}=0.045\times70.70=3.182$. PSR $=\Phi(3.182/0.9873)=\Phi(3.223)\approx0.99936$. The same $\widehat{SR}$ at $T=384$ (WC-only): numerator $=0.045\sqrt{383}=0.045\times19.57=0.881$, PSR $=\Phi(0.881/0.9873)=\Phi(0.892)\approx0.814$ — below conventional thresholds. The positive skew *raises* PSR slightly relative to the negatively-skewed counterfactual (denominator $0.9873$ vs $1.0143$, PSR $0.99936$ vs $0.99915$ at $T=5000$), so the favorable skew does not rescue the small sample: the conclusion that **$T$ must grow** is preserved, and now for the correct reason — it is the kurtosis-inflated SE and the small $\widehat{SR}$, not a (nonexistent) negative skew penalty, that demand a large $T$. (If $SR_0$ is deflated to $SR_0^\star>0$ from a large grid, even the $T=5000$ case can fall below 0.95; the DSR is the binding test.)

---

## 9. Walk-forward / time-ordered validation and leakage canary

### 9.1 No k-fold

Per the project's time-series-integrity rules, k-fold CV is prohibited because it trains on future data. Validation is **walk-forward**: estimate parameters (e.g. the de-vig model, any threshold) on data up to time $t$, evaluate on $(t, t+\Delta]$, roll forward. Splits are time-ordered and disjoint; the World Cup is the final held-out block. Every feature must be computable at $t$ from information available at $t$ (no closing odds used as a feature when betting at the open, no full-season strength ratings leaking into mid-season bets).

### 9.2 Point-in-time leakage canary

Per the project's pit-canary skill: inject a deliberately constructed **future-knowing feature** (e.g. the realized match result, or the *closing* line when betting at the open) into the pipeline. If that oracle feature does **not** dominate the legitimate feature set in the walk-forward evaluation, the pipeline already leaks future information and the result is invalid. This is a falsification test run before any performance number is trusted. A concrete canary for this project: confirm that swapping opening for closing odds *changes* the bet set — if it does not, the pipeline is silently reading closing odds.

---

## 10. Assumption checks

| Assumption | Why it matters | Test / diagnostic |
|---|---|---|
| **Stationarity** of $\{R_i\}$ | Bootstrap & HAC validity; Sharpe annualization | ADF and Phillips–Perron unit-root tests; KPSS (null = stationary) as complement; rolling-mean/variance plots; structural-break test for regime shifts (e.g. rule changes, VAR introduction 2018). Report the bandwidth-free KPSS alongside ADF since they have opposite nulls. |
| **Independence / serial dependence** | IID bootstrap & OLS SE invalid if violated | Ljung–Box on $R_i$ and on $|R_i|$/$R_i^2$ (volatility clustering); sample ACF/PACF; runs test. The estimated $\hat\gamma_k$ feed the Politis–White block length (3.3) and the $\eta(q)$ scaling (2.3). |
| **Distributional form** | Gaussian Sharpe inference invalid; choose robust SE | Jarque–Bera / D'Agostino for normality (expected to reject); report $\hat\gamma_3,\hat\gamma_4$ explicitly since they enter PSR/DSR; QQ-plot vs normal; check for the $-1$ floor and discrete payoff mass. |
| **Cross-sectional dependence** | Same-day/same-tournament bets correlated | Block on match-day; the joint circular-block bootstrap (Section 4) preserves it. |

Any rejection routes to the corresponding robust method already specified (block bootstrap for dependence, moment-corrected SE for non-normality), so the diagnostics are decision-linked rather than decorative.

---

## Citations

Full references with verified DOIs / stable URLs. Verification protocol (re-run 2026-06-16 with network access): each journal DOI was resolved against the CrossRef REST record (`api.crossref.org/works/{doi}`) and the returned title / container-title / volume / issue / page-range / year confirmed to match the citation below; non-DOI items (AMS Notices PDF, Mertens discussion note, Ottaviani–Sørensen chapter, football-data.co.uk notes) were confirmed live or confirmed via the publisher's issue/table-of-contents index. Nineteen journal DOIs resolved exactly (including Hegarty & Whelan 2025, `10.1016/j.ijforecast.2024.06.013`, IJF 41(2):803–820, added in this revision and CrossRef-confirmed). Two items required URL correction and are flagged in-line: the Ottaviani–Sørensen Elsevier book-chapter DOI `10.1016/B978-0-444-50744-0.50009-3` does **not** resolve (404 on both CrossRef and doi.org) and has been replaced with the ScienceDirect chapter PII URL; the Mertens (2002) discussion-note deep link `…/discussion/soprano01.pdf` now 404s and has been repointed to the author's stable research homepage, with the substantive formula anchored to the verified Bailey & López de Prado (2014) and Lo (2002) DOIs (see resolved open question #2).

1. Andrews, D. W. K. (1991). "Heteroskedasticity and Autocorrelation Consistent Covariance Matrix Estimation." *Econometrica* 59(3): 817–858. https://doi.org/10.2307/2938229
2. Angelini, G., & De Angelis, L. (2019). "Efficiency of online football betting markets." *International Journal of Forecasting* 35(2): 712–721. https://doi.org/10.1016/j.ijforecast.2018.07.008
3. Bailey, D. H., Borwein, J. M., López de Prado, M., & Zhu, Q. J. (2014). "Pseudo-Mathematics and Financial Charlatanism: The Effects of Backtest Overfitting on Out-of-Sample Performance." *Notices of the American Mathematical Society* 61(5): 458–471. https://www.ams.org/notices/201405/rnoti-p458.pdf
4. Bailey, D. H., & López de Prado, M. (2014). "The Deflated Sharpe Ratio: Correcting for Selection Bias, Backtest Overfitting, and Non-Normality." *The Journal of Portfolio Management* 40(5): 94–107. https://doi.org/10.3905/jpm.2014.40.5.094
5. Benjamini, Y., & Hochberg, Y. (1995). "Controlling the False Discovery Rate: A Practical and Powerful Approach to Multiple Testing." *Journal of the Royal Statistical Society: Series B* 57(1): 289–300. https://doi.org/10.1111/j.2517-6161.1995.tb02031.x
6. Hansen, P. R. (2005). "A Test for Superior Predictive Ability." *Journal of Business & Economic Statistics* 23(4): 365–380. https://doi.org/10.1198/073500105000000063
7. Hegarty, T., & Whelan, K. (2025). "Forecasting soccer matches with betting odds: A tale of two markets." *International Journal of Forecasting* 41(2): 803–820. https://doi.org/10.1016/j.ijforecast.2024.06.013
8. Hoenig, J. M., & Heisey, D. M. (2001). "The Abuse of Power: The Pervasive Fallacy of Power Calculations for Data Analysis." *The American Statistician* 55(1): 19–24. https://doi.org/10.1198/000313001300339897
9. Ledoit, O., & Wolf, M. (2008). "Robust performance hypothesis testing with the Sharpe ratio." *Journal of Empirical Finance* 15(5): 850–859. https://doi.org/10.1016/j.jempfin.2008.03.002
10. Lo, A. W. (2002). "The Statistics of Sharpe Ratios." *Financial Analysts Journal* 58(4): 36–52. https://doi.org/10.2469/faj.v58.n4.2453
11. Mertens, E. (2002). "Comments on the Correct Variance of Estimated Sharpe Ratios in Lo (2002, FAJ) When Returns Are IID." Discussion note (unpublished, self-hosted; no journal DOI). Author research page: https://www.elmarmertens.com/research/ (historic deep link `…/discussion/soprano01.pdf` now returns 404). The note's non-normality-robust Sharpe-SE result is independently and authoritatively given as eq. 4 of Bailey & López de Prado (2014) [ref. 4] and in Lo (2002) [ref. 10], both DOI-verified, so the attributed formula stands irrespective of the note's link stability.
12. Newey, W. K., & West, K. D. (1994). "Automatic Lag Selection in Covariance Matrix Estimation." *The Review of Economic Studies* 61(4): 631–653. https://doi.org/10.2307/2297912
13. Opdyke, J. D. (2007). "Comparing Sharpe ratios: So where are the p-values?" *Journal of Asset Management* 8(5): 308–336. https://doi.org/10.1057/palgrave.jam.2250084
14. Ottaviani, M., & Sørensen, P. N. (2008). "The Favorite-Longshot Bias: An Overview of the Main Explanations." In *Handbook of Sports and Lottery Markets* (Hausch & Ziemba, eds.), Elsevier, ch. 6, pp. 83–101. ScienceDirect chapter: https://www.sciencedirect.com/science/article/pii/B9780444507440500093 (the previously cited DOI `10.1016/B978-0-444-50744-0.50009-3` does not resolve and has been retired here). Author-hosted survey PDF (verified live): https://web.econ.ku.dk/sorensen/papers/FLBsurvey.pdf
15. Patton, A., Politis, D. N., & White, H. (2009). "Correction to 'Automatic Block-Length Selection for the Dependent Bootstrap' by D. Politis and H. White." *Econometric Reviews* 28(4): 372–375. https://doi.org/10.1080/07474930802459016
16. Politis, D. N., & Romano, J. P. (1994). "The Stationary Bootstrap." *Journal of the American Statistical Association* 89(428): 1303–1313. https://doi.org/10.1080/01621459.1994.10476870
17. Politis, D. N., & White, H. (2004). "Automatic Block-Length Selection for the Dependent Bootstrap." *Econometric Reviews* 23(1): 53–70. https://doi.org/10.1081/ETC-120028836
18. Romano, J. P., & Wolf, M. (2005). "Stepwise Multiple Testing as Formalized Data Snooping." *Econometrica* 73(4): 1237–1282. https://doi.org/10.1111/j.1468-0262.2005.00615.x
19. Štrumbelj, E. (2014). "On determining probability forecasts from betting odds." *International Journal of Forecasting* 30(4): 934–943. https://doi.org/10.1016/j.ijforecast.2014.02.008
20. White, H. (2000). "A Reality Check for Data Snooping." *Econometrica* 68(5): 1097–1126. https://doi.org/10.1111/1468-0262.00152
21. Football-Data.co.uk. "Notes — football results and betting odds data; column definitions (Pinnacle `PSH/PSD/PSA`, closing `PS*C`, Asian-Handicap `AHh`, `MaxAHH/AvgAHH`)." https://www.football-data.co.uk/notes.txt

---

## Open questions and assumptions to validate

1. **Output path placeholders.** The prompt's literal target path contained `undefined/docs/research/research_statistical-methodology_undefined.md`. Resolved to the project root [worldcup-underdog-dnb-backtest/docs/research/research_statistical-methodology_2026-06-16.md](docs/research/research_statistical-methodology_2026-06-16.md) per the CLAUDE.md `{type}_{description}_{YYYY-MM-DD}.md` convention. Confirm the date-stamped filename is the intended artifact name.
2. **Mertens (2002) DOI — RESOLVED 2026-06-16.** The earlier conjecture that this item carries a CFA-Institute "comment" DOI (`10.2469/faj.v58.n6.2480-comment`, minted under the parent Lo article) was tested and is **incorrect**: the Mertens item is a self-hosted, unpublished discussion note with **no** journal DOI of any kind, so no CFA-Institute record exists to reassign. The historic deep link `…/research/discussion/soprano01.pdf` now 404s; the citation has been repointed to the author's stable research homepage (https://www.elmarmertens.com/research/). The non-normality-robust Sharpe-SE formula attributed to the note is independently DOI-verified as eq. 4 of Bailey & López de Prado (2014) and in Lo (2002), so the equation is fully sourced regardless of the note's link stability. No further action; closed.
3. **DSR independence assumption.** The DSR $E[\max]$ expression assumes $N$ **independent** trials; the strategy grid (correlated staking/threshold variants on the same matches) is strongly dependent, so effective $N_{\text{eff}}<N$. Estimate $N_{\text{eff}}$ (e.g. via the dominant eigenvalues of the strategy-return correlation matrix or a clustering of trials) before applying DSR, or treat the raw-$N$ DSR as conservative.
4. **Per-bet vs per-period inference.** Whether the inferential unit is the individual bet or a calendar period (week/tournament) changes the serial-dependence structure and the annualization $\eta(q)$. Decide and pre-register; the block bootstrap must match the chosen unit.
5. **DNB variance reduction.** The exact $\operatorname{Var}(R^{\text{DNB}})$ vs straight-win variance should be computed empirically per odds bucket from the league data and compared with the analytic $(o-1)$ benchmark; the power table (Section 6.3) currently uses the straight-win $\sigma^2=o-1$ as an upper bound on DNB variance.
6. **Synthetic-DNB closing line.** Verify that the closing 1X2 columns (`PSCH/PSCD/PSCA`) are present and populated across the full league panel; if closing AH-0 columns exist, cross-check $A(D-1)/D$ against the direct closing AH-0 quote to validate the synthetic identity and quantify the basis.
7. **Bootstrap block length stability.** Run the Politis–White (2004) selector on $\{R_i\}$ and report sensitivity of the Sharpe CI to $\pm 50\%$ perturbation of $\hat b$; large sensitivity flags a long-memory or break problem.
8. **Multiple-testing register completeness.** The honesty of White/Hansen/DSR depends on $K$ (and $N$) being fixed *before* fitting. Confirm the register in `config/multipletest_family.yaml` enumerates every side/staking/threshold/odds-source combination actually examined, including abandoned ones.
9. **Stationarity across the 2018 VAR introduction and 2026 format change.** Test for a structural break in $\{R_i\}$ at the VAR rule change and treat the 104-match 2026 format as a potential regime shift when the World Cup is used as the held-out block.
