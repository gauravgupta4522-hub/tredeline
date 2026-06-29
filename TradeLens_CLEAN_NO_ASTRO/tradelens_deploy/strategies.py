"""
strategies.py
-------------
Indicator calculation + Buy/Sell signal strategies.

A "signal" column convention used everywhere in this project:
    +1  -> be LONG (buy / hold long)
     0  -> be FLAT (no position)
    -1  -> be SHORT (sell / hold short)

These are decision-support signals. They are NOT a promise of profit.
Every strategy can lose money in some market regimes. Always check the
backtest tab before trusting any of them.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


# --------------------------------------------------------------------------
# Core indicators
# --------------------------------------------------------------------------
def ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()


def sma(series: pd.Series, window: int) -> pd.Series:
    return series.rolling(window).mean()


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    out = 100 - (100 / (1 + rs))
    return out.fillna(50)


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high, low, close = df["High"], df["Low"], df["Close"]
    prev_close = close.shift(1)
    tr = pd.concat(
        [(high - low), (high - prev_close).abs(), (low - prev_close).abs()],
        axis=1,
    ).max(axis=1)
    return tr.ewm(alpha=1 / period, adjust=False).mean()


def macd(series: pd.Series, fast=12, slow=26, signal=9):
    macd_line = ema(series, fast) - ema(series, slow)
    signal_line = ema(macd_line, signal)
    hist = macd_line - signal_line
    return macd_line, signal_line, hist


def bollinger(series: pd.Series, window=20, n_std=2.0):
    mid = sma(series, window)
    sd = series.rolling(window).std()
    upper = mid + n_std * sd
    lower = mid - n_std * sd
    return lower, mid, upper


# --------------------------------------------------------------------------
# Strategies  (each returns df with a 'signal' column)
# --------------------------------------------------------------------------
def strat_ema_crossover(df: pd.DataFrame, fast=20, slow=50) -> pd.DataFrame:
    out = df.copy()
    out["ema_fast"] = ema(out["Close"], fast)
    out["ema_slow"] = ema(out["Close"], slow)
    out["signal"] = np.where(out["ema_fast"] > out["ema_slow"], 1, -1)
    return out


def strat_rsi_reversion(df: pd.DataFrame, period=14, low=30, high=70) -> pd.DataFrame:
    out = df.copy()
    out["rsi"] = rsi(out["Close"], period)
    sig = np.zeros(len(out))
    pos = 0
    vals = out["rsi"].values
    for i in range(len(vals)):
        if vals[i] < low:
            pos = 1            # oversold -> go long
        elif vals[i] > high:
            pos = 0            # overbought -> exit (this is a long-only mean reversion)
        sig[i] = pos
    out["signal"] = sig
    return out


def strat_macd(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    m, s, h = macd(out["Close"])
    out["macd"], out["macd_signal"], out["macd_hist"] = m, s, h
    out["signal"] = np.where(m > s, 1, -1)
    return out


def strat_breakout(df: pd.DataFrame, lookback=20) -> pd.DataFrame:
    """Donchian-style breakout: new N-day high -> long, new N-day low -> flat/short."""
    out = df.copy()
    out["hh"] = out["High"].rolling(lookback).max().shift(1)
    out["ll"] = out["Low"].rolling(lookback).min().shift(1)
    sig = np.zeros(len(out))
    pos = 0
    c = out["Close"].values
    hh = out["hh"].values
    ll = out["ll"].values
    for i in range(len(out)):
        if not np.isnan(hh[i]) and c[i] > hh[i]:
            pos = 1
        elif not np.isnan(ll[i]) and c[i] < ll[i]:
            pos = 0
        sig[i] = pos
    out["signal"] = sig
    return out


def strat_combined(df: pd.DataFrame) -> pd.DataFrame:
    """
    Trend + momentum + filter combo:
      - EMA(20) > EMA(50)  (trend up)
      - MACD line > signal (momentum up)
      - RSI between 45 and 75 (not exhausted)
    All three agree -> long. Otherwise flat.
    More selective => fewer trades but usually cleaner.
    """
    out = df.copy()
    out["ema_fast"] = ema(out["Close"], 20)
    out["ema_slow"] = ema(out["Close"], 50)
    m, s, _ = macd(out["Close"])
    out["macd"], out["macd_signal"] = m, s
    out["rsi"] = rsi(out["Close"], 14)

    trend_up = out["ema_fast"] > out["ema_slow"]
    mom_up = out["macd"] > out["macd_signal"]
    rsi_ok = (out["rsi"] > 45) & (out["rsi"] < 75)

    out["signal"] = np.where(trend_up & mom_up & rsi_ok, 1, 0)
    return out


STRATEGIES = {
    "EMA Crossover (20/50)": strat_ema_crossover,
    "RSI Mean-Reversion": strat_rsi_reversion,
    "MACD Trend": strat_macd,
    "Donchian Breakout (20)": strat_breakout,
    "Combined (Trend+Momentum+RSI)": strat_combined,
}


def list_strategies() -> list[str]:
    return list(STRATEGIES.keys())


def run_strategy(name: str, df: pd.DataFrame) -> pd.DataFrame:
    fn = STRATEGIES[name]
    return fn(df)


def latest_action(signal_df: pd.DataFrame) -> str:
    """Human-readable current recommendation based on last two signal values."""
    s = signal_df["signal"].fillna(0).values
    if len(s) < 2:
        return "WAIT (not enough data)"
    cur, prev = s[-1], s[-2]
    if cur > prev:
        return "BUY  (signal turned up)"
    if cur < prev:
        return "SELL / EXIT  (signal turned down)"
    if cur > 0:
        return "HOLD LONG"
    if cur < 0:
        return "HOLD SHORT"
    return "STAY FLAT (no trade)"
