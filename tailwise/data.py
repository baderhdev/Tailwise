"""Download, cache, and clean Tadawul prices. Every cleaning action is written to the cleaning log."""
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
PROC = ROOT / "data" / "processed"

START = "2019-12-11"  # Saudi Aramco's first trading day
END = "2026-10-20"  # last session in the TASI file: a later --refresh reproduces this sample, not a longer one
WARMUP_START = "2019-06-01"  # extra history so the trailing-volume median exists at START
LIMIT = 0.10  # Tadawul daily price limit
# Saudi Exchange official TASI daily history: a price index (no dividends reinvested)
TASI_FILE = RAW / "TASI_daily_close_2013-01-01_to_2026-10-20.csv"

UNIVERSE = {
    "2222.SR": "Saudi Aramco", "2010.SR": "SABIC", "2020.SR": "SABIC Agri-Nutrients", "2310.SR": "Sipchem",
    "2350.SR": "Saudi Kayan", "2290.SR": "Yansab", "1211.SR": "Ma'aden",
    "1120.SR": "Al Rajhi Bank", "1180.SR": "Saudi National Bank", "1010.SR": "Riyad Bank",
    "1060.SR": "Saudi Awwal Bank", "1150.SR": "Alinma Bank", "1140.SR": "Bank Albilad", "1080.SR": "Arab National Bank",
    "7010.SR": "stc", "7020.SR": "Mobily", "7030.SR": "Zain KSA", "5110.SR": "Saudi Electricity",
    "2280.SR": "Almarai", "4190.SR": "Jarir", "4002.SR": "Mouwasat", "8210.SR": "Bupa Arabia",
    "4300.SR": "Dar Al Arkan", "4030.SR": "Bahri",
}


def download(tickers=UNIVERSE, refresh=False):
    """Raw yfinance history per ticker, cached as CSV so reruns use the same snapshot."""
    import yfinance as yf

    RAW.mkdir(parents=True, exist_ok=True)
    out = {}
    for t in tickers:
        path = RAW / f"yf_{t}.csv"
        if refresh or not path.exists():
            df = yf.Ticker(t).history(period="max", auto_adjust=False, actions=True)
            if df.empty:
                raise RuntimeError(f"yfinance returned no data for {t}")
            df.index = df.index.tz_localize(None).normalize()
            df.index.name = "Date"
            df.to_csv(path)
        out[t] = read_raw(path)
    return out


def drop_filler(df, ticker):
    """Yahoo inserts zero-volume, carried-forward bars on holidays and outages; they are not trades."""
    bad = (df["Volume"] <= 0) | df["Adj Close"].isna()
    log = [(ticker, d, "drop_filler", f"volume={v:.0f}") for d, v in df.loc[bad, "Volume"].items()]
    return df[~bad], log


def drop_spikes(df, ticker):
    """Drop a day that moves >10% and reverses by >10% the next day (a bad print beyond the daily limit).

    Uses day t+1 to judge day t: this is a data-correction step (like a vendor fixing a bad print),
    not a forecast input. No volume test: Yahoo's Tadawul volumes are themselves unreliable.
    """
    r = df["Adj Close"].pct_change()
    r_next = r.shift(-1)
    spike = (r.abs() > LIMIT) & (r_next.abs() > LIMIT) & (np.sign(r) != np.sign(r_next))
    log = [(ticker, d, "drop_spike", f"ret={r[d]:+.3f} next={r_next[d]:+.3f}") for d in df.index[spike]]
    return df[~spike], log


def flag_stale(df, ticker, max_run=5):
    """Log (do not change) runs of more than max_run unchanged closes on days with real volume."""
    same = df["Close"].diff() == 0
    groups = (~same).cumsum()
    log = []
    for _, run in same[same].groupby(groups[same]):
        if len(run) > max_run:
            log.append((ticker, run.index[0], "flag_stale", f"{len(run)} unchanged closes to {run.index[-1].date()}"))
    return log


def build_panel(raw, tasi=None):
    """Clean each ticker, then keep only dates on which every ticker has a valid price
    (and, if `tasi` is given, on which TASI also has a close: an inner join, see align_calendars).

    Returns (prices, returns, log). A date missing for any stock is dropped for all, so the return
    on the following date spans both days for every stock alike.
    """
    log, clean = [], {}
    for t, df in raw.items():
        df = df.loc[WARMUP_START:]
        df, l1 = drop_filler(df, t)
        df, l2 = drop_spikes(df, t)
        log += l1 + l2 + flag_stale(df.loc[START:END], t)
        clean[t] = df.loc[START:END, "Adj Close"]
    wide = pd.DataFrame(clean).sort_index()
    incomplete = wide.isna().any(axis=1)
    for d in wide.index[incomplete]:
        missing = ",".join(wide.columns[wide.loc[d].isna()])
        log.append(("ALL", d, "drop_date_all", f"missing: {missing}"))
    prices = wide[~incomplete]
    if tasi is not None:
        n_before = len(prices)
        prices, _, drop_stock, drop_tasi = align_calendars(prices, tasi)
        log += [("ALL", d, "drop_date_no_tasi", "stock date with no TASI close") for d in drop_stock]
        log += [("TASI", d, "tasi_session_not_in_stocks", "TASI session missing from the stock panel") for d in drop_tasi]
        print(f"calendar join: {n_before} stock dates, {n_before - len(drop_stock) + len(drop_tasi)} TASI sessions "
              f"in sample -> {len(prices)} common; dropped {len(drop_stock)} stock-side, {len(drop_tasi)} TASI-side")
    returns = prices.pct_change().iloc[1:]
    for t in returns:
        for d, x in returns[t][returns[t].abs() > LIMIT].items():
            log.append((t, d, "flag_over_limit", f"kept, ret={x:+.3f}"))
    log = pd.DataFrame(log, columns=["ticker", "date", "action", "detail"])
    log = log[log["date"].between(pd.Timestamp(START), pd.Timestamp(END))]
    log = log.sort_values(["date", "ticker"]).reset_index(drop=True)
    return prices, returns, log


TASI_SCHEMA = """TASI file schema, one row per Tadawul trading session:
  Date   YYYY-MM-DD, strictly increasing, no duplicates
  Close  float > 0, TASI closing level. A price index: dividends are not reinvested."""


def read_raw(path):
    """Shared reader for every raw daily file (cached Yahoo stock CSVs and the TASI file)."""
    return pd.read_csv(path, index_col="Date", parse_dates=True, date_format="%Y-%m-%d")


def load_tasi(path=TASI_FILE):
    """TASI close on its own trading calendar. Refuses any file that breaks TASI_SCHEMA."""
    df = read_raw(path)
    problems = []
    if list(df.columns) != ["Close"]:
        problems.append(f"columns {['Date', *df.columns]}, expected ['Date', 'Close']")
    if not isinstance(df.index, pd.DatetimeIndex):
        problems.append("dates are not all YYYY-MM-DD")
    elif not (df.index.is_monotonic_increasing and df.index.is_unique):
        problems.append("dates are not strictly increasing")
    if "Close" in df and not (pd.api.types.is_numeric_dtype(df["Close"]) and (df["Close"] > 0).all()):
        problems.append("Close is not numeric and positive")
    if problems:
        raise ValueError(f"{path.name}: " + "; ".join(problems) + "\n" + TASI_SCHEMA)
    return df["Close"].rename("TASI")


def align_calendars(prices, tasi, max_drop=0.02):
    """Inner join of the stock panel and TASI on trading dates, within the stock sample. No forward-fill.

    Returns (prices, tasi, dates dropped from the stock side, TASI sessions dropped). Refuses if TASI
    lacks more than max_drop of the stock dates, which would point to a wrong file.
    """
    in_sample = tasi.loc[prices.index[0]:prices.index[-1]]
    common = prices.index.intersection(in_sample.index)
    drop_stock, drop_tasi = prices.index.difference(common), in_sample.index.difference(common)
    if len(drop_stock) > max_drop * len(prices):
        raise ValueError(f"TASI lacks {len(drop_stock)} of {len(prices)} stock dates")
    return prices.loc[common], in_sample.loc[common], drop_stock, drop_tasi


def run(refresh=False):
    PROC.mkdir(parents=True, exist_ok=True)
    raw = download(refresh=refresh)
    download(["BZ=F"], refresh=refresh)  # Brent for Phase 5, refreshed together with the stocks
    tasi_full = load_tasi() if TASI_FILE.exists() else None
    prices, returns, log = build_panel(raw, tasi_full)
    # price-return panel (split-adjusted Close, no dividends), the like-for-like comparison with TASI
    close = pd.DataFrame({t: d["Close"] for t, d in raw.items()}).reindex(prices.index)
    assert close.notna().all().all(), "Close missing on a panel date"
    close.pct_change().iloc[1:].to_csv(PROC / "returns_price.csv")
    if tasi_full is not None:
        tasi = tasi_full.reindex(prices.index)
        pd.DataFrame({"close": tasi, "ret": tasi.pct_change()}).to_csv(PROC / "tasi.csv")
        pd.DataFrame({"close": tasi_full, "ret": tasi_full.pct_change()}).to_csv(PROC / "tasi_full.csv")
    else:
        print(f"WARNING: {TASI_FILE.name} not found; benchmark skipped")
    prices.to_csv(PROC / "prices.csv")
    returns.to_csv(PROC / "returns.csv")
    log.to_csv(PROC / "cleaning_log.csv", index=False)
    print(f"panel: {len(prices)} dates, {prices.shape[1]} stocks, {prices.index[0].date()} -> {prices.index[-1].date()}")
    print(log["action"].value_counts().to_string())
    return prices, returns, log


def load_returns():
    return pd.read_csv(PROC / "returns.csv", index_col=0, parse_dates=True)


def load_tasi_returns(full=False):
    """TASI daily price returns: on the stock panel calendar, or (full=True) on TASI's own calendar since 2013."""
    path = PROC / ("tasi_full.csv" if full else "tasi.csv")
    return pd.read_csv(path, index_col=0, parse_dates=True)["ret"] if path.exists() else None


def load_price_returns():
    return pd.read_csv(PROC / "returns_price.csv", index_col=0, parse_dates=True)
