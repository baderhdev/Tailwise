# Tailwise

How well can standard risk models estimate the risk of a Saudi (Tadawul) equity portfolio
out of sample, and where do they fail?

This is a student portfolio project. Results are reported as they come out, including bad ones.

## Summary of findings

- **Simple baselines are hard to beat.** GARCH-CCC ranks first for covariance forecasts but its
  edge over the plain 250-day sample covariance is not statistically significant; Ledoit-Wolf
  shrinkage makes no practical difference; and a minimum-variance portfolio built from GARCH does
  *worse* after costs than one built from the sample covariance.
- **Normal VaR fails** (too many breaches, ES too small). Fat-tailed and historical VaR get the
  breach count roughly right overall but fail in turbulent markets. Only GARCH-filtered historical
  simulation passes every coverage test, and it is too conservative at 99% in calm markets.
- **Market regimes from TASI** show the failure clearly: in TASI-turbulent periods the three
  window-based VaR models are breached two to five times as often as they should be.
- **TASI's longer history puts the sample in context.** March 2020 was TASI's worst 21-session
  window since 2013, but August 2015 came close; the 2014–16 oil-price decline took TASI down 51%
  over two years, a stress the stock sample never contains.
- **The equal-weight portfolio beat TASI** by 1.8 points a year in price terms, with beta 0.97.
  That is most likely survivorship and equal-weighting, not skill (see Known Limitations).

## Status

| Phase | Content | State |
|---|---|---|
| 1 | Data pipeline and exploratory stats | done |
| 1b | TASI benchmark: relative performance and beta | done |
| 2 | Covariance estimation (sample, Ledoit-Wolf, GARCH) | done |
| 3 | VaR / Expected Shortfall backtests | done |
| 4 | Volatility regimes | done |
| 5 | Historical stress replay, Brent sensitivity | done |
| 6 | Allocation (optional) | done |

## Reproduce

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt   # Windows; .venv/bin/python elsewhere
.venv/Scripts/python run.py --refresh  # first run on a fresh clone: downloads Yahoo data into data/raw
.venv/Scripts/python run.py            # later runs reuse that cached snapshot
.venv/Scripts/python -m pytest
```

Yahoo Finance data is not redistributed in this repository, so a fresh `--refresh` download
may differ slightly from the snapshot behind the committed results (Yahoo revises history).
The TASI file is included. Everything is deterministic given the same raw data: two full reruns
reproduce every output file byte for byte.

## Data

- **Stocks:** daily prices from Yahoo Finance via `yfinance` (`.SR` tickers), cached as raw CSVs in
  `data/raw/` so reruns use the same snapshot. Returns are simple daily total returns from
  Yahoo's dividend- and split-adjusted close (`Adj Close`).
- **Benchmark (TASI):** the Saudi Exchange (Tadawul) official historical reports, TASI daily
  history, 2013-01-01 to 2026-10-20 (3,443 sessions), in
  `data/raw/TASI_daily_close_2013-01-01_to_2026-10-20.csv`. **TASI is a price index: dividends
  are not reinvested.** Every comparison with TASI therefore uses the stocks' *price* returns
  (split-adjusted close, no dividends); risk models elsewhere use total returns. Yahoo has no
  usable TASI history (`^TASI.SR` returns one bar). Schema, enforced on load and tested:
  `Date` (YYYY-MM-DD, strictly increasing, unique) and `Close` (numeric, positive). The file
  passes range checks (5,416 to 13,820) and its largest daily move is −8.7% on 2020-03-08.
  Before 29 June 2013 the exchange traded Saturday to Wednesday; those sessions are real.
- **Oil:** Brent front-month futures from Yahoo (`BZ=F`), Phase 5 only.
- **Sample:** 2019-12-11 (Saudi Aramco's listing) to 2026-10-20: 1,646 stock-panel dates.
  TASI's history before 2019-12-11 is used only for market regimes (Phase 4) and the stress
  replay of 2014–16 (Phase 5), always walk-forward.

### Calendar alignment

Stocks and TASI are joined on trading dates (inner join, no forward-filling). In the sample,
TASI has 1,711 sessions and the stock panel 1,646 dates: **0 stock dates are dropped** (every
panel date is a real TASI session) and **65 TASI sessions are dropped** (3.8%) because Yahoo has
no usable prices for them (by year: 2020 6, 2021 7, 2022 10, 2023 20, 2024 10, 2025 10, 2026 2).
Returns after a missing session span it: 54 panel returns cover more than one session, at most
4. Each dropped session is listed in the cleaning log.

### Universe (hand-picked)

24 large, liquid stocks that traded continuously over the whole sample:

| Sector | Stocks |
|---|---|
| Energy & petrochemicals | 2222 Aramco, 2010 SABIC, 2020 SABIC Agri-Nutrients, 2310 Sipchem, 2350 Saudi Kayan, 2290 Yansab |
| Materials | 1211 Ma'aden |
| Banks | 1120 Al Rajhi, 1180 SNB, 1010 Riyad, 1060 SAB, 1150 Alinma, 1140 Albilad, 1080 ANB |
| Telecom & utilities | 7010 stc, 7020 Mobily, 7030 Zain KSA, 5110 Saudi Electricity |
| Consumer & health | 2280 Almarai, 4190 Jarir, 4002 Mouwasat, 8210 Bupa Arabia |
| Other | 4300 Dar Al Arkan, 4030 Bahri |

Screened out: Petro Rabigh and Savola (capital restructurings that Yahoo's adjustment does not
handle cleanly), Banque Saudi Fransi (30 missing trading days), Saudi Cement (too illiquid).

### Cleaning decisions

Every action is written to `data/processed/cleaning_log.csv` with ticker, date, and detail.

| Step | Rule | Why | Effect |
|---|---|---|---|
| Filler rows | Drop rows with zero volume or missing price | Yahoo inserts carried-forward, zero-volume bars on holidays and outages; large caps never really trade zero shares | 1,295 stock-days |
| Spike reversal | Drop a day that moves >10% and reverses by >10% the next day | Bad prints beyond Tadawul's ±10% daily limit. An earlier version also required very low volume, but Yahoo's volumes are unreliable (limitation 4) and it caught nothing | 1 day: Ma'aden 2023-06-08 (+51%, then −34%) |
| Common calendar | Keep only dates on which all 24 stocks have a valid price | One calendar for covariance estimation; the next return then spans the gap for every stock alike | 38 dates dropped |
| TASI join | Inner join with TASI sessions; no forward-fill | Benchmark and stocks on identical dates | 0 stock dates, 65 TASI sessions dropped |
| Over-limit flag | Log, but keep, any return beyond ±10% | Most are two-day returns across a dropped date; deleting real tail events would flatter the risk models | 14 returns |
| Stale prices | Log runs of >5 unchanged closes with real volume | Detects frozen price feeds | none in sample |

The spike rule looks one day ahead to decide that day *t* was a bad print. It is a data
correction (as a vendor would make), not a model input.

## Phase 1 results: what the data looks like

Full-sample descriptive statistics (`results/phase1/summary_stats.csv`), not used by any model.

- **Volatility:** annualised volatility ranges from 16.5% (Aramco) to 34.6% (Ma'aden). The
  equal-weight (EW) portfolio runs at 15.3%, well below any single stock: diversification does
  real work here. Annualised with the panel's 240 observations per calendar year (see Known
  Limitations 3 and 18).
- **Correlation:** mean pairwise correlation is 0.32. Banks form the tightest block (up to 0.61),
  followed by the petrochemicals. Healthcare, insurance, and Ma'aden are the least connected.
  The 120-day average correlation swung from 0.60 (2020) to 0.14 (late 2021), so a single
  full-sample correlation matrix hides a lot.
- **Fat tails:** every stock rejects normality (Jarque-Bera p ≈ 0). The EW portfolio has
  excess kurtosis 11.6 and skew −0.87: moves beyond 3 standard deviations happen on 1.16% of
  days versus 0.27% under a normal, and the large ones are mostly on the downside.
  This is a first warning for any normal (parametric) VaR.
- **Volatility clustering:** 60-day EW volatility ranged from about 7% to 41% (peak May 2020).
- **TASI** (price index, same dates): volatility 15.1%, skew −1.17, excess kurtosis 12.6, moves
  beyond 3 standard deviations on 1.28% of days. The market index is as fat-tailed as the
  portfolio.

![Rolling vol and correlation](results/phase1/rolling_vol_corr.png)
![EW return distribution](results/phase1/ew_return_distribution.png)

## Benchmark results: the portfolios against TASI

Price returns on both sides (TASI has no dividends), annualised by calendar time
(`results/benchmark/relative_performance.csv`). Beta is walk-forward: the beta used for day *t*
is estimated on the 250 days before *t*. A full-sample beta is shown for description only.

| Series | Price return p.a. | Volatility | vs TASI p.a. | Tracking error | Correlation | Beta (full sample) | Walk-forward beta range |
|---|---|---|---|---|---|---|---|
| equal_weight | 4.8% | 15.3% | +1.8 | 4.5% | 0.96 | 0.97 | 0.89–1.01 |
| random 1–5 | 2.5% to 5.1% | 15.4–17.1% | −0.5 to +2.1 | 5.3–9.0% | 0.84–0.94 | 0.90–1.02 | 0.81–1.17 |
| TASI | 3.0% | 15.1% | — | — | — | — | — |

- **The portfolios are market portfolios.** Correlation with TASI is 0.84–0.96 and beta is close
  to 1; walk-forward beta for equal-weight stayed between 0.89 and 1.01.
- **Equal-weight beat TASI by 1.8 points a year in price terms.** Do not read this as skill: the
  24 stocks were picked in 2026 as survivors, and equal-weighting underweights Aramco, which is a
  large part of TASI. Four of the five random portfolios also beat TASI.
- **Dividends matter a lot here.** The equal-weight total return was 8.2% a year against a 4.8%
  price return, so about 3.4 points a year come from dividends that TASI does not include.

![EW vs TASI](results/benchmark/ew_vs_tasi.png)

## Phase 2 results: covariance forecasts

**Setup.** On the first trading day of each block of 21 days (66 non-overlapping months,
Dec 2020 – Sep 2026), each method forecasts the covariance of the next 21 daily returns using
only data before that day. The forecast variance of a fixed portfolio is compared with its
realised variance (sum of squared daily returns over the 21 days).

| Method | What it is |
|---|---|
| `sample_250` | Sample covariance of the last 250 days |
| `ledoit_wolf_250` | Ledoit-Wolf (2004) shrinkage toward a scaled identity, last 250 days (checked against scikit-learn in the tests) |
| `garch_ccc` | GARCH(1,1) per stock for the 21-day variance, fitted on all data to date; correlation of standardised residuals over the last 250 days |
| `sample_expanding` | Sample covariance of all data to date. A control: GARCH sees all history, so this checks whether its edge is just more data |

Test portfolios: equal-weight plus 5 random long-only portfolios (Dirichlet(1) weights, seed 2026,
saved in `results/phase2/test_portfolios.csv`). Main loss: QLIKE (Patton 2011), which ranks
forecasts correctly even though one month of realised variance is a noisy target. Uncertainty:
Diebold-Mariano test on monthly loss differences against `sample_250`, Newey-West standard errors.

**Equal-weight portfolio** (`results/phase2/evaluation.csv` has all six):

| Method | QLIKE (lower is better) | vs sample_250 (95% CI) | DM p | mean realised / mean forecast | months realised > forecast |
|---|---|---|---|---|---|
| garch_ccc | 0.281 | −0.053 (−0.123, +0.016) | 0.13 | 0.84 | 30% |
| sample_250 | 0.335 | — | — | 0.89 | 33% |
| ledoit_wolf_250 | 0.343 | +0.008 (−0.019, +0.035) | 0.55 | 0.97 | 33% |
| sample_expanding | 0.372 | +0.037 (−0.089, +0.164) | 0.56 | 0.61 | 14% |

**What this says**

- **GARCH ranks first on all six portfolios, but the win is not statistically significant.**
  Its QLIKE is about 16% lower than the sample covariance's, and every 95% interval includes zero
  (p = 0.13–0.31). With 66 months, this test cannot separate the three main methods.
- **The GARCH edge comes from a few months.** The two largest gains are the months starting
  2025-03-18 (the April 2025 sell-off) and 2022-05-11, where GARCH had already raised its
  forecast and the 250-day sample had not. In calm months GARCH is slightly worse.
- **It is not just more data.** The expanding-window sample covariance uses the same history as
  GARCH and is the worst method: it never forgets 2020, so it over-forecasts risk by about 40%
  on average.
- **Ledoit-Wolf makes no practical difference here.** With 24 stocks and 250 days the sample
  covariance is already well estimated; the shrinkage intensity averages 10%. Shrinkage would
  matter for larger universes or shorter windows, which this project does not have.
- **Every method misses the spikes.** All of them under-forecast the sharpest months (May 2022,
  April 2025, September 2025) and over-forecast in calm ones. Monthly risk forecasts from past
  data react to a shock only after it starts.
- **The six test portfolios are nearly one test.** Long-only random weights spread across 24
  stocks behave like the equal-weight portfolio: the monthly loss differences correlate at 0.80
  or more across portfolios. Six wins are not six independent pieces of evidence.

![EW forecast vs realised](results/phase2/ew_forecast_vs_realised.png)

## Phase 3 results: VaR and Expected Shortfall backtests

**Setup.** Every trading day from December 2020 (1,395 days), each model forecasts the next
day's 95% and 99% VaR and ES for the six Phase 2 test portfolios, using only earlier returns.
Portfolio weights are held fixed (equivalent to daily rebalancing).

| Model | How the forecast is made |
|---|---|
| `historical` | Empirical quantile of the last 250 daily returns; ES is the mean of the returns beyond it |
| `normal` | Normal distribution with the mean and standard deviation of the last 250 days |
| `student_t` | Student-t fitted by maximum likelihood to the last 250 days |
| `fhs_garch` | Filtered historical simulation: GARCH(1,1) on the portfolio return (refitted every 21 days, volatility updated daily) scaled by the empirical quantile of all standardised residuals to date |

Backtests: exceedance count against the expected 5% / 1%, Kupiec unconditional coverage test,
Christoffersen independence test (are exceedances clustered?), conditional coverage (both),
and an ES check: on exceedance days, is the realised loss larger than the forecast ES on average
(one-sided t-test, McNeil-Frey style)? Full results in `results/phase3/backtest.csv`.

**Equal-weight portfolio**

| Model | Level | Exceedances (expected) | Kupiec p | Independence p | Cond. coverage p | Realised loss / forecast ES |
|---|---|---|---|---|---|---|
| historical | 95% | 69 (70) | 0.93 | **0.006** | **0.024** | 1.03 |
| historical | 99% | **24 (14)** | **0.014** | 0.41 | **0.035** | 0.95 |
| normal | 95% | 58 (70) | 0.14 | **0.002** | **0.003** | **1.26** |
| normal | 99% | **26 (14)** | **0.004** | **0.010** | **0.001** | **1.28** |
| student_t | 95% | 74 (70) | 0.61 | **0.001** | **0.005** | 1.05 |
| student_t | 99% | 20 (14) | 0.13 | 0.27 | 0.17 | 1.06 |
| fhs_garch | 95% | 70 (70) | 0.98 | 0.40 | 0.70 | 0.90 |
| fhs_garch | 99% | 8 (14) | 0.08 | 0.76 | 0.21 | 0.96 |

Bold: rejected at 5%. Across all six portfolios, number of rejections of conditional coverage:
historical 5 (95%) and 3 (99%), normal 4 and 5, Student-t 3 and 2, FHS-GARCH 0 and 0.

**What this says**

- **The normal model fails, as Phase 1 predicted.** At 99% it has nearly twice the expected
  exceedances on every portfolio, and when it is breached the loss is about 25% larger than its
  ES forecast (ES rejected on all six portfolios at both levels). Fat tails break it.
- **Fat tails alone fix the count but not the timing.** Student-t gets the 99% rate roughly right
  and its ES is not rejected, but at 95% its exceedances cluster (independence rejected on 4 of 6
  portfolios). A fixed 250-day window cannot react when volatility jumps, so breaches arrive in
  bunches: late 2021, mid-2022, 2024.
- **Historical simulation has the same clustering problem**, and at 99% it is also breached too
  often (1.3–1.7% vs 1%): with 250 observations its 99% quantile rests on the 2–3 worst days of
  the past year.
- **FHS-GARCH is the only model never rejected**, because its volatility updates daily and
  removes the clustering. But it is **too conservative at 99%**: 0.5–0.6% exceedances versus
  1%, significantly too few on 2 of 6 portfolios, and its 95% ES runs about 10% above realised
  losses. Likely cause: its residual tail includes the 2020 crash; that is a capital cost, not a
  risk failure, but it is still a miss.
- **The tests have little power at 99%.** About 14 exceedances are expected in the whole period,
  so 8 or 20 are not significantly different from 14. The 99% verdicts are weaker than the
  95% ones.

![EW 99% VaR](results/phase3/ew_var99.png)

**Bug found and fixed during this phase:** scipy's default Student-t fit sometimes stopped at a
worse local optimum (degrees of freedom below 2), producing one-day spikes in the t VaR on 74 days.
The fit now starts from two points and keeps the higher likelihood (tested). This is a numerical
fix, not a model change; the 99% exceedance count was 20 before and after.

## Phase 4 results: where the models fail, by market regime

**Setup.** Regimes are defined on the market, TASI, not on the test portfolios. A 2-state
Gaussian hidden Markov model (HMM) runs on TASI daily returns on TASI's own calendar since 2013,
refitted every 21 sessions on all TASI history to date (best of 5 seeded starts). The label for
day *t* is the predicted probability of the turbulent state given TASI returns **before** *t*
only: a risk manager could have known it that morning. Day *t* is "turbulent" when that probability
is above 0.5. Cross-check: a simple threshold (trailing 21-session TASI volatility above its
own median to date). Tests check both labelings for lookahead.

Since 2014, the HMM labels 25% of TASI sessions turbulent, with 2015 and 2016 the most turbulent
years. In the Phase 3 test period it labels 217 of 1,395 days (16%) turbulent, in episodes such
as late 2021, May–July and September–October 2022, mid-2024, and April and June 2025. The
threshold labels 41%; the two agree on 73% of test days.

![HMM regimes](results/phase4/hmm_regimes.png)

**VaR exceedance rate by TASI-HMM regime, EW portfolio** (`results/phase4/var_by_regime_*.csv`)

| Model | 95% calm (exp. 5%) | 95% turbulent | 99% calm (exp. 1%) | 99% turbulent |
|---|---|---|---|---|
| historical | 4.1% | **9.7%** | 1.4% | **3.7%** |
| normal | **3.2%** | **9.2%** | 1.3% | **5.1%** |
| student_t | 4.2% | **11.1%** | 1.1% | **3.2%** |
| fhs_garch | 5.0% | 5.1% | **0.4%** | 1.4% |

1,178 calm days, 217 turbulent days. Bold: Kupiec test rejects at 5%. Across all six portfolios,
historical and Student-t VaR are rejected in the turbulent regime on all six at both levels,
normal on all six at 99% and three at 95%; FHS-GARCH on none. In calm periods FHS-GARCH is
rejected at 99% on four of six portfolios for having too *few* breaches (0.3–0.5%).

**What this says**

- **The window-based models fail when the market is turbulent.** Historical, normal, and
  Student-t VaR are breached on 9–11% of turbulent days instead of 5%, and 3–5% instead of 1%.
  Their aggregate Phase 3 numbers looked tolerable because most days are calm.
- **FHS-GARCH is the only model that holds in turbulent markets** (5.1% and 1.4%, not rejected).
  Its weakness is the opposite: in calm markets it is too conservative at 99%.
- **Fat tails are not the fix; reaction speed is.** Student-t is no better than historical in
  turbulent periods. What separates the models is whether their volatility updates daily.
- **The threshold cross-check agrees.** On its turbulent days the window models run at 2.5–3.2%
  at 99% for equal-weight and are rejected on 5–6 of 6 portfolios; FHS-GARCH at 1.1%, never rejected.
- **For covariance forecasts the regime split does not favour GARCH.** Only 8 of 66 Phase 2
  months start TASI-turbulent. On the threshold split (28 turbulent months), GARCH-CCC has the
  lowest QLIKE in calm months (0.29 vs 0.39 for the sample covariance) but not in turbulent ones
  (0.27 vs 0.25). Too few months to conclude anything.
- **What changed from the earlier version.** Regimes were first defined on the equal-weight
  portfolio's own returns since December 2019, which labelled only 7% of test days turbulent and
  gave more extreme breach rates (14–17% at 95%). Defining them on TASI, with its longer history,
  labels a broader set of days. The conclusions are the same; the magnitudes are smaller.

## Phase 5 results: stress replay and oil sensitivity

### Historical episodes

The worst non-overlapping 10- and 21-trading-day windows for the equal-weight (EW) portfolio are
found in the data, then replayed on all six test portfolios (`results/phase5/episodes.csv`). The
"context" column is my annotation of widely reported events, not something derived from the data.
For episodes after the first year, the last column compares the loss with the 1-day 99% VaR each
model forecast the day before the episode started, scaled by √days (which assumes independent
days; with volatility clustering this understates multi-day risk). TASI's loss over the same
dates is in `episodes.csv` (price return), with the equal-weight price-return loss predicted
from its walk-forward beta to TASI before the episode.

| Window | Dates | EW loss | Random portfolios | Context | Loss ÷ scaled 99% VaR (FHS / hist / normal / t) |
|---|---|---|---|---|---|
| 21d | 2020-02-20 → 03-23 | 22.4% | 18–27% | COVID onset and the OPEC+ price war (Brent −30% in two consecutive weeks) | no model yet |
| 10d | 2020-02-23 → 03-09 | 20.2% | 19–21% | same | no model yet |
| 10d | 2022-05-09 → 05-23 | 10.4% | 8–12% | 2022 global rate-hike sell-off | 1.28 / 1.44 / 2.02 / 1.79 |
| 21d | 2022-04-17 → 05-23 | 11.3% | 9–13% | same | 0.98 / 1.08 / 1.56 / 1.37 |
| 10d | 2022-06-07 → 06-20 | 9.2% | 9–11% | same | 0.73 / 1.12 / 1.53 / 1.29 |
| 21d | 2022-06-12 → 07-14 | 10.1% | 9–11% | same | 0.65 / 0.85 / 1.15 / 0.97 |
| 21d | 2022-08-28 → 09-26 | 11.8% | 10–14% | September 2022 global sell-off | 0.87 / 0.73 / 1.12 / 0.93 |
| 21d | 2022-11-08 → 12-11 | 11.1% | 10–13% | not verified; banks led the decline | 0.80 / 0.69 / 0.95 / 0.84 |
| 10d | 2020-10-19 → 11-01 | 8.4% | 8–10% | not verified | no model yet |
| 10d | 2021-11-15 → 11-30 | 8.0% | 7–9% | includes the Omicron news of 26 Nov 2021 | 1.32 / 1.78 / 2.00 / 1.87 |

- **March 2020 is the worst episode in the stock sample** (20–22% in two to four weeks, about
  twice any later one) and the one no model could be tested on, because the sample starts three
  months before it. TASI's longer history shows it is not unique (next section).
- **TASI fell more than the portfolio in 8 of 10 episodes** (price terms). For the seven
  episodes with a pre-episode beta, beta × TASI's loss predicted the equal-weight price loss to
  within 2.2 points each time (for example 10.6% predicted vs 10.6% in May 2022, 9.4% vs 11.6%
  in April–May 2022). These are moderate sell-offs; whether the linear beta holds in a crash like
  March 2020 cannot be tested here.
- **Every model's scaled 99% VaR was exceeded by at least one episode.** The normal model was
  exceeded by 6 of 7 testable episodes, FHS-GARCH by 2 of 7 (both short, sharp 10-day drops). Even the best model's 99% number is not a worst case.
- **Diversification barely helps in a stress episode.** The random portfolios lose about the
  same as equal-weight in every episode; in March 2020 the worst stocks were banks, not oil names.

### TASI's longer history: 2014–16 and March 2020 in context

The stock sample starts in December 2019, but TASI goes back to 2013
(`results/phase5/tasi_episodes.csv`, `oil_decline_2014_16.csv`).

| Rank | TASI's worst 10 sessions since 2013 | TASI's worst 21 sessions since 2013 |
|---|---|---|
| 1 | 2016-01-04 → 01-17: −20.6% | 2020-02-24 → 03-23: −25.0% |
| 2 | 2015-08-11 → 08-24: −20.5% | 2015-07-27 → 08-24: −24.5% |
| 3 | 2020-03-04 → 03-17: −19.2% | 2015-12-23 → 2016-01-20: −22.5% |
| 4 | 2014-12-03 → 12-16: −16.2% | 2014-11-18 → 12-16: −21.1% |
| 5 | 2016-09-18 → 10-02: −11.8% | 2014-09-10 → 10-16: −14.4% |

- **March 2020 is not unique.** It is TASI's worst 21-session window since 2013, but only
  narrowly ahead of August 2015, and four of the five worst 10- and 21-session windows fall in the
  2014–16 oil-price decline.
- **The 2014–16 oil-price decline:** TASI fell 51.4% from 2014-09-09 to 2016-10-03 (512
  sessions); Brent fell 50.5% over the same dates (its own peak-to-trough, June 2014 to January
  2016, was −75.8%). This is a slow, two-year bear market, not a crash.
- **Replayed on today's portfolio** (hypothetical): with its latest walk-forward beta to TASI
  (0.98), a repeat of the 2014–16 fall would cost the equal-weight portfolio about 51% in price
  terms. This assumes the beta stays constant through a two-year decline and that the 24 stocks
  of 2026 behave like the 2014 market; it is a scenario, not a forecast.

### Oil sensitivity (Brent)

Weekly returns, Tadawul Thursday-to-Thursday paired with Brent Wednesday-to-Wednesday
(Brent settles after Tadawul closes), 343 weeks. Brent is Yahoo's continuous front-month future
`BZ=F`. Full table: `results/phase5/oil_betas.csv`.

- **Oil explains little of the week-to-week risk.** EW portfolio oil beta 0.11 (95% CI 0.07–0.14),
  R² 9%: a 10% Brent drop goes with about a 1.1% portfolio drop on average.
- **Oil exposure is broad, not just energy.** The highest betas are petrochemicals (Yansab,
  Sipchem, Saudi Kayan ≈ 0.19) but Riyad Bank (0.18) and ANB (0.16) are as high; Aramco itself
  is only 0.13. Telecoms, consumer, and Bahri are near zero.
- **The market's oil link has weakened.** TASI's weekly oil beta was 0.17 (SE 0.03) from July 2013
  to December 2019, against 0.11 (SE 0.02) in the sample period, the same as the equal-weight
  portfolio's. Oil explains about 9–10% of weekly TASI moves in both periods.

**Scenario** (Brent weekly moves that actually occurred in the sample; full-sample beta):

| Brent weekly shock | Predicted EW move (95% CI) |
|---|---|
| −30.5% (worst week, March 2020) | −3.3% (−2.2% to −4.4%) |
| −16.0% (1st percentile week) | −1.7% (−1.2% to −2.3%) |
| −9.7% (5th percentile week) | −1.0% (−0.7% to −1.4%) |

**The scenario number is not reliable.** The two worst Brent weeks were almost identical (−30.0%
and −30.5%, March 2020), but the EW portfolio fell 12.2% in the first and only 1.7% in the second.
A linear oil beta cannot capture that. Out of sample (betas estimated only on earlier weeks, 239
weeks from January 2022), predicted and actual weekly returns correlate at 0.27; in the six worst Brent
weeks the portfolio fell in three and rose in three. In April 2025 the model predicted −1.6% and
the portfolio fell 6.2%: that sell-off was a global equity shock, not an oil shock.

## Phase 6 results: minimum-variance allocation

**Setup.** Same 66 monthly rebalance dates as Phase 2. At each date, a long-only, fully invested
minimum-variance portfolio is built from the GARCH-CCC covariance (top-ranked in Phase 2) and,
as a control, from the 250-day sample covariance, using only earlier returns. Weights drift with
prices between rebalances; trading costs are 15 bps per unit traded (roughly Tadawul's
commission; spreads and market impact are ignored), with 0 and 30 bps as sensitivity.
Differences against equal-weight carry 95% intervals from a 21-day moving-block bootstrap.
Full results: `results/phase6/performance.csv`.

| Strategy (15 bps) | Return p.a. | Volatility p.a. | Max drawdown | Monthly turnover | Effective no. of stocks |
|---|---|---|---|---|---|
| equal_weight | 7.5% | 13.5% | 20.3% | 5% | 24 |
| min_var_sample_250 | 6.8% | 11.3% | 18.8% | 20% | 5.1 |
| min_var_garch_ccc | 4.6% | 11.3% | 23.9% | 63% | 5.6 |

Returns and volatilities are annualised with the observations per calendar year in the test
period (about 239). Volatility vs equal-weight: −2.1 points for both, 95% CI about (−2.8, −1.4):
**significant**. Return vs equal-weight: −0.6 points for sample (CI −7.2 to +5.3) and −2.9 for
GARCH (CI −10.2 to +3.3): **not significant**.

![Min-variance vs equal-weight](results/phase6/cumulative.png)

**What this says**

- **Minimum variance does what it promises:** about 2.1 points lower volatility than
  equal-weight, a reduction the bootstrap says is real.
- **The better covariance forecast does not make a better portfolio.** GARCH-CCC gives exactly
  the same volatility reduction as the plain sample covariance, but trades three times as much
  (63% vs 20% of the portfolio a month) because its volatility forecasts move every month. After
  costs it returns 2.3 points a year less than the sample version and has the deepest drawdown
  of the three (23.9%, April–December 2022). Phase 2's small, insignificant forecasting edge does
  not survive contact with an optimiser and costs.
- **The portfolios are concentrated.** Half of the 24 stocks get zero weight; on average the
  largest position is about a third of the portfolio (Saudi Aramco, about 26–32% on average),
  followed by Jarir, Bahri, and stc. Effective diversification is about 5 stocks. A real mandate
  would cap weights; this test does not, and that is a choice that favours lower volatility.
- **Returns cannot be compared with any confidence.** Six years of monthly rebalancing is far too
  short to say whether minimum variance costs return here.

## Known Limitations

Kept up to date as the project goes.

1. **Survivorship bias.** The universe is hand-picked today from stocks that survived and stayed
   liquid through the whole sample. Delisted, merged, or collapsed names are excluded, which
   likely understates realised risk and flatters performance: the equal-weight portfolio's
   1.8-point annual lead over TASI should be read in that light.
2. **Short history.** About 6.8 years and 1,646 days for the stocks. Backtests of 99% risk
   measures have few expected exceedances and wide uncertainty. TASI's history from 2013 shows
   that the sample misses a full bear market (2014–16) and that 2015–16 shocks were as large as
   March 2020; risk models fitted on the sample have never seen a two-year decline.
3. **Data vendor.** Yahoo Finance data for Tadawul is free and unofficial. Data before mid-2013
   is unusable (fake prices, wrong trading week). Checked against TASI's official calendar,
   Yahoo lacks 65 of 1,711 sessions in the sample (3.8%; 20 in 2023). Returns after a missing
   session cover two to four sessions, which slightly inflates measured tail risk on those days.
4. **Volume data is unreliable.** Yahoo's volume for some stocks drops to a few hundred shares for
   weeks at a time (e.g. Ma'aden May–June 2023), so no cleaning rule or liquidity measure here
   relies on volume, other than treating zero volume as a non-trading filler row.
5. **Adjustment accuracy.** Total returns rely on Yahoo's dividend and split adjustments. Spot
   checks match exactly, but a wrong adjustment that stays within the daily limit would not be
   caught.
6. **The out-of-sample period starts after the March 2020 crash.** Starting at Aramco's listing
   leaves only about 60 days before March 2020, so every rolling test (from December 2020 on) uses
   the crash only as estimation data. The worst event in the sample is never forecast out of sample.
7. **Few independent observations.** Monthly evaluation gives 66 non-overlapping months; the
   Phase 2 differences between methods are within statistical noise. Long-only random portfolios
   add little independent evidence because they are highly correlated with equal-weight.
8. **Phase 2 design choices** (not tuned to results): 250-day window, 21-day horizon, GARCH(1,1)
   with normal quasi-likelihood, constant correlation instead of DCC, identity shrinkage target
   instead of constant correlation.
9. **Phase 3 design choices** (not tuned to results): 250-day window for historical, normal, and
   t models; FHS uses all standardised residuals since December 2019, including the 2020 crash,
   which likely explains why it is conservative; GARCH parameters refitted every 21 days.
10. **The ES test is weak.** It is a one-sided t-test on 8–26 exceedance days per model and only
    detects ES that is too small; an ES that is too large (as with FHS at 95%) shows only in the ratio.
11. **Real-time regime labels lag.** The label uses only earlier TASI sessions, so the first day
    of a shock arriving from calm conditions is labelled calm. The turbulent regime measures how
    models behave once turbulence is visible, not at its onset.
12. **The turbulent sample is small.** 217 TASI-turbulent test days and 8 turbulent months; regime
    splits of the 99% results rest on single-digit exceedance counts.
13. **Stress episodes are chosen with hindsight** (worst windows in the data). That is intended for
    a replay, but they are not a forecast of the next crisis. The 2014–16 decline is replayed on
    TASI only, and on today's portfolio only through a linear beta; the stocks themselves have no
    usable data then. The 2019 Abqaiq attack falls before the stock sample and is not studied.
14. **Episode labels are annotations.** The "context" column summarises widely reported events and
    is not tested against the data; two episodes are left unexplained rather than guessed.
15. **Oil betas are unstable and linear.** Brent explains about 9% of weekly portfolio variance, the
    same oil shock produced very different equity moves, and front-month futures have roll jumps.
16. **Allocation test simplifications.** No weight caps (portfolios concentrate in about 5 stocks),
    costs are commission only, no taxes or Zakat, no cash or risk-free rate, and only 66 rebalances.
17. **Price index vs total return.** TASI excludes dividends, so all benchmark comparisons use
    price returns. Saudi dividend yields are high (about 3.4 points a year for the equal-weight
    portfolio here), so comparing a total-return portfolio with TASI would overstate it.
18. **Annualisation.** Daily statistics are annualised with the number of observations per
    calendar year (about 240), not the usual 250, because returns that span sessions Yahoo lacks
    still cover real time (limitation 3). An earlier version used 250 and overstated Phase 1 and 6
    annualised figures by about 4% (returns) and 2% (volatility). The axis of the Phase 2 chart
    of forecast vs realised volatility still uses 250; it is display only and no reported number
    depends on it.
19. **One TASI source.** The TASI file is a single static export from the Saudi Exchange. It passes
    the schema and range checks above, but was not cross-checked against a second source.
