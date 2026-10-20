import numpy as np

from tailwise import regimes


def switching(n=500, seed=0):
    """Calm/turbulent blocks with 4x volatility in the turbulent ones."""
    rng = np.random.default_rng(seed)
    state = np.zeros(n, int)
    for start in (120, 330):
        state[start:start + 60] = 1
    return rng.normal(0, np.where(state == 1, 0.02, 0.005)), state


def test_hmm_finds_turbulent_blocks():
    r, state = switching()
    prob = regimes.hmm_regimes(r, window=100, refit=50)
    t = np.arange(100, len(r))
    lab = prob[t] > 0.5
    assert (lab == (state[t] == 1)).mean() > 0.85


def test_hmm_no_lookahead():
    r, _ = switching()
    k = 340
    shocked = r.copy()
    shocked[k:] *= 10
    a = regimes.hmm_regimes(r, window=300, refit=21)
    b = regimes.hmm_regimes(shocked, window=300, refit=21)
    assert np.allclose(a[300:k + 1], b[300:k + 1])
    assert not np.allclose(a[k + 1:], b[k + 1:])


def test_threshold_no_lookahead():
    r, _ = switching()
    k = 400
    shocked = r.copy()
    shocked[k:] *= 10
    a, b = regimes.threshold_regimes(r, window=100), regimes.threshold_regimes(shocked, window=100)
    assert np.array_equal(a[100:k + 1], b[100:k + 1])
