"""TASI as the market benchmark: relative performance and beta of the test portfolios.

TASI is a price index (no dividends reinvested), so every comparison here uses the stocks' price
returns (split-adjusted Close). The walk-forward beta for day t uses only the days before t.
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .covariance import test_portfolios
from .data import ROOT, START, load_price_returns, load_returns, load_tasi_returns
from .eda import BLUE, ORANGE, per_year

OUT = ROOT / "results" / "benchmark"
BETA_WINDOW = 250


def rolling_beta(y, x, window=BETA_WINDOW):
    """Beta of y on x for day t from the `window` days before t, so it is known before day t trades."""
    return (y.rolling(window).cov(x) / x.rolling(window).var()).shift(1)


def run():
    OUT.mkdir(parents=True, exist_ok=True)
    rp, tasi = load_price_returns(), load_tasi_returns()
    if tasi is None:
        print("benchmark skipped: no TASI")
        return None
    tasi = tasi.loc[rp.index]
    ports = pd.DataFrame({p: rp.values @ w for p, w in test_portfolios(rp.shape[1]).items()}, index=rp.index)
    ppy = per_year(rp.index, START)
    ann_ret = lambda r: (1 + r).prod() ** (ppy / len(r)) - 1
    ann_vol = lambda r: r.std() * np.sqrt(ppy)

    rows, betas = [], {}
    for p, r in ports.items():
        betas[p] = rolling_beta(r, tasi)
        diff = r - tasi
        rows.append(dict(series=p, ann_price_return=ann_ret(r), ann_vol=ann_vol(r),
                         excess_return_vs_tasi=ann_ret(r) - ann_ret(tasi), tracking_error=ann_vol(diff),
                         correlation=r.corr(tasi), full_sample_beta=r.cov(tasi) / tasi.var(),
                         wf_beta_mean=betas[p].mean(), wf_beta_min=betas[p].min(), wf_beta_max=betas[p].max(),
                         wf_beta_latest=betas[p].iloc[-1]))
    rows.append(dict(series="TASI", ann_price_return=ann_ret(tasi), ann_vol=ann_vol(tasi)))
    res = pd.DataFrame(rows)
    ew_total = load_returns().mean(axis=1)
    res.loc[res.series == "equal_weight", "ann_total_return"] = ann_ret(ew_total)  # for the dividend effect only
    res.to_csv(OUT / "relative_performance.csv", index=False, float_format="%.5f")
    pd.DataFrame(betas).to_csv(OUT / "walk_forward_beta.csv", float_format="%.4f")

    fig, (a1, a2) = plt.subplots(2, 1, figsize=(10, 6), sharex=True, gridspec_kw={"height_ratios": [2, 1]})
    a1.plot((1 + ports.equal_weight).cumprod(), color=BLUE, label="Equal-weight portfolio (price return)")
    a1.plot((1 + tasi).cumprod(), color=ORANGE, label="TASI (price index)")
    a1.set_ylabel("Growth of 1, price return")
    a1.legend(frameon=False)
    a1.set_title("Equal-weight portfolio vs TASI, and its walk-forward beta", loc="left")
    a2.plot(betas["equal_weight"], color=BLUE)
    a2.axhline(1, color="#898781", lw=0.8, ls="--")
    a2.set_ylabel(f"Beta to TASI ({BETA_WINDOW}d, prior days)")
    fig.tight_layout()
    fig.savefig(OUT / "ew_vs_tasi.png")
    plt.close(fig)

    pd.set_option("display.width", 250)
    print(f"observations per year {ppy:.1f}")
    print(res.round(4).to_string(index=False))
    return res
