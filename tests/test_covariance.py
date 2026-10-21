import numpy as np
import pandas as pd
import pytest

from tailwise import covariance as cv


def synthetic(t=320, n=4, seed=0):
    rng = np.random.default_rng(seed)
    a = rng.normal(size=(n, n))
    x = rng.multivariate_normal(np.zeros(n), 1e-4 * (a @ a.T + np.eye(n)), size=t)
    return pd.DataFrame(x, index=pd.bdate_range("2020-01-01", periods=t))


def test_ledoit_wolf_matches_sklearn():
    from sklearn.covariance import LedoitWolf  # installed with hmmlearn; used only as a reference here
    x = synthetic().values
    assert np.allclose(cv.ledoit_wolf(x), LedoitWolf().fit(x).covariance_)


def test_no_lookahead_in_walk_forward():
    # changing returns from origin k onward must not change any forecast made at or before k
    rets = synthetic()
    w = cv.test_portfolios(rets.shape[1], n_random=1)
    a = cv.walk_forward(rets, w, h=10, window=250)
    k = 270
    shocked = rets.copy()
    shocked.iloc[k:] *= 5
    b = cv.walk_forward(shocked, w, h=10, window=250)
    early = a.origin <= rets.index[k]
    assert early.sum() > 0
    assert np.allclose(a.loc[early, "forecast"], b.loc[early, "forecast"])
    assert not np.allclose(a.loc[~early, "forecast"], b.loc[~early, "forecast"])


def test_qlike_minimised_at_truth():
    assert cv.qlike(2.0, 2.0) == pytest.approx(0)
    assert cv.qlike(2.0, 1.5) > 0 and cv.qlike(2.0, 2.5) > 0


def test_portfolio_weights_reproducible_and_valid():
    a, b = cv.test_portfolios(24), cv.test_portfolios(24)
    for k in a:
        assert np.allclose(a[k], b[k]) and np.isclose(a[k].sum(), 1) and (a[k] >= 0).all()


def test_newey_west_se_iid_and_autocorrelated():
    rng = np.random.default_rng(1)
    d = rng.normal(0.1, 1, 20000)
    assert cv.newey_west_se(d) == pytest.approx(d.std() / np.sqrt(len(d)), rel=0.05)
    ar = np.zeros(20000)
    for i in range(1, len(ar)):
        ar[i] = 0.5 * ar[i - 1] + d[i]
    assert cv.newey_west_se(ar) > 1.3 * ar.std() / np.sqrt(len(ar))  # positive autocorrelation widens it


def test_evaluate_finds_the_better_forecast():
    rng = np.random.default_rng(2)
    origins = pd.bdate_range("2021-01-01", periods=200)
    truth = rng.uniform(0.5, 2.0, 200)
    realised = truth * rng.chisquare(21, 200) / 21
    wf = pd.concat([pd.DataFrame({"origin": origins, "portfolio": "p", "method": m, "forecast": f, "realised": realised})
                    for m, f in [("sample_250", 2 * truth), ("good", truth)]])
    res = cv.evaluate(wf).set_index("method")
    assert res.loc["sample_250", "qlike_diff_vs_base"] == 0
    assert res.loc["good", "qlike_diff_vs_base"] < 0 and res.loc["good", "dm_p"] < 0.01
    assert res.loc["good", "diff_ci_high"] < 0
