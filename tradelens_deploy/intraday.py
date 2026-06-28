"""
intraday.py
-----------
Intraday strategies for 5m / 15m timeframes. Same signal convention:
   +1 long, 0 flat, -1 short.

Built to work on ANY intraday OHLCV DataFrame (from Angel candles OR yfinance).
These reuse indicators from strategies.py where possible.

Reality check: intraday edges decay fast and costs/slippage hurt more
(more trades). The backtest engine already charges per turn — use it.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from strategies import ema, rsi, atr


def vwap(df: pd.DataFrame) -> pd.Series:
    """Session VWAP, reset each day."""
    tp = (df["High"] + df["Low"] + df["Close"]) / 3
    pv = tp * df["Volume"].replace(0, np.nan).fillna(1)
    # group by date so VWAP resets daily
    day = pd.Series(df.index.date, index=df.index)
    cum_pv = pv.groupby(day).cumsum()
    cum_v = df["Volume"].replace(0, np.nan).fillna(1).groupby(day).cumsum()
    return cum_pv / cum_v


def supertrend(df: pd.DataFrame, period=10, mult=3.0) -> pd.Series:
    """Returns +1 (uptrend) / -1 (downtrend) supertrend direction."""
    a = atr(df, period)
    hl2 = (df["High"] + df["Low"]) / 2
    upper = hl2 + mult * a
    lower = hl2 - mult * a
    close = df["Close"].values
    up = upper.values
    lo = lower.values
    dir_ = np.ones(len(df))
    final_up = up.copy()
    final_lo = lo.copy()
    for i in range(1, len(df)):
        final_up[i] = min(up[i], final_up[i - 1]) if close[i - 1] <= final_up[i - 1] else up[i]
        final_lo[i] = max(lo[i], final_lo[i - 1]) if close[i - 1] >= final_lo[i - 1] else lo[i]
        if close[i] > final_up[i - 1]:
            dir_[i] = 1
        elif close[i] < final_lo[i - 1]:
            dir_[i] = -1
        else:
            dir_[i] = dir_[i - 1]
    return pd.Series(dir_, index=df.index)


# ---------------------------------------------------------------- strategies
def intraday_vwap(df: pd.DataFrame) -> pd.DataFrame:
    """Long above VWAP with momentum, flat below."""
    out = df.copy()
    out["vwap"] = vwap(out)
    out["ema9"] = ema(out["Close"], 9)
    long_cond = (out["Close"] > out["vwap"]) & (out["ema9"] > out["vwap"])
    out["signal"] = np.where(long_cond, 1, 0)
    return out


def intraday_orb(df: pd.DataFrame, opening_bars=3) -> pd.DataFrame:
    """
    Opening Range Breakout: each day, take the first N bars' high/low as the
    opening range; long on break above, short on break below (intraday only).
    """
    out = df.copy()
    out["date"] = out.index.date
    sig = np.zeros(len(out))
    or_high = {}
    or_low = {}
    bar_count = {}
    dates = out["date"].values
    high = out["High"].values
    low = out["Low"].values
    close = out["Close"].values
    pos_today = {}
    for i in range(len(out)):
        d = dates[i]
        bar_count[d] = bar_count.get(d, 0) + 1
        if bar_count[d] <= opening_bars:
            or_high[d] = max(or_high.get(d, -np.inf), high[i])
            or_low[d] = min(or_low.get(d, np.inf), low[i])
            sig[i] = 0
            pos_today[d] = 0
            continue
        pos = pos_today.get(d, 0)
        if close[i] > or_high[d]:
            pos = 1
        elif close[i] < or_low[d]:
            pos = -1
        pos_today[d] = pos
        sig[i] = pos
    out["signal"] = sig
    out = out.drop(columns=["date"])
    return out


def intraday_supertrend(df: pd.DataFrame, period=10, mult=3.0) -> pd.DataFrame:
    out = df.copy()
    st = supertrend(out, period, mult)
    out["supertrend_dir"] = st
    out["signal"] = np.where(st > 0, 1, 0)   # long-only by default
    return out


def intraday_rsi_scalp(df: pd.DataFrame, period=7, low=35, high=65) -> pd.DataFrame:
    """Fast RSI scalper for 5m: buy dips in uptrend, exit on overbought."""
    out = df.copy()
    out["rsi"] = rsi(out["Close"], period)
    out["ema20"] = ema(out["Close"], 20)
    sig = np.zeros(len(out))
    pos = 0
    r = out["rsi"].values
    c = out["Close"].values
    e = out["ema20"].values
    for i in range(len(out)):
        if pos == 0 and r[i] < low and c[i] > e[i]:
            pos = 1
        elif pos == 1 and (r[i] > high or c[i] < e[i]):
            pos = 0
        sig[i] = pos
    out["signal"] = sig
    return out


INTRADAY_STRATEGIES = {
    "VWAP Momentum": intraday_vwap,
    "Opening Range Breakout": intraday_orb,
    "Supertrend (10,3)": intraday_supertrend,
    "RSI Scalper (7)": intraday_rsi_scalp,
}


def list_intraday() -> list[str]:
    return list(INTRADAY_STRATEGIES.keys())


def run_intraday(name: str, df: pd.DataFrame) -> pd.DataFrame:
    return INTRADAY_STRATEGIES[name](df)
