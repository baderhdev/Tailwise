import numpy as np
import pandas as pd

from tailwise import stress


def test_worst_windows_are_worst_and_disjoint():
    r = np.zeros(100)
    r[10:13] = -0.05
    r[50:53] = -0.03
    w = stress.worst_windows(r, 5, k=2)
    assert all(s <= 10 and e >= 12 for s, e in w[:1])
    assert abs(w[0][0] - w[1][0]) >= 5


def test_weekly_pairs_thursday_tadawul_with_prior_wednesday_brent():
    days = pd.date_range("2024-01-01", "2024-01-31")
    tad = pd.DataFrame({"A": np.arange(len(days), dtype=float) + 100}, index=days)
    brent = pd.Series(np.arange(len(days), dtype=float) + 50, index=days)
    wk = stress.weekly(tad, brent)
    d = wk.index[1]  # a Thursday
    assert d.day_name() == "Thursday"
    prev_thu, wed, prev_wed = d - pd.Timedelta(days=7), d - pd.Timedelta(days=1), d - pd.Timedelta(days=8)
    assert np.isclose(wk.loc[d, "A"], tad.A[d] / tad.A[prev_thu] - 1)
    assert np.isclose(wk.loc[d, "brent"], brent[wed] / brent[prev_wed] - 1)


def test_walk_forward_oil_no_lookahead():
    rng = np.random.default_rng(0)
    idx = pd.date_range("2020-01-02", periods=200, freq="W-THU")
    oil = pd.Series(rng.normal(0, 0.05, 200), index=idx)
    port = 0.1 * oil + pd.Series(rng.normal(0, 0.02, 200), index=idx)
    k = 150
    shocked = port.copy()
    shocked.iloc[k:] *= 5
    a = stress.walk_forward_oil(port, oil, min_weeks=104)
    b = stress.walk_forward_oil(shocked, oil, min_weeks=104)
    assert np.allclose(a.iloc[104:k + 1], b.iloc[104:k + 1])
    assert not np.allclose(a.iloc[k + 1:], b.iloc[k + 1:])
