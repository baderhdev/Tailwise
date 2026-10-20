"""Phase 3: one-day VaR and Expected Shortfall, forecast daily walk-forward and backtested.

VaR and ES are reported as positive loss numbers. The forecast for day t uses returns before t only.
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from arch import arch_model
from scipy import stats

from .covariance import test_portfolios
from .data import ROOT, load_returns
from .eda import BLUE, ORANGE

OUT = ROOT / "results" / "phase3"
ALPHAS = (0.05, 0.01)  # tail probabilities: 95% and 99% VaR
WINDOW = 250
REFIT = 21  # GARCH parameters are re-estimated every 21 days; volatility updates daily


def historical(x, a):
    q = np.quantile(x, a)
    return -q, -x[x <= q].mean()


def normal(x, a):
    m, s, z = x.mean(), x.std(ddof=1), stats.norm.ppf(a)
    return -(m + s * z), -(m - s * stats.norm.pdf(z) / a)


def student_t_fit(x):
    """MLE from scipy's default start and a moment-based start; keep the higher likelihood.
    scipy's default start alone sometimes stops at a worse local optimum (nu < 2)."""
    fits = [stats.t.fit(x), stats.t.fit(x, 5, loc=x.mean(), scale=x.std() * np.sqrt(3 / 5))]
    nu, loc, scale = max(fits, key=lambda p: stats.t.logpdf(x, *p).sum())
    if nu <= 1:
        raise ValueError(f"t fit gave nu={nu:.2f}: ES undefined")
    return nu, loc, scale


def student_t(params, a):
    nu, loc, scale = params
    q = stats.t.ppf(a, nu)
    es_std = -stats.t.pdf(q, nu) / a * (nu + q ** 2) / (nu - 1)  # ES of a standard t, as a return
    return -(loc + scale * q), -(loc + scale * es_std)


def _garch(r):
    return arch_model(100 * r, mean="Constant", vol="GARCH", p=1, q=1, rescale=False)


def forecasts(r, window=WINDOW, refit=REFIT, alphas=ALPHAS):
    """Rows (t, method, alpha, var, es) for every t >= window, each using r[:t] only."""
    rows = []
    params = None
    for t in range(window, len(r)):
        hist, win = r[:t], r[t - window:t]
        if (t - window) % refit == 0:
            params = _garch(hist).fit(disp="off").params
        g = _garch(hist).fix(params)
        sig = np.sqrt(g.forecast(horizon=1, reindex=False).variance.values[-1, 0]) / 100
        z = g.std_resid[~np.isnan(g.std_resid)]  # all standardised residuals to date
        mu = params["mu"] / 100
        tp = student_t_fit(win)
        for a in alphas:
            qz = np.quantile(z, a)
            rows += [
                (t, "historical", a, *historical(win, a)),
                (t, "normal", a, *normal(win, a)),
                (t, "student_t", a, *student_t(tp, a)),
                (t, "fhs_garch", a, -(mu + sig * qz), -(mu + sig * z[z <= qz].mean())),
            ]
    return pd.DataFrame(rows, columns=["t", "method", "alpha", "var", "es"])


def _xlogy(x, y):
    return x * np.log(y) if x > 0 else 0.0


def kupiec(hits, p):
    """Unconditional coverage LR test (Kupiec 1995): is the exceedance rate equal to p?"""
    n, x = len(hits), int(np.sum(hits))
    phat = x / n
    lr = -2 * (_xlogy(n - x, 1 - p) + _xlogy(x, p) - _xlogy(n - x, 1 - phat) - _xlogy(x, phat))
    return lr, stats.chi2.sf(lr, 1)


def christoffersen(hits):
    """Independence LR test (Christoffersen 1998): does an exceedance make the next one more likely?"""
    h = np.asarray(hits, int)
    prev, cur = h[:-1], h[1:]
    n00, n01 = np.sum((prev == 0) & (cur == 0)), np.sum((prev == 0) & (cur == 1))
    n10, n11 = np.sum((prev == 1) & (cur == 0)), np.sum((prev == 1) & (cur == 1))
    p01 = n01 / max(n00 + n01, 1)
    p11 = n11 / max(n10 + n11, 1)
    p = (n01 + n11) / (n00 + n01 + n10 + n11)
    l0 = _xlogy(n00 + n10, 1 - p) + _xlogy(n01 + n11, p)
    l1 = _xlogy(n00, 1 - p01) + _xlogy(n01, p01) + _xlogy(n10, 1 - p11) + _xlogy(n11, p11)
    lr = -2 * (l0 - l1)
    return lr, stats.chi2.sf(lr, 1)


def backtest(df):
    """Coverage and ES statistics per (portfolio, method, alpha)."""
    rows = []
    for (p, m, a), g in df.groupby(["portfolio", "method", "alpha"]):
        hits = (g.ret < -g["var"]).values
        lr_uc, p_uc = kupiec(hits, a)
        lr_ind, p_ind = christoffersen(hits)
        exc = g[hits]
        loss, es = -exc.ret, exc.es
        # ES check: on exceedance days, is the realised loss larger than the forecast ES on average?
        d = loss - es
        es_p = stats.ttest_1samp(d, 0, alternative="greater").pvalue if len(d) > 2 else np.nan
        rows.append(dict(
            portfolio=p, method=m, level=f"{1 - a:.0%}", n=len(g), expected=a * len(g), exceedances=int(hits.sum()),
            rate_pct=hits.mean() * 100, kupiec_p=p_uc, christoffersen_ind_p=p_ind,
            cond_coverage_p=stats.chi2.sf(lr_uc + lr_ind, 2),
            mean_loss_on_exceed=loss.mean(), mean_es_on_exceed=es.mean(), es_ratio=loss.mean() / es.mean(), es_ttest_p=es_p,
        ))
    return pd.DataFrame(rows)


def plot_ew(df, dates):
    ew = df[(df.portfolio == "equal_weight") & (df.alpha == 0.01)]
    methods = ["historical", "normal", "student_t", "fhs_garch"]
    fig, axes = plt.subplots(2, 2, figsize=(11, 6.5), sharex=True, sharey=True)
    for ax, m in zip(axes.flat, methods):
        g = ew[ew.method == m]
        x = dates[g.t.values]
        hit = g.ret.values < -g["var"].values
        ax.bar(x, g.ret.values * 100, width=1.5, color="#c3c2b7")
        ax.plot(x, -g["var"].values * 100, color=BLUE, lw=1)
        ax.scatter(x[hit], g.ret.values[hit] * 100, s=12, color=ORANGE, zorder=3)
        ax.set_title(f"{m}: {hit.sum()} exceedances (expected {0.01 * len(g):.0f})", loc="left")
    for ax in axes[:, 0]:
        ax.set_ylabel("Daily return, %")
    fig.suptitle("Equal-weight portfolio: 99% VaR (blue) vs daily returns; exceedances in orange", x=0.01, ha="left")
    fig.tight_layout()
    fig.savefig(OUT / "ew_var99.png")
    plt.close(fig)


def run():
    OUT.mkdir(parents=True, exist_ok=True)
    rets = load_returns()
    frames = []
    for p, w in test_portfolios(rets.shape[1]).items():
        r = rets.values @ w
        f = forecasts(r)
        f["portfolio"], f["ret"] = p, r[f.t.values]
        frames.append(f)
    df = pd.concat(frames, ignore_index=True)
    df.insert(0, "date", rets.index[df.t.values])
    df.to_csv(OUT / "forecasts.csv", index=False, float_format="%.6f")
    bt = backtest(df)
    bt.to_csv(OUT / "backtest.csv", index=False, float_format="%.5f")
    plot_ew(df, rets.index)
    pd.set_option("display.width", 250)
    print(bt[bt.portfolio == "equal_weight"].round(3).to_string(index=False))
    return bt
