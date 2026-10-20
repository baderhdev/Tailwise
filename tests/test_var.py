import numpy as np
import pytest
from scipy import stats

from tailwise import var


def test_no_lookahead_in_forecasts():
    # shocking returns from day k onward must not change any forecast for days <= k
    rng = np.random.default_rng(1)
    r = rng.standard_t(5, 330) * 0.01
    k = 300
    shocked = r.copy()
    shocked[k:] *= 4
    a = var.forecasts(r, window=250, refit=21)
    b = var.forecasts(shocked, window=250, refit=21)
    early = a.t <= k
    assert np.allclose(a.loc[early, ["var", "es"]], b.loc[early, ["var", "es"]])
    assert not np.allclose(a.loc[~early, ["var", "es"]], b.loc[~early, ["var", "es"]])


def test_student_t_es_matches_simulation():
    params = (4.0, 0.001, 0.01)
    v, es = var.student_t(params, 0.01)
    x = stats.t.rvs(params[0], loc=params[1], scale=params[2], size=4_000_000, random_state=0)
    assert v == pytest.approx(-np.quantile(x, 0.01), rel=0.02)
    assert es == pytest.approx(-x[x <= -v].mean(), rel=0.02)


def test_student_t_fit_not_worse_than_default():
    rng = np.random.default_rng(3)
    for _ in range(20):
        x = rng.standard_t(6, 250) * 0.01
        best = var.student_t_fit(x)
        assert stats.t.logpdf(x, *best).sum() >= stats.t.logpdf(x, *stats.t.fit(x)).sum() - 1e-9


def test_normal_var_es_known_values():
    x = np.random.default_rng(0).normal(0, 1, 200_000)
    v, es = var.normal(x, 0.01)
    assert v == pytest.approx(2.326, abs=0.02) and es == pytest.approx(2.665, abs=0.02)


def test_kupiec_zero_at_expected_rate_and_rejects_far_off():
    hits = np.zeros(1000, bool)
    hits[:10] = True
    assert var.kupiec(hits, 0.01)[0] == pytest.approx(0, abs=1e-9)
    hits[:40] = True
    assert var.kupiec(hits, 0.01)[1] < 0.001


def test_christoffersen_detects_clustering():
    spread = np.zeros(1000, bool)
    spread[::100] = True
    clustered = np.zeros(1000, bool)
    clustered[500:510] = True
    assert var.christoffersen(spread)[1] > 0.5
    assert var.christoffersen(clustered)[1] < 0.001
