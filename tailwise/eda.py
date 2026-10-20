"""Phase 1 exploratory statistics: volatility, correlation, fat tails. Descriptive only, full sample."""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import LinearSegmentedColormap
from scipy import stats

from .data import ROOT, UNIVERSE, load_returns, load_tasi_returns

OUT = ROOT / "results" / "phase1"
DAYS = 250  # annualisation convention; Tadawul has ~245-250 sessions a year
BLUE, ORANGE, INK2, MUTED = "#2a78d6", "#eb6834", "#52514e", "#898781"
SEQ = LinearSegmentedColormap.from_list("blues", ["#f0efec", "#86b6ef", "#2a78d6", "#0d366b"])

plt.rcParams.update({
    "figure.facecolor": "#fcfcfb", "axes.facecolor": "#fcfcfb", "axes.edgecolor": "#c3c2b7",
    "axes.labelcolor": INK2, "xtick.color": MUTED, "ytick.color": MUTED, "text.color": "#0b0b0b",
    "axes.grid": True, "grid.color": "#e1e0d9", "grid.linewidth": 0.6, "axes.spines.top": False,
    "axes.spines.right": False, "lines.linewidth": 1.5, "font.size": 9, "figure.dpi": 130,
})


def summary(r):
    """Per-series annualised vol/mean, skew, excess kurtosis, tail frequency vs a normal."""
    z = (r - r.mean()) / r.std()
    return pd.DataFrame({
        "ann_vol": r.std() * np.sqrt(DAYS),
        "ann_mean": r.mean() * DAYS,
        "skew": r.skew(),
        "excess_kurt": r.kurt(),
        "min": r.min(),
        "max": r.max(),
        "pct_beyond_3sd": (z.abs() > 3).mean() * 100,  # normal: 0.27%
        "jarque_bera_p": [stats.jarque_bera(r[c].dropna()).pvalue for c in r],
        "n": r.count(),
    })


def run():
    OUT.mkdir(parents=True, exist_ok=True)
    rets = load_returns()
    ew = rets.mean(axis=1).rename("EW portfolio")
    tasi = load_tasi_returns()
    # align TASI to the return dates; an extra all-NaN row would change the tail-frequency denominators
    table = pd.concat([rets, ew] + ([tasi.loc[rets.index].rename("TASI")] if tasi is not None else []), axis=1)
    s = summary(table)
    s.insert(0, "name", [UNIVERSE.get(c, c) for c in s.index])
    s.to_csv(OUT / "summary_stats.csv", float_format="%.5f")

    corr = rets.corr()
    corr.to_csv(OUT / "correlation.csv", float_format="%.3f")
    off = corr.values[~np.eye(len(corr), dtype=bool)]

    # correlation heatmap, tickers ordered by sector as in UNIVERSE
    fig, ax = plt.subplots(figsize=(8, 7))
    im = ax.imshow(corr, cmap=SEQ, vmin=0, vmax=1)
    labels = [UNIVERSE[c] for c in corr.columns]
    ax.set_xticks(range(len(labels)), labels, rotation=90)
    ax.set_yticks(range(len(labels)), labels)
    ax.grid(False)
    fig.colorbar(im, ax=ax, shrink=0.8, label="Pearson correlation of daily returns")
    ax.set_title(f"Return correlations, full sample (mean off-diagonal {off.mean():.2f})", loc="left")
    fig.tight_layout()
    fig.savefig(OUT / "correlation_heatmap.png")
    plt.close(fig)

    # rolling risk: EW volatility and average pairwise correlation, two panels sharing time (no dual axis)
    roll_vol = ew.rolling(60).std() * np.sqrt(DAYS)
    n = rets.shape[1]
    roll_corr = rets.rolling(120).corr().groupby(level=0).apply(lambda m: (m.values.sum() - n) / (n * n - n))
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(9, 5.5), sharex=True)
    a1.plot(roll_vol, color=BLUE)
    a1.set_ylabel("Annualised vol (60-day)")
    a1.set_title("Equal-weight portfolio: rolling volatility and average pairwise correlation", loc="left")
    a2.plot(roll_corr, color=BLUE)
    a2.set_ylabel("Avg correlation (120-day)")
    fig.tight_layout()
    fig.savefig(OUT / "rolling_vol_corr.png")
    plt.close(fig)

    # fat tails of the EW portfolio: histogram vs fitted normal, and QQ plot
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(10, 4))
    a1.hist(ew, bins=80, density=True, color=BLUE, edgecolor="#fcfcfb", linewidth=0.5, label="Observed")
    x = np.linspace(ew.min(), ew.max(), 400)
    a1.plot(x, stats.norm.pdf(x, ew.mean(), ew.std()), color=ORANGE, label="Normal, same mean/sd")
    a1.set_yscale("log")
    a1.set_ylim(bottom=0.05)
    a1.set_xlabel("Daily return")
    a1.set_ylabel("Density (log scale)")
    a1.legend(frameon=False)
    a1.set_title("EW portfolio daily returns", loc="left")
    (osm, osr), (slope, icpt, _) = stats.probplot(ew, dist="norm")
    a2.scatter(osm, osr, s=8, color=BLUE)
    a2.plot(osm, slope * osm + icpt, color=ORANGE)
    a2.set_xlabel("Normal quantile")
    a2.set_ylabel("Observed return")
    a2.set_title("Normal QQ plot", loc="left")
    fig.tight_layout()
    fig.savefig(OUT / "ew_return_distribution.png")
    plt.close(fig)

    pd.set_option("display.width", 200)
    print(s.round(4).to_string())
    print(f"mean pairwise correlation {off.mean():.3f} (min {off.min():.3f}, max {off.max():.3f})")
    return s
