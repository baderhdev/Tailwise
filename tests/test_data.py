import numpy as np
import pandas as pd
import pytest

from tailwise import data


def frame(close, volume, start="2020-01-05"):
    idx = pd.bdate_range(start, periods=len(close))
    close = np.asarray(close, float)
    return pd.DataFrame({"Close": close, "Adj Close": close, "Volume": np.asarray(volume, float)}, index=idx)


def test_filler_rows_dropped():
    df = frame([10, 10, 10.5], [100, 0, 100])
    out, log = data.drop_filler(df, "X")
    assert len(out) == 2 and len(log) == 1


def base(n=80):
    rng = np.random.default_rng(0)
    return list(100 * np.cumprod(1 + rng.normal(0, 0.01, n))), [1e6] * n


def test_spike_reversal_removed():
    close, vol = base()
    close[70] = close[69] * 1.5
    out, log = data.drop_spikes(frame(close, vol), "X")
    assert len(log) == 1 and len(out) == 79 and out.index[69] == frame(close, vol).index[69]


def test_genuine_limit_move_kept():
    # a real limit-down day on heavy volume that does not reverse must survive
    close, vol = base()
    close[70:] = [c * 0.9 for c in close[70:]]
    vol[70] = 5e6
    out, log = data.drop_spikes(frame(close, vol), "X")
    assert log == [] and len(out) == 80


def test_spike_rule_looks_at_most_one_day_ahead():
    # the decision for day t must not change when prices after t+1 change
    close, vol = base()
    close[50] = close[49] * 1.5
    _, log_a = data.drop_spikes(frame(close, vol), "X")
    close2 = close[:52] + [c * 0.7 for c in close[52:]]
    _, log_b = data.drop_spikes(frame(close2, vol), "X")
    assert [l[1] for l in log_a[:1]] == [l[1] for l in log_b[:1]]


def test_missing_date_dropped_for_all_and_return_spans_gap(monkeypatch):
    monkeypatch.setattr(data, "WARMUP_START", "2020-01-01")
    monkeypatch.setattr(data, "START", "2020-01-01")
    a = frame([100, 110, 121, 133.1], [1] * 4)
    b = frame([50, 50, 55, 55], [1, 0, 1, 1])  # day 2 is filler for b
    prices, rets, log = data.build_panel({"A": a, "B": b})
    assert len(prices) == 3
    assert rets["A"].iloc[0] == pytest.approx(0.21)  # 100 -> 121 across the dropped date
    assert (log["action"] == "drop_date_all").sum() == 1


def write(tmp_path, lines):
    p = tmp_path / "tasi.csv"
    p.write_text("\n".join(lines) + "\n")
    return p


def test_load_tasi_reads_schema(tmp_path):
    s = data.load_tasi(write(tmp_path, ["Date,Close", "2024-03-03,12300.5", "2024-03-04,12400"]))
    assert list(s.values) == [12300.5, 12400.0] and isinstance(s.index, pd.DatetimeIndex)


@pytest.mark.parametrize("lines", [
    ["Date,Close", "03/03/2024,1", "03/04/2024,2"],  # not YYYY-MM-DD
    ["Date,Close", "2024-03-04,1", "2024-03-03,2"],  # not increasing
    ["Date,Close", "2024-03-03,1", "2024-03-03,2"],  # duplicate
    ["Date,Close", "2024-03-03,1", "2024-03-04,0"],  # non-positive
    ["Date,Price", "2024-03-03,1", "2024-03-04,2"],  # wrong column
])
def test_load_tasi_rejects_schema_violations(tmp_path, lines):
    with pytest.raises(ValueError):
        data.load_tasi(write(tmp_path, lines))


def test_inner_join_with_tasi_no_forward_fill(monkeypatch):
    monkeypatch.setattr(data, "WARMUP_START", "2020-01-01")
    monkeypatch.setattr(data, "START", "2020-01-01")
    a = frame([100, 110, 121, 133.1] + [140.0] * 56, [1] * 60)  # 60 weekdays from Mon Jan 6
    idx = a.index
    # TASI lacks stock day Jan 8 and has a session on Saturday Jan 11 that the stocks lack
    tasi_idx = idx.delete(2).append(pd.DatetimeIndex(["2020-01-11"])).sort_values()
    tasi = pd.Series(10.0, index=tasi_idx)
    prices, rets, log = data.build_panel({"A": a}, tasi)
    assert list(prices.index) == list(idx.delete(2))  # Jan 8 dropped, nothing filled in
    assert rets["A"].iloc[1] == pytest.approx(133.1 / 110 - 1)  # the return spans the dropped date
    assert (log.action == "drop_date_no_tasi").sum() == 1
    assert (log.action == "tasi_session_not_in_stocks").sum() == 1


def test_align_refuses_tasi_missing_many_stock_dates():
    prices = pd.DataFrame({"A": range(1, 101)}, index=pd.bdate_range("2024-01-01", periods=100))
    tasi = pd.Series(1.0, index=prices.index[:90])
    with pytest.raises(ValueError):
        data.align_calendars(prices, tasi)


def test_panel_stops_at_end_date(monkeypatch):
    # a refresh that brings dates past END must reproduce the fixed sample, not extend it
    monkeypatch.setattr(data, "WARMUP_START", "2020-01-01")
    monkeypatch.setattr(data, "START", "2020-01-01")
    monkeypatch.setattr(data, "END", "2020-01-10")
    a = frame([100.0] * 10, [1] * 10)  # Jan 6 to Jan 17
    prices, rets, log = data.build_panel({"A": a})
    assert prices.index[-1] == pd.Timestamp("2020-01-10") and len(prices) == 5
