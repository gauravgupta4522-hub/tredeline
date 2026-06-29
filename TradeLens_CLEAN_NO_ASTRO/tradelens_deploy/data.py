"""
data.py
--------
Market data fetching for Nifty, Sensex, BankNifty (and gold/crypto as extras).
Uses yfinance. Includes caching so we don't hammer the network.

IMPORTANT (honest note):
  yfinance gives delayed / end-of-day quality data for free. It is great for
  BACKTESTING and learning, but it is NOT a low-latency live feed for real
  auto-execution. For real intraday signals you need a broker feed
  (Angel One SmartAPI, etc.). This module is built for analysis + backtest.
"""

from __future__ import annotations

import datetime as _dt
import time
from functools import lru_cache

import pandas as pd
import yfinance as yf

# Friendly name  ->  yfinance ticker
SYMBOLS = {
    "Nifty 50": "^NSEI",
    "Sensex": "^BSESN",
    "Bank Nifty": "^NSEBANK",
    "Nifty IT": "^CNXIT",
    "Gold (USD)": "GC=F",
    "Gold (INR ETF)": "GOLDBEES.NS",
    "Bitcoin (USD)": "BTC-USD",
    "Ethereum (USD)": "ETH-USD",
}


def list_symbols() -> list[str]:
    return list(SYMBOLS.keys())


@lru_cache(maxsize=64)
def _download_cached(ticker: str, period: str, interval: str) -> pd.DataFrame:
    # retry a couple of times — free hosts sometimes get throttled by Yahoo
    last_err = None
    for attempt in range(3):
        try:
            df = yf.download(
                ticker,
                period=period,
                interval=interval,
                auto_adjust=True,
                progress=False,
            )
            if df is not None and not df.empty:
                return df
        except Exception as e:  # noqa
            last_err = e
        time.sleep(1.2 * (attempt + 1))
    if last_err:
        raise last_err
    return pd.DataFrame()


def get_history(name: str, period: str = "5y", interval: str = "1d") -> pd.DataFrame:
    """
    Return a clean OHLCV DataFrame with columns:
    ['Open', 'High', 'Low', 'Close', 'Volume'] indexed by date.
    """
    ticker = SYMBOLS.get(name, name)
    df = _download_cached(ticker, period, interval).copy()

    if df.empty:
        raise ValueError(
            f"No data returned for '{name}' ({ticker}). "
            "Network issue or market closed for too long?"
        )

    # yfinance sometimes returns multi-index columns -> flatten
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    keep = ["Open", "High", "Low", "Close", "Volume"]
    df = df[[c for c in keep if c in df.columns]].copy()
    df = df.dropna()
    df.index.name = "Date"
    return df


def last_price(name: str) -> float:
    df = get_history(name, period="5d", interval="1d")
    return float(df["Close"].iloc[-1])


def clear_cache() -> None:
    _download_cached.cache_clear()


if __name__ == "__main__":
    # quick smoke test
    for s in ["Nifty 50", "Sensex"]:
        d = get_history(s, period="1y")
        print(s, d.shape, "last close:", round(float(d['Close'].iloc[-1]), 2))
