import numpy as np
import pandas as pd
import pytest

from tailwise import allocation as al


def test_min_variance_matches_closed_form_when_unconstrained_is_long_only():
    cov = np.diag([1.0, 2.0, 4.0])
    w = al.min_variance(cov)
    expected = (1 / np.diag(cov)) / (1 / np.diag(cov)).sum()
    assert np.allclose(w, expected, atol=1e-6)


def test_min_variance_long_only():
    rho = np.array([[1, 0.9, 0.1], [0.9, 1, 0.1], [0.1, 0.1, 1]])
    cov = rho * np.outer([0.1, 0.3, 0.2], [0.1, 0.3, 0.2])
    w = al.min_variance(cov)
    assert np.isclose(w.sum(), 1) and (w >= 0).all()


def test_weights_no_lookahead():
    rng = np.random.default_rng(0)
    x = rng.normal(0, 0.01, (320, 4))
    k = 280
    shocked = x.copy()
    shocked[k:] *= 5
    a = al.target_weights(x, {"s": "sample_250"}, window=250, h=10)["s"]
    b = al.target_weights(shocked, {"s": "sample_250"}, window=250, h=10)["s"]
    for (i, wa), (_, wb) in zip(a, b):
        if i <= k:
            assert np.allclose(wa, wb)


def test_simulate_costs_and_drift():
    x = np.zeros((40, 2))
    x[25, 0] = 0.10  # asset 0 gains 10% between rebalances at 20 and 30
    targets = [(20, np.array([0.5, 0.5])), (30, np.array([0.5, 0.5]))]
    r, to = al.simulate(x, targets, cost_bps=100)
    assert to[0] == pytest.approx(1.0)  # buy in from cash
    assert r[0] == pytest.approx(-0.01)
    drifted = np.array([0.55, 0.5]) / 1.05
    assert to[1] == pytest.approx(np.abs(np.array([0.5, 0.5]) - drifted).sum())
    assert r[5] == pytest.approx(0.05)


def test_per_year_counts_observations_per_calendar_year():
    from tailwise.eda import per_year
    dates = pd.date_range("2021-01-04", "2021-12-31", periods=240)
    assert per_year(dates, "2020-12-31") == pytest.approx(240, rel=0.01)
