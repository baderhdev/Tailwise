"""Phase 4: real-time market volatility regimes from TASI, and Phase 2/3 accuracy split by regime.

The HMM runs on TASI daily returns on TASI's own trading calendar since 2013. The regime for day t
is the predicted probability of the turbulent state given TASI returns before t only (forward
filter, then one step through the transition matrix). Parameters are refitted every 21 sessions
on all TASI history to date.
"""
import logging

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from hmmlearn.hmm import GaussianHMM

from .covariance import qlike
from .data import ROOT, load_returns, load_tasi_returns
from .eda import BLUE, ORANGE
from .var import kupiec

logging.getLogger("hmmlearn").setLevel(logging.ERROR)  # convergence chatter on short samples

OUT = ROOT / "results" / "phase4"
WINDOW = 250
REFIT = 21
SEEDS = range(5)


def fit_hmm(x):
    """Best of several seeded EM runs; state 1 is the higher-variance (turbulent) state."""
    best = None
    for s in SEEDS:
        m = GaussianHMM(n_components=2, covariance_type="diag", n_iter=200, random_state=s).fit(x)
        score = m.score(x)
        if best is None or score > best[0]:
            best = (score, m)
    m = best[1]
    order = np.argsort(m.covars_.ravel())
    return m, order


def hmm_regimes(r, window=WINDOW, refit=REFIT):
    """Predicted P(turbulent on day t | r[:t]) for every t >= window."""
    x = 100 * np.asarray(r).reshape(-1, 1)
    prob = np.full(len(x), np.nan)
    for t in range(window, len(x)):
        if (t - window) % refit == 0:
            m, order = fit_hmm(x[:t])
        filtered = m.predict_proba(x[:t])[-1]  # last smoothed posterior equals the filtered one
        prob[t] = (filtered @ m.transmat_)[order[1]]
    return prob


def threshold_regimes(r, window=WINDOW, vol_days=21):
    """Cross-check: turbulent when trailing 21-day vol (to t-1) exceeds its own median to date."""
    vol = pd.Series(r).rolling(vol_days).std().shift(1)
    med = vol.expanding().median()
    lab = (vol > med).astype(float)
    lab[:window] = np.nan
    return lab.values


def market_regimes(tasi_ret):
    """Real-time regime labels for every TASI session after the first WINDOW, from TASI alone."""
    r = tasi_ret.dropna()
    prob, thr = hmm_regimes(r.values), threshold_regimes(r.values)
    reg = pd.DataFrame({"p_turbulent": prob, "hmm": prob > 0.5, "threshold": thr == 1}, index=r.index)
    return reg[~np.isnan(prob)]


def var_by_regime(fc, reg):
    df = fc.merge(reg, on="date")
    df["hit"] = df.ret < -df["var"]
    rows = []
    for (p, m, a, s), g in df.groupby(["portfolio", "method", "alpha", "regime"]):
        rows.append(dict(portfolio=p, method=m, level=f"{1 - a:.0%}", regime=s, days=len(g),
                         expected=a * len(g), exceedances=int(g.hit.sum()), rate_pct=g.hit.mean() * 100,
                         kupiec_p=kupiec(g.hit.values, a)[1]))
    return pd.DataFrame(rows)


def cov_by_regime(wf, reg):
    df = wf.merge(reg.rename(columns={"date": "origin"}), on="origin")
    df["qlike"] = qlike(df.realised, df.forecast)
    res = (df.groupby(["portfolio", "method", "regime"])
             .agg(months=("qlike", "size"), qlike=("qlike", "mean"), rv=("realised", "sum"), f=("forecast", "sum"))
             .reset_index())
    res["mean_rv_over_mean_f"] = res.rv / res.f
    return res.drop(columns=["rv", "f"])


def plot(dates, r, prob):
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(10, 5.5), sharex=True, gridspec_kw={"height_ratios": [2, 1]})
    turb = prob > 0.5
    a1.vlines(dates, 0, r * 100, color="#c3c2b7", lw=0.6)  # lines, not bars: thin bars drop large moves
    a1.vlines(dates[turb], 0, r[turb] * 100, color=ORANGE, lw=0.6, label="Labelled turbulent (known that morning)")
    a1.set_ylabel("TASI daily return, %")
    a1.legend(frameon=False, loc="lower left")
    a1.set_title("Real-time HMM regimes on TASI (label uses only earlier sessions)", loc="left")
    a2.plot(dates, prob, color=BLUE)
    a2.axhline(0.5, color="#898781", lw=0.8, ls="--")
    a2.set_ylabel("P(turbulent)")
    fig.tight_layout()
    fig.savefig(OUT / "hmm_regimes.png")
    plt.close(fig)


def run():
    OUT.mkdir(parents=True, exist_ok=True)
    tasi = load_tasi_returns(full=True)
    full = market_regimes(tasi)
    full.to_csv(OUT / "regimes_tasi_full.csv", float_format="%.4f")
    plot(full.index, tasi.loc[full.index].values, full.p_turbulent.values)
    # panel dates are all TASI sessions (inner join), so each gets the label known that morning
    reg = full.loc[load_returns().index.intersection(full.index)].rename_axis("date").reset_index()
    reg.to_csv(OUT / "regimes.csv", index=False, float_format="%.4f")

    fc = pd.read_csv(ROOT / "results" / "phase3" / "forecasts.csv", parse_dates=["date"])
    wf = pd.read_csv(ROOT / "results" / "phase2" / "walk_forward.csv", parse_dates=["origin"])
    out = {}
    for name in ("hmm", "threshold"):
        lab = reg[["date"]].assign(regime=np.where(reg[name], "turbulent", "calm"))
        out[name] = (var_by_regime(fc, lab), cov_by_regime(wf, lab))
        out[name][0].to_csv(OUT / f"var_by_regime_{name}.csv", index=False, float_format="%.4f")
        out[name][1].to_csv(OUT / f"cov_by_regime_{name}.csv", index=False, float_format="%.4f")

    pd.set_option("display.width", 220)
    print(f"turbulent share: hmm {reg.hmm.mean():.1%}, threshold {reg.threshold.mean():.1%}, "
          f"agreement {(reg.hmm == reg.threshold).mean():.1%}")
    v, c = out["hmm"]
    print(v[v.portfolio == "equal_weight"].round(3).to_string(index=False))
    print(c[c.portfolio == "equal_weight"].round(3).to_string(index=False))
    return out
