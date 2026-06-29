"""
pro_strategy.py — A realistic "professional-style" strategy + event-driven
backtest with STOP-LOSS and TAKE-PROFIT (ATR based).

Philosophy (what good traders actually do — NOT magic):
  * Trade WITH the trend, not against it  (EMA50 > EMA200 = uptrend filter)
  * Only enter on momentum confirmation    (pullback then up, RSI not extreme)
  * ALWAYS use a stop-loss                  (cap the loss on every trade)
  * Let winners run with a trailing stop    (profit > loss on average)
  * Skip dead/choppy markets                (ADX-style volatility filter)

This does NOT guarantee profit and will NOT win every trade. Nobody can.
The goal is a sensible win-rate + a profit factor > 1 on real data, shown
honestly via backtest (fees + slippage + next-bar fills + stops).

Signal convention stays compatible: the function returns a df with a
'signal' column (+1 long / 0 flat) so it also works in the simple engine,
but the REAL evaluation uses backtest_with_stops() below.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from strategies import ema, rsi, atr


def _adx(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Average Directional Index — measures trend strength (filter chop)."""
    high, low, close = df["High"], df["Low"], df["Close"]
    up = high.diff()
    down = -low.diff()
    plus_dm = np.where((up > down) & (up > 0), up, 0.0)
    minus_dm = np.where((down > up) & (down > 0), down, 0.0)
    tr = pd.concat([(high - low),
                    (high - close.shift()).abs(),
                    (low - close.shift()).abs()], axis=1).max(axis=1)
    atr_ = tr.ewm(alpha=1 / period, adjust=False).mean()
    plus_di = 100 * pd.Series(plus_dm, index=df.index).ewm(alpha=1 / period, adjust=False).mean() / atr_
    minus_di = 100 * pd.Series(minus_dm, index=df.index).ewm(alpha=1 / period, adjust=False).mean() / atr_
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    return dx.ewm(alpha=1 / period, adjust=False).mean().fillna(0)


def pro_signal(df: pd.DataFrame) -> pd.DataFrame:
    """
    Entry rules (LONG only — index trading from the long side is statistically
    friendlier over the long run):
        - Uptrend:     EMA50 > EMA200
        - Trend strong: ADX > 20
        - Momentum:    Close > EMA20  AND  45 < RSI < 70 (not overbought)
    Exit is handled by the stop/target engine, but we also flatten if the
    uptrend breaks (EMA50 < EMA200).
    """
    out = df.copy()
    out["ema20"] = ema(out["Close"], 20)
    out["ema50"] = ema(out["Close"], 50)
    out["ema200"] = ema(out["Close"], 200)
    out["rsi"] = rsi(out["Close"], 14)
    out["atr"] = atr(out, 14)
    out["adx"] = _adx(out, 14)

    uptrend = out["ema50"] > out["ema200"]
    strong = out["adx"] > 20
    momentum = (out["Close"] > out["ema20"]) & (out["rsi"] > 45) & (out["rsi"] < 70)

    out["want_long"] = (uptrend & strong & momentum).astype(int)
    out["trend_ok"] = uptrend.astype(int)
    # simple compatibility signal (engine #1): long when want_long
    out["signal"] = out["want_long"]
    return out


def backtest_with_stops(
    sig_df: pd.DataFrame,
    *,
    initial_capital: float = 100_000.0,
    atr_stop_mult: float = 3.5,     # wide stop -> survive normal index noise
    atr_target_mult: float = 99.0,  # effectively no fixed cap -> let winners run
    trail: bool = False,            # exit on trend-break instead of a tight trail
    cost_pct: float = 0.0006,
    slippage_pct: float = 0.0003,
    periods_per_year: int = 252,
) -> dict:
    """
    Event-driven long-only backtest with ATR stop-loss + take-profit + trailing.
    Enters next bar's open after a 'want_long' signal; exits on stop, target,
    or trend-break. Realistic costs on entry+exit.
    """
    df = sig_df.copy().reset_index()
    date_col = df.columns[0]
    o = df["Open"].values
    h = df["High"].values
    l = df["Low"].values
    c = df["Close"].values
    a = df["atr"].values
    want = df["want_long"].values
    trend_ok = df["trend_ok"].values
    dates = df[date_col].values

    cost = cost_pct + slippage_pct
    cash = initial_capital
    equity_curve = []
    in_pos = False
    entry = stop = target = 0.0
    entry_date = None
    units = 0.0
    trades = []

    for i in range(len(df)):
        price = c[i]

        if in_pos:
            # update trailing stop
            if trail:
                new_stop = h[i] - atr_stop_mult * a[i]
                stop = max(stop, new_stop)
            exit_price = None
            reason = None
            # stop hit (intrabar low)
            if l[i] <= stop:
                exit_price = stop
                reason = "stop"
            # target hit (intrabar high)
            elif h[i] >= target:
                exit_price = target
                reason = "target"
            # trend break -> exit at close
            elif trend_ok[i] == 0:
                exit_price = price
                reason = "trend_exit"

            if exit_price is not None:
                gross = (exit_price / entry - 1.0)
                pnl = gross - 2 * cost
                cash = cash * (1 + pnl)
                trades.append({
                    "entry_date": str(pd.Timestamp(entry_date).date()),
                    "exit_date": str(pd.Timestamp(dates[i]).date()),
                    "direction": "LONG",
                    "entry": round(float(entry), 2),
                    "exit": round(float(exit_price), 2),
                    "reason": reason,
                    "pnl_pct": round(float(pnl), 4),
                })
                in_pos = False

        # entry (next bar after signal) — we approximate with current bar open
        if (not in_pos) and i > 0 and want[i - 1] == 1 and a[i] > 0:
            entry = o[i]
            stop = entry - atr_stop_mult * a[i]
            target = entry + atr_target_mult * a[i]
            entry_date = dates[i]
            in_pos = True

        equity_curve.append(cash if not in_pos else cash * (price / entry))

    # close any open trade at the end
    if in_pos:
        gross = (c[-1] / entry - 1.0)
        pnl = gross - 2 * cost
        cash = cash * (1 + pnl)
        trades.append({
            "entry_date": str(pd.Timestamp(entry_date).date()),
            "exit_date": str(pd.Timestamp(dates[-1]).date()),
            "direction": "LONG", "entry": round(float(entry), 2),
            "exit": round(float(c[-1]), 2), "reason": "eod",
            "pnl_pct": round(float(pnl), 4), "open_at_end": True,
        })

    eq = pd.Series(equity_curve, index=df[date_col])
    bh = (df["Close"] / df["Close"].iloc[0]) * initial_capital
    bh.index = df[date_col]

    roll_max = eq.cummax()
    dd = (eq / roll_max - 1.0)
    daily = eq.pct_change().fillna(0)
    sharpe = (np.sqrt(periods_per_year) * daily.mean() / daily.std()) if daily.std() > 0 else 0.0

    if trades:
        wins = [t for t in trades if t["pnl_pct"] > 0]
        win_rate = len(wins) / len(trades)
        gross_win = sum(t["pnl_pct"] for t in wins)
        gross_loss = abs(sum(t["pnl_pct"] for t in trades if t["pnl_pct"] <= 0))
        pf = gross_win / gross_loss if gross_loss > 0 else float("inf")
        avg_win = np.mean([t["pnl_pct"] for t in wins]) if wins else 0
        losses = [t for t in trades if t["pnl_pct"] <= 0]
        avg_loss = np.mean([t["pnl_pct"] for t in losses]) if losses else 0
    else:
        win_rate = pf = avg_win = avg_loss = 0.0

    n_years = max(len(df) / periods_per_year, 1e-9)
    cagr = (eq.iloc[-1] / initial_capital) ** (1 / n_years) - 1

    metrics = {
        "Net Return %": round((eq.iloc[-1] / initial_capital - 1) * 100, 2),
        "Buy & Hold %": round((bh.iloc[-1] / initial_capital - 1) * 100, 2),
        "CAGR %": round(cagr * 100, 2),
        "Sharpe (ann.)": round(sharpe, 2),
        "Max Drawdown %": round(dd.min() * 100, 2),
        "Total Trades": len(trades),
        "Win Rate %": round(win_rate * 100, 1),
        "Avg Win %": round(avg_win * 100, 2),
        "Avg Loss %": round(avg_loss * 100, 2),
        "Profit Factor": round(pf, 2) if pf != float("inf") else "inf",
        "Final Equity": round(eq.iloc[-1], 0),
    }

    step = max(1, len(eq) // 120)
    return {
        "metrics": metrics,
        "trades": trades,
        "equity": [round(float(x), 0) for x in eq.values[::step]],
        "buyhold": [round(float(x), 0) for x in bh.values[::step]],
        "equity_dates": [str(pd.Timestamp(d).date()) for d in eq.index[::step]],
    }


def latest_action(sig_df: pd.DataFrame) -> str:
    w = sig_df["want_long"].values
    trend = sig_df["trend_ok"].values
    if len(w) < 2:
        return "WAIT"
    if w[-1] == 1 and w[-2] == 0:
        return "BUY (setup triggered)"
    if w[-1] == 1:
        return "HOLD LONG (in trend)"
    if trend[-1] == 0:
        return "STAY OUT (no uptrend)"
    return "WAIT (no setup yet)"


if __name__ == "__main__":
    import data
    for sym in ["Nifty 50", "Sensex"]:
        df = data.get_history(sym, period="5y")
        sig = pro_signal(df)
        res = backtest_with_stops(sig)
        m = res["metrics"]
        print(f"{sym:10s} Net {m['Net Return %']}% | B&H {m['Buy & Hold %']}% | "
              f"Trades {m['Total Trades']} | Win {m['Win Rate %']}% | PF {m['Profit Factor']} | "
              f"Sharpe {m['Sharpe (ann.)']} | MaxDD {m['Max Drawdown %']}%")
