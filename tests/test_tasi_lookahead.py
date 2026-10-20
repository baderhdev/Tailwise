"""No lookahead in anything built from TASI: shocking TASI from session k on must not change any
value used at or before k (walk-forward beta, regime labels, pre-episode beta predictions)."""
import numpy as np
import pandas as pd
import pytest

from tailwise import benchmark, regimes, stress


@pytest.fixture
def series():
    rng = np.random.default_rng(7)
    idx = pd.bdate_range("2015-01-01", periods=420)
    tasi = pd.Series(rng.normal(0, 0.01, len(idx)), index=idx)
    port = 0.9 * tasi + pd.Series(rng.normal(0, 0.005, len(idx)), index=idx)
    return tasi, port


def shock(s, k):
    out = s.copy()
    out.iloc[k:] = out.iloc[k:] * 6 + 0.01
    return out


def test_walk_forward_beta_no_lookahead(series):
    tasi, port = series
    k = 330
    a = benchmark.rolling_beta(port, tasi)
    b = benchmark.rolling_beta(shock(port, k), shock(tasi, k))
    assert np.allclose(a.iloc[:k + 1].dropna(), b.iloc[:k + 1].dropna())  # beta for day k uses days before k
    assert not np.allclose(a.iloc[k + 1:], b.iloc[k + 1:])


def test_rolling_beta_matches_ols_on_prior_window(series):
    tasi, port = series
    b = benchmark.rolling_beta(port, tasi, window=250)
    x, y = tasi.iloc[50:300], port.iloc[50:300]
    assert b.iloc[300] == pytest.approx(np.polyfit(x, y, 1)[0])


def test_market_regimes_no_lookahead(series):
    tasi, _ = series
    k = 360
    a = regimes.market_regimes(tasi)
    b = regimes.market_regimes(shock(tasi, k))
    early = a.index <= tasi.index[k]
    assert early.sum() > 50
    assert np.allclose(a.p_turbulent[early], b.p_turbulent[early])
    assert (a.threshold[early] == b.threshold[early]).all()
    assert not np.allclose(a.p_turbulent[~early], b.p_turbulent[~early])


def test_max_drawdown_dates():
    close = pd.Series([100, 120, 90, 60, 80, 130, 100], index=pd.bdate_range("2014-01-01", periods=7))
    peak, trough, dd = stress.max_drawdown_dates(close)
    assert peak == close.index[1] and trough == close.index[3] and dd == pytest.approx(-0.5)
