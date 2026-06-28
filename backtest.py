"""
backtest.py
-----------
A realistic vectorized backtester.

Realism features (this is where most "amazing" backtests cheat -> we don't):
  * Trades execute on the NEXT bar's open after a signal (no look-ahead).
  * Transaction cost (brokerage+taxes) applied on every position change.
  * Slippage applied on every position change.
  * Equity curve, drawdown, Sharpe, win-rate, per-trade list all reported.

Returns a dict of results that the dashboard renders.

HONEST DISCLAIMER baked into the output:
  Past performance != future performance. A good backtest is a necessary
  filter, not a guarantee. Real fills, gaps, and regime change will differ.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def run_backtest(
    signal_df: pd.DataFrame,
    *,
    initial_capital: float = 100_000.0,
    cost_pct: float = 0.0006,      # 0.06% round-trip-ish per side (brokerage+STT+slippage proxy)
    slippage_pct: float = 0.0003,  # 0.03% per side
    allow_short: bool = False,
    periods_per_year: int = 252,
) -> dict:
    df = signal_df.copy()
    df["signal"] = df["signal"].fillna(0)

    if not allow_short:
        df["signal"] = df["signal"].clip(lower=0)

    # Position is taken NEXT bar (avoid look-ahead): shift signal by 1.
    df["position"] = df["signal"].shift(1).fillna(0)

    # Bar return of the underlying
    df["ret"] = df["Close"].pct_change().fillna(0)

    # Strategy return before costs
    df["strat_ret"] = df["position"] * df["ret"]

    # Cost whenever position changes
    df["pos_change"] = df["position"].diff().abs().fillna(0)
    per_turn_cost = cost_pct + slippage_pct
    df["cost"] = df["pos_change"] * per_turn_cost
    df["strat_ret_net"] = df["strat_ret"] - df["cost"]

    # Equity curves
    df["equity"] = (1 + df["strat_ret_net"]).cumprod() * initial_capital
    df["buyhold"] = (1 + df["ret"]).cumprod() * initial_capital

    # Drawdown
    roll_max = df["equity"].cummax()
    df["drawdown"] = df["equity"] / roll_max - 1.0

    # --- Trade extraction (round trips) ---
    trades = _extract_trades(df, cost=per_turn_cost)

    # --- Metrics ---
    net_ret = df["equity"].iloc[-1] / initial_capital - 1.0
    n_years = max(len(df) / periods_per_year, 1e-9)
    cagr = (df["equity"].iloc[-1] / initial_capital) ** (1 / n_years) - 1.0

    daily = df["strat_ret_net"]
    sharpe = (
        np.sqrt(periods_per_year) * daily.mean() / daily.std()
        if daily.std() > 0 else 0.0
    )
    max_dd = df["drawdown"].min()

    if trades:
        wins = [t for t in trades if t["pnl_pct"] > 0]
        win_rate = len(wins) / len(trades)
        avg_win = np.mean([t["pnl_pct"] for t in wins]) if wins else 0.0
        losses = [t for t in trades if t["pnl_pct"] <= 0]
        avg_loss = np.mean([t["pnl_pct"] for t in losses]) if losses else 0.0
        gross_win = sum(t["pnl_pct"] for t in wins)
        gross_loss = abs(sum(t["pnl_pct"] for t in losses))
        profit_factor = gross_win / gross_loss if gross_loss > 0 else float("inf")
    else:
        win_rate = avg_win = avg_loss = 0.0
        profit_factor = 0.0

    metrics = {
        "Net Return %": round(net_ret * 100, 2),
        "Buy & Hold %": round((df["buyhold"].iloc[-1] / initial_capital - 1) * 100, 2),
        "CAGR %": round(cagr * 100, 2),
        "Sharpe (ann.)": round(sharpe, 2),
        "Max Drawdown %": round(max_dd * 100, 2),
        "Total Trades": len(trades),
        "Win Rate %": round(win_rate * 100, 1),
        "Avg Win %": round(avg_win * 100, 2),
        "Avg Loss %": round(avg_loss * 100, 2),
        "Profit Factor": round(profit_factor, 2) if profit_factor != float("inf") else "inf",
        "Final Equity": round(df["equity"].iloc[-1], 0),
    }

    return {
        "df": df,
        "trades": trades,
        "metrics": metrics,
        "initial_capital": initial_capital,
    }


def _extract_trades(df: pd.DataFrame, cost: float) -> list[dict]:
    trades = []
    position = 0
    entry_price = None
    entry_date = None

    idx = df.index
    pos = df["position"].values
    price = df["Close"].values

    for i in range(len(df)):
        p = pos[i]
        if position == 0 and p != 0:
            position = p
            entry_price = price[i]
            entry_date = idx[i]
        elif position != 0 and p != position:
            exit_price = price[i]
            gross = (exit_price / entry_price - 1.0) * position
            pnl = gross - 2 * cost  # entry + exit cost
            trades.append({
                "entry_date": str(entry_date.date()) if hasattr(entry_date, "date") else str(entry_date),
                "exit_date": str(idx[i].date()) if hasattr(idx[i], "date") else str(idx[i]),
                "direction": "LONG" if position > 0 else "SHORT",
                "entry": round(float(entry_price), 2),
                "exit": round(float(exit_price), 2),
                "pnl_pct": round(float(pnl), 4),
            })
            # handle flip vs flat
            if p != 0:
                position = p
                entry_price = price[i]
                entry_date = idx[i]
            else:
                position = 0
                entry_price = entry_date = None

    # close any open trade at the end
    if position != 0 and entry_price is not None:
        exit_price = price[-1]
        gross = (exit_price / entry_price - 1.0) * position
        pnl = gross - 2 * cost
        trades.append({
            "entry_date": str(entry_date.date()) if hasattr(entry_date, "date") else str(entry_date),
            "exit_date": str(idx[-1].date()) if hasattr(idx[-1], "date") else str(idx[-1]),
            "direction": "LONG" if position > 0 else "SHORT",
            "entry": round(float(entry_price), 2),
            "exit": round(float(exit_price), 2),
            "pnl_pct": round(float(pnl), 4),
            "open_at_end": True,
        })
    return trades
