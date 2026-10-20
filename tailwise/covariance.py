"""Phase 2: covariance forecasts, evaluated walk-forward against realised portfolio variance.

At each origin t the estimators see only returns before t and forecast the covariance of the
next H daily returns. The target is the realised variance of a fixed portfolio over those H days.
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from arch import arch_model
from scipy import stats

from .data import ROOT, load_returns
from .eda import DAYS  # also applies the shared plot style

OUT = ROOT / "results" / "phase2"
WINDOW = 250  # rolling estimation window, about one year
H = 21  # forecast horizon and step, about one month; origins do not overlap
SEED = 2026
N_RANDOM = 5
COLORS = {"sample_250": "#2a78d6", "sample_expanding": "#eb6834", "ledoit_wolf_250": "#1baf7a", "garch_ccc": "#6250d6"}


def sample_cov(x):
    return np.cov(x, rowvar=False)


def ledoit_wolf(x):
    """Ledoit-Wolf (2004) shrinkage of the sample covariance toward a scaled identity."""
    x = x - x.mean(0)
    t, n = x.shape
    s = x.T @ x / t
    mu = np.trace(s) / n
    d2 = ((s - mu * np.eye(n)) ** 2).sum()
    b2 = (((x ** 2).T @ (x ** 2)).sum() / t - (s ** 2).sum()) / t
    delta = min(b2, d2) / d2
    return delta * mu * np.eye(n) + (1 - delta) * s


def garch_ccc(hist, h, window):
    """Constant-correlation GARCH: per-stock GARCH(1,1) h-day variance, fitted on all history to date,
    combined with the correlation of standardised residuals over the last `window` days."""
    var_h, z = [], []
    for j in range(hist.shape[1]):
        res = arch_model(100 * hist[:, j], mean="Constant", vol="GARCH", p=1, q=1, rescale=False).fit(disp="off")
        var_h.append(res.forecast(horizon=h, reindex=False).variance.values[-1].sum() / 1e4)
        z.append(res.std_resid[-window:])
    sd = np.sqrt(var_h)
    return np.corrcoef(np.array(z)) * np.outer(sd, sd)


METHODS = {
    "sample_250": lambda hist, h, w: h * sample_cov(hist[-w:]),
    "sample_expanding": lambda hist, h, w: h * sample_cov(hist),  # same data as GARCH: separates "more data" from "GARCH"
    "ledoit_wolf_250": lambda hist, h, w: h * ledoit_wolf(hist[-w:]),
    "garch_ccc": garch_ccc,
}


def test_portfolios(n_assets, seed=SEED, n_random=N_RANDOM):
    rng = np.random.default_rng(seed)
    w = {"equal_weight": np.full(n_assets, 1 / n_assets)}
    for k in range(n_random):
        w[f"random_{k + 1}"] = rng.dirichlet(np.ones(n_assets))  # long-only, uniform on the simplex
    return w


def walk_forward(rets, weights, h=H, window=WINDOW, methods=METHODS):
    """One row per (origin, portfolio, method): forecast and realised h-day variance."""
    x = rets.values
    rows = []
    for i in range(window, len(x) - h + 1, h):
        hist = x[:i]  # strictly before the origin
        covs = {m: f(hist, h, window) for m, f in methods.items()}
        fut = x[i:i + h]
        for p, w in weights.items():
            rv = ((fut @ w) ** 2).sum()
            for m, c in covs.items():
                rows.append((rets.index[i], p, m, w @ c @ w, rv))
    return pd.DataFrame(rows, columns=["origin", "portfolio", "method", "forecast", "realised"])


def qlike(rv, f):
    """Patton (2011) QLIKE loss, robust to a noisy variance proxy; 0 when forecast equals realised."""
    return rv / f - np.log(rv / f) - 1


def newey_west_se(d, lags=2):
    d = np.asarray(d) - np.mean(d)
    n = len(d)
    v = d @ d / n
    for k in range(1, lags + 1):
        v += 2 * (1 - k / (lags + 1)) * (d[k:] @ d[:-k]) / n
    return np.sqrt(v / n)


def evaluate(wf, baseline="sample_250"):
    wf = wf.assign(qlike=qlike(wf.realised, wf.forecast), log_ratio=np.log(wf.realised / wf.forecast))
    rows = []
    for (p, m), g in wf.groupby(["portfolio", "method"]):
        b = wf[(wf.portfolio == p) & (wf.method == baseline)].set_index("origin")["qlike"]
        d = g.set_index("origin")["qlike"] - b  # negative: better than baseline
        se = newey_west_se(d) if m != baseline else np.nan
        rows.append(dict(
            portfolio=p, method=m, n=len(g), qlike=g.qlike.mean(),
            mean_rv_over_mean_f=g.realised.mean() / g.forecast.mean(),  # <1: risk over-forecast on average
            bias_log_rv_over_f=g.log_ratio.mean(),  # negative even for a correct forecast (Jensen), so read with the ratio
            pct_rv_above_f=(g.realised > g.forecast).mean() * 100,
            qlike_diff_vs_base=d.mean(), diff_ci_low=d.mean() - 1.96 * se, diff_ci_high=d.mean() + 1.96 * se,
            dm_p=2 * stats.norm.sf(abs(d.mean() / se)) if m != baseline else np.nan,
        ))
    return pd.DataFrame(rows)


def plot_ew(wf):
    ew = wf[wf.portfolio == "equal_weight"]
    ann = lambda v: np.sqrt(v * DAYS / H)
    fig, ax = plt.subplots(figsize=(10, 4.5))
    real = ew[ew.method == "sample_250"].set_index("origin")["realised"]
    ax.bar(real.index, ann(real), width=20, color="#c3c2b7", label="Realised (next 21 days)")
    for m, c in COLORS.items():
        s = ew[ew.method == m].set_index("origin")["forecast"]
        ax.step(s.index, ann(s), where="post", color=c, label=m)
    ax.set_ylabel("Annualised volatility")
    ax.set_title("Equal-weight portfolio: forecast vs realised volatility, monthly walk-forward", loc="left")
    ax.legend(frameon=False, ncol=5, loc="upper right", fontsize=8)
    fig.tight_layout()
    fig.savefig(OUT / "ew_forecast_vs_realised.png")
    plt.close(fig)


def run():
    OUT.mkdir(parents=True, exist_ok=True)
    rets = load_returns()
    weights = test_portfolios(rets.shape[1])
    pd.DataFrame(weights, index=rets.columns).to_csv(OUT / "test_portfolios.csv", float_format="%.4f")
    wf = walk_forward(rets, weights)
    wf.to_csv(OUT / "walk_forward.csv", index=False)
    res = evaluate(wf)
    res.to_csv(OUT / "evaluation.csv", index=False, float_format="%.5f")
    plot_ew(wf)
    pd.set_option("display.width", 220)
    print(f"origins: {wf.origin.nunique()}, {wf.origin.min().date()} -> {wf.origin.max().date()}")
    print(res.round(4).to_string(index=False))
    return res
