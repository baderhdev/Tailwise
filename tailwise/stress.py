"""Phase 5: replay real stress episodes, TASI's longer history (incl. 2014-16), and Brent sensitivity.

Episodes are the worst non-overlapping 10- and 21-day windows of the equal-weight portfolio (and of
TASI since 2013): a historical replay, chosen with hindsight on purpose. Anything used as a forecast
(pre-episode VaR, pre-episode beta to TASI, walk-forward oil betas) uses only data before the date
it applies to. Comparisons with TASI use price returns, because TASI is a price index.
"""
import numpy as np
import pandas as pd
from scipy import stats

from .benchmark import rolling_beta
from .covariance import test_portfolios
from .data import PROC, ROOT, START, UNIVERSE, download, load_price_returns, load_returns, load_tasi_returns

OUT = ROOT / "results" / "phase5"
HORIZONS = (10, 21)
N_EPISODES = 5
MIN_WEEKS = 104  # two years of weekly data before the first walk-forward oil beta
OIL_DECLINE = ("2014-01-01", "2016-12-31")  # window searched for TASI's 2014-16 peak-to-trough


def worst_windows(r, n, k=N_EPISODES):
    """Start/end positions of the k worst non-overlapping n-day compounded returns."""
    cum = pd.Series(np.log1p(r)).rolling(n).sum().shift(-(n - 1)).dropna()  # indexed by window start
    chosen = []
    for start in cum.sort_values().index:
        if all(abs(start - s) >= n for s, _ in chosen):
            chosen.append((start, start + n - 1))
        if len(chosen) == k:
            break
    return chosen


def episodes(rets, weights):
    ew = rets.mean(axis=1).values
    fc = pd.read_csv(ROOT / "results" / "phase3" / "forecasts.csv", parse_dates=["date"])
    pv = fc[fc.alpha == 0.01].pivot_table(index=["date", "portfolio"], columns="method", values="var")
    tasi = load_tasi_returns().loc[rets.index]
    ew_price = load_price_returns().mean(axis=1)
    beta = rolling_beta(ew_price, tasi)  # known before each day
    rows = []
    for n in HORIZONS:
        for s, e in worst_windows(ew, n):
            first, last = rets.index[s], rets.index[e]
            window = rets.iloc[s:e + 1]
            stock = (1 + window).prod() - 1
            row = dict(days=n, start=first.date(), end=last.date(),
                       worst_stocks=", ".join(f"{UNIVERSE[t]} {v:.0%}" for t, v in stock.nsmallest(3).items()),
                       loss_tasi=-((1 + tasi.iloc[s:e + 1]).prod() - 1),
                       loss_ew_price=-((1 + ew_price.iloc[s:e + 1]).prod() - 1),
                       beta_before=beta.iloc[s])
            row["predicted_ew_price_loss"] = row["beta_before"] * row["loss_tasi"]  # NaN before 250 days of history
            for p, w in weights.items():
                loss = -((1 + window.values @ w).prod() - 1)
                row[f"loss_{p}"] = loss
                if p == "equal_weight" and (first, p) in pv.index:
                    # 1-day 99% VaR forecast made before the episode, scaled by sqrt(n) (assumes iid days)
                    for m, v in pv.loc[(first, p)].items():
                        row[f"loss_over_var99_{m}"] = loss / (v * np.sqrt(n))
            rows.append(row)
    return pd.DataFrame(rows)


def max_drawdown_dates(close):
    """(peak date, trough date, drawdown) of the deepest peak-to-trough fall in `close`."""
    trough = (close / close.cummax()).idxmin()
    peak = close[:trough].idxmax()
    return peak, trough, close[trough] / close[peak] - 1


def tasi_history(tasi_full, brent, ew_price, ew_total):
    """TASI's own worst windows since 2013, and the 2014-16 oil-price decline: TASI, Brent and the portfolio."""
    r = tasi_full["ret"].dropna()
    eps = []
    for n in HORIZONS:
        for s, e in worst_windows(r.values, n):
            eps.append(dict(days=n, start=r.index[s].date(), end=r.index[e].date(),
                            loss_tasi=-((1 + r.iloc[s:e + 1]).prod() - 1)))
    close = tasi_full["close"].loc[OIL_DECLINE[0]:OIL_DECLINE[1]]
    peak, trough, dd = max_drawdown_dates(close)
    b_peak, b_trough, b_dd = max_drawdown_dates(brent.loc[OIL_DECLINE[0]:OIL_DECLINE[1]])
    decline = pd.DataFrame([dict(
        tasi_peak=peak.date(), tasi_trough=trough.date(), tasi_drawdown=dd, sessions=len(close.loc[peak:trough]) - 1,
        brent_over_tasi_dates=brent.loc[:trough].iloc[-1] / brent.loc[:peak].iloc[-1] - 1,
        brent_peak=b_peak.date(), brent_trough=b_trough.date(), brent_drawdown=b_dd,
        # the portfolio over the same dates: returns after the peak close, up to the trough close
        ew_price_change=(1 + ew_price.loc[peak:trough].iloc[1:]).prod() - 1,
        ew_total_change=(1 + ew_total.loc[peak:trough].iloc[1:]).prod() - 1)])
    return pd.DataFrame(eps), decline


def weekly(prices, brent):
    """Tadawul Thursday-to-Thursday returns paired with Brent Wednesday-to-Wednesday returns.

    Brent settles around 21:30 Riyadh time, after Tadawul's 15:00 close, so Brent's Wednesday close
    is the last oil price a Thursday Tadawul close could have seen.
    """
    tad = prices.resample("W-THU").last().pct_change()
    oil = brent.resample("W-WED").last().pct_change()
    oil.index = oil.index + pd.Timedelta(days=1)
    wk = pd.concat([tad, oil.rename("brent")], axis=1, join="inner").dropna()
    return wk[wk.index <= prices.index[-1]]  # drop a week that has not finished yet


def beta(y, x):
    fit = stats.linregress(x, y)
    return fit.slope, fit.stderr, fit.rvalue ** 2


def walk_forward_oil(port, oil, min_weeks=MIN_WEEKS):
    """Predicted return for week t = beta (from weeks before t) x Brent return in week t."""
    pred = pd.Series(np.nan, index=port.index)
    for t in range(min_weeks, len(port)):
        b, _, _ = beta(port.iloc[:t].values, oil.iloc[:t].values)
        pred.iloc[t] = b * oil.iloc[t]
    return pred


def oil(prices, weights):
    brent = download(["BZ=F"])["BZ=F"]["Close"]
    wk = weekly(prices, brent)
    rets = wk.drop(columns="brent")
    ports = pd.DataFrame({p: rets.values @ w for p, w in weights.items()}, index=wk.index)
    betas = pd.DataFrame([dict(series=c, name=UNIVERSE.get(c, c), **dict(zip(["beta", "se", "r2"], beta(s.values, wk.brent.values))))
                          for c, s in pd.concat([rets, ports], axis=1).items()])
    # TASI's oil beta in two halves of the sample: before and after December 2019
    tasi_px = pd.read_csv(PROC / "tasi_full.csv", index_col=0, parse_dates=True)[["close"]]
    for label, a, b in [("TASI 2014-01 to 2019-12", START, "2019-12-10"), ("TASI 2019-12 to 2026-10", "2019-12-11", None)]:
        wt = weekly(tasi_px.loc[a:b], brent)
        betas.loc[len(betas)] = dict(series=label, name=f"{label} ({len(wt)} weeks)",
                                     **dict(zip(["beta", "se", "r2"], beta(wt.close.values, wt.brent.values))))
    # scenarios: Brent weekly moves that actually happened in the sample
    shocks = {"worst week": wk.brent.min(), "1st pct week": wk.brent.quantile(0.01), "5th pct week": wk.brent.quantile(0.05)}
    b, se, r2 = beta(ports.equal_weight.values, wk.brent.values)
    scen = pd.DataFrame([dict(scenario=k, brent=v, ew_predicted=b * v, ew_ci_low=(b - 1.96 * se) * v,
                              ew_ci_high=(b + 1.96 * se) * v) for k, v in shocks.items()])
    worst_week = wk.brent.idxmin()
    scen.loc[0, "ew_actual_that_week"] = ports.equal_weight[worst_week]
    # out-of-sample check on the worst Brent weeks after the first two years
    pred = walk_forward_oil(ports.equal_weight, wk.brent)
    oos = pd.DataFrame({"brent": wk.brent, "ew_predicted": pred, "ew_actual": ports.equal_weight}).dropna()
    return wk, betas, scen, oos, brent


def run():
    OUT.mkdir(parents=True, exist_ok=True)
    rets = load_returns()
    weights = test_portfolios(rets.shape[1])
    ep = episodes(rets, weights)
    ep.to_csv(OUT / "episodes.csv", index=False, float_format="%.4f")
    prices = pd.read_csv(PROC / "prices.csv", index_col=0, parse_dates=True)
    wk, betas, scen, oos, brent = oil(prices, weights)
    tasi_eps, decline = tasi_history(pd.read_csv(PROC / "tasi_full.csv", index_col=0, parse_dates=True),
                                     brent, load_price_returns().mean(axis=1), rets.mean(axis=1))
    tasi_eps.to_csv(OUT / "tasi_episodes.csv", index=False, float_format="%.4f")
    decline.to_csv(OUT / "oil_decline_2014_16.csv", index=False, float_format="%.4f")
    betas.to_csv(OUT / "oil_betas.csv", index=False, float_format="%.4f")
    scen.to_csv(OUT / "oil_scenarios.csv", index=False, float_format="%.4f")
    oos.to_csv(OUT / "oil_walk_forward.csv", float_format="%.4f")
    pd.set_option("display.width", 250, "display.max_colwidth", 70)
    print(ep.round(3).to_string(index=False))
    print(tasi_eps.round(3).to_string(index=False))
    print(decline.round(3).T.to_string())
    print(f"weeks: {len(wk)}  {wk.index[0].date()} -> {wk.index[-1].date()}")
    print(betas.round(3).to_string(index=False))
    print(scen.round(4).to_string(index=False))
    print("walk-forward: corr(pred, actual) =", round(oos.ew_predicted.corr(oos.ew_actual), 3), "weeks", len(oos))
    print(oos.nsmallest(6, "brent").round(4).to_string())
    return ep, betas, scen, oos, tasi_eps, decline
