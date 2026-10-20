"""Phase 6: long-only minimum-variance vs equal-weight, monthly walk-forward with transaction costs.

At each rebalance date the covariance uses only returns before that date. Weights drift with
prices between rebalances; turnover is measured against the drifted weights.
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.optimize import minimize

from .covariance import H, METHODS, SEED, WINDOW
from .data import ROOT, load_returns
from .eda import BLUE, ORANGE, per_year

OUT = ROOT / "results" / "phase6"
COST_BPS = 15  # one-way, per unit traded: roughly Tadawul commission; ignores spread and impact
COST_SENSITIVITY = (0, 15, 30)
STRATEGIES = {"min_var_garch_ccc": "garch_ccc", "min_var_sample_250": "sample_250"}


def min_variance(cov):
    n = len(cov)
    res = minimize(lambda w: w @ cov @ w, np.full(n, 1 / n), jac=lambda w: 2 * cov @ w, method="SLSQP",
                   bounds=[(0, 1)] * n, constraints=[{"type": "eq", "fun": lambda w: w.sum() - 1}],
                   options={"ftol": 1e-12, "maxiter": 500})
    if not res.success:
        raise RuntimeError(f"min-variance optimisation failed: {res.message}")
    w = np.clip(res.x, 0, None)
    return w / w.sum()


def target_weights(x, strategies=STRATEGIES, window=WINDOW, h=H):
    """{strategy: [(origin index, weights)]}, each from x[:origin] only."""
    out = {"equal_weight": [], **{s: [] for s in strategies}}
    for i in range(window, len(x) - h + 1, h):
        out["equal_weight"].append((i, np.full(x.shape[1], 1 / x.shape[1])))
        for s, m in strategies.items():
            out[s].append((i, min_variance(METHODS[m](x[:i], h, window))))
    return out


def simulate(x, targets, cost_bps):
    """Daily net returns and per-rebalance turnover for one strategy, buy-and-hold between rebalances."""
    first = targets[0][0]
    ret = np.zeros(len(x) - first)
    turnover = []
    held = np.zeros(x.shape[1])  # start in cash, so the first rebalance pays to buy in
    starts = [i for i, _ in targets] + [len(x)]
    for (i, w), end in zip(targets, starts[1:]):
        trade = np.abs(w - held).sum()
        turnover.append(trade)
        cur = w.copy()
        for t in range(i, end):
            gross = cur @ x[t]
            ret[t - first] = gross - (trade * cost_bps / 1e4 if t == i else 0)
            cur = cur * (1 + x[t]) / (1 + gross)  # drift
        held = cur
    return ret, np.array(turnover)


def max_drawdown(r):
    wealth = np.cumprod(1 + r)
    return (1 - wealth / np.maximum.accumulate(wealth)).max()


def block_bootstrap_diff(a, b, stat, block=21, reps=2000, seed=SEED):
    """95% CI for stat(a) - stat(b) from a moving-block bootstrap of the paired daily returns."""
    rng = np.random.default_rng(seed)
    n = len(a)
    k = int(np.ceil(n / block))
    out = np.empty(reps)
    for j in range(reps):
        idx = (rng.integers(0, n - block + 1, k)[:, None] + np.arange(block)).ravel()[:n]
        out[j] = stat(a[idx]) - stat(b[idx])
    return np.percentile(out, [2.5, 97.5])


def ann_vol(r, ppy):
    return r.std() * np.sqrt(ppy)


def ann_ret(r, ppy):
    return np.prod(1 + r) ** (ppy / len(r)) - 1


def run():
    OUT.mkdir(parents=True, exist_ok=True)
    rets = load_returns()
    x = rets.values
    targets = target_weights(x)
    first = targets["equal_weight"][0][0]
    dates = rets.index[first:]
    ppy = per_year(dates, rets.index[first - 1])
    vol, ret = (lambda r: ann_vol(r, ppy)), (lambda r: ann_ret(r, ppy))
    wts = pd.DataFrame({(s, rets.index[i].date()): w for s, tw in targets.items() for i, w in tw}, index=rets.columns).T
    wts.to_csv(OUT / "weights.csv", float_format="%.4f")

    rows, daily = [], {}
    for c in COST_SENSITIVITY:
        sims = {s: simulate(x, tw, c) for s, tw in targets.items()}
        ew = sims["equal_weight"][0]
        for s, (r, to) in sims.items():
            w = np.array([w for _, w in targets[s]])
            row = dict(strategy=s, cost_bps=c, ann_return=ret(r), ann_vol=vol(r), max_drawdown=max_drawdown(r),
                       avg_turnover=to[1:].mean(), avg_max_weight=w.max(axis=1).mean(),
                       avg_effective_n=(1 / (w ** 2).sum(axis=1)).mean())
            if s != "equal_weight":
                row["vol_diff_vs_ew"] = row["ann_vol"] - vol(ew)
                row["vol_diff_ci_low"], row["vol_diff_ci_high"] = block_bootstrap_diff(r, ew, vol)
                row["ret_diff_vs_ew"] = row["ann_return"] - ret(ew)
                row["ret_diff_ci_low"], row["ret_diff_ci_high"] = block_bootstrap_diff(r, ew, ret)
            rows.append(row)
            if c == COST_BPS:
                daily[s] = r
    res = pd.DataFrame(rows)
    res.to_csv(OUT / "performance.csv", index=False, float_format="%.5f")
    pd.DataFrame(daily, index=dates).to_csv(OUT / "daily_net_returns.csv", float_format="%.6f")

    fig, ax = plt.subplots(figsize=(10, 4.5))
    for (s, r), c in zip(daily.items(), ["#898781", BLUE, ORANGE]):
        ax.plot(dates, np.cumprod(1 + r), color=c, label=s)
    ax.set_ylabel(f"Growth of 1, net of {COST_BPS} bps costs")
    ax.set_title("Monthly walk-forward: minimum-variance vs equal-weight", loc="left")
    ax.legend(frameon=False)
    fig.tight_layout()
    fig.savefig(OUT / "cumulative.png")
    plt.close(fig)

    pd.set_option("display.width", 250)
    print(res.round(4).to_string(index=False))
    return res
