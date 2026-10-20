"""Checks on the TASI benchmark file itself (Saudi Exchange daily history, price index)."""
import numpy as np
import pandas as pd
import pytest

from tailwise import data

pytestmark = pytest.mark.skipif(not data.TASI_FILE.exists(), reason="TASI file not present")


@pytest.fixture(scope="module")
def tasi():
    df = pd.read_csv(data.TASI_FILE)
    df["Date"] = pd.to_datetime(df["Date"], format="%Y-%m-%d")
    return df


def test_shape_and_range(tasi):
    assert list(tasi.columns) == ["Date", "Close"]
    assert len(tasi) == 3443
    assert tasi.Date.iloc[0] == pd.Timestamp("2013-01-01")
    assert tasi.Date.iloc[-1] == pd.Timestamp("2026-10-20")


def test_dates_strictly_increasing(tasi):
    assert tasi.Date.is_monotonic_increasing and tasi.Date.is_unique


def test_close_numeric_positive_and_plausible(tasi):
    assert pd.api.types.is_float_dtype(tasi.Close) and tasi.Close.notna().all()
    assert (tasi.Close > 0).all()
    assert tasi.Close.between(5400, 13900).all()


def test_no_daily_move_beyond_ten_percent(tasi):
    lr = np.log(tasi.Close).diff()
    assert lr.abs().max() < 0.10
    worst = lr.abs().idxmax()
    assert tasi.Date[worst] == pd.Timestamp("2020-03-08")
    assert lr[worst] == pytest.approx(-0.087, abs=0.001)
