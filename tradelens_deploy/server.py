"""
server.py — TradeLens backend + PWA (self-contained, deploy-ready).
All engine modules live in this same folder, so no parent imports needed.

Local run:
    pip install -r requirements.txt
    python server.py

Online (Render.com): uses the PORT env var automatically. Start command:
    uvicorn server:app --host 0.0.0.0 --port $PORT

HONEST: read-only. No real orders are ever placed by this server.
Educational decision-support, not investment advice.
"""

from __future__ import annotations

import os
import pathlib

import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import data
import strategies
import backtest
import intraday
import astro
import pro_strategy
from greeks import compute_greeks, implied_vol
from angel_broker import AngelConfig, AngelBroker

HERE = pathlib.Path(__file__).resolve().parent
app = FastAPI(title="TradeLens API", version="1.0")

_BROKER: dict[str, AngelBroker] = {}
BARS_PER_DAY = {"5m": 75, "15m": 25, "1h": 6, "1d": 1}


class GreeksReq(BaseModel):
    S: float; K: float; dte: int; iv: float; rate: float = 6.5; type: str = "call"; lot: int = 75


class IVReq(BaseModel):
    price: float; S: float; K: float; dte: int; rate: float = 6.5; type: str = "call"


class AngelLogin(BaseModel):
    api_key: str; client_code: str; pin: str; totp_secret: str


@app.get("/api/symbols")
def api_symbols():
    return {"symbols": data.list_symbols()}


@app.get("/api/strategies")
def api_strategies():
    return {"daily": strategies.list_strategies(),
            "intraday": intraday.list_intraday(),
            "astro": astro.list_astro()}


@app.get("/api/pro")
def api_pro(symbol: str, period: str = "5y",
            stop: float = 3.5, target: float = 99.0, trail: bool = False):
    try:
        df = data.get_history(symbol, period=period)
    except Exception as e:
        raise HTTPException(400, f"data error: {e}")
    sig = pro_strategy.pro_signal(df)
    res = pro_strategy.backtest_with_stops(
        sig, atr_stop_mult=stop, atr_target_mult=target, trail=trail)
    return {
        "action": pro_strategy.latest_action(sig),
        "metrics": res["metrics"],
        "trades": res["trades"][-30:],
        "equity": res["equity"],
        "buyhold": res["buyhold"],
    }


@app.get("/api/astro/today")
def api_astro_today():
    return {"today": astro.today_snapshot(), "events": astro.upcoming_events()}


@app.get("/api/astro")
def api_astro(symbol: str, strategy: str, period: str = "5y"):
    try:
        df = data.get_history(symbol, period=period)
    except Exception as e:
        raise HTTPException(400, f"data error: {e}")
    sig = astro.run_astro(strategy, df)
    short = "(long/short)" in strategy
    bt = backtest.run_backtest(sig, allow_short=short)
    return {
        "action": strategies.latest_action(sig),
        "metrics": bt["metrics"],
        "trades": bt["trades"][-30:],
        "today": astro.today_snapshot(),
    }


@app.get("/api/signal")
def api_signal(symbol: str, strategy: str, period: str = "1y"):
    try:
        df = data.get_history(symbol, period=period)
    except Exception as e:
        raise HTTPException(400, f"data error: {e}")
    sig = strategies.run_strategy(strategy, df)
    out = {
        "symbol": symbol, "strategy": strategy,
        "last_close": round(float(df["Close"].iloc[-1]), 2),
        "prev_close": round(float(df["Close"].iloc[-2]), 2),
        "action": strategies.latest_action(sig),
        "rsi": round(float(sig["rsi"].iloc[-1]), 1) if "rsi" in sig.columns else None,
    }
    tail = df["Close"].tail(60)
    out["spark"] = [round(float(x), 2) for x in tail.values]
    return out


@app.get("/api/backtest")
def api_backtest(symbol: str, strategy: str, period: str = "5y", short: bool = False):
    try:
        df = data.get_history(symbol, period=period)
    except Exception as e:
        raise HTTPException(400, f"data error: {e}")
    sig = strategies.run_strategy(strategy, df)
    bt = backtest.run_backtest(sig, allow_short=short)
    eq = bt["df"]["equity"]; bh = bt["df"]["buyhold"]
    step = max(1, len(eq) // 120)
    return {
        "metrics": bt["metrics"],
        "equity_dates": [str(d.date()) for d in eq.index[::step]],
        "equity": [round(float(x), 0) for x in eq.values[::step]],
        "buyhold": [round(float(x), 0) for x in bh.values[::step]],
        "trades": bt["trades"][-50:],
    }


@app.get("/api/intraday")
def api_intraday(symbol: str, strategy: str, tf: str = "15m", short: bool = True):
    import yfinance as yf
    ticker = data.SYMBOLS.get(symbol, symbol)
    period = "60d" if tf in ("5m", "15m") else "180d"
    df = yf.download(ticker, period=period, interval=tf, auto_adjust=True, progress=False)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df[["Open", "High", "Low", "Close", "Volume"]].dropna()
    if len(df) < 30:
        raise HTTPException(400, "not enough intraday data")
    sig = intraday.run_intraday(strategy, df)
    bpd = BARS_PER_DAY.get(tf, 25)
    bt = backtest.run_backtest(sig, allow_short=short, periods_per_year=bpd * 252)
    return {"action": strategies.latest_action(sig), "metrics": bt["metrics"], "trades": bt["trades"][-30:]}


@app.post("/api/greeks")
def api_greeks(r: GreeksReq):
    T = max(r.dte, 0) / 365
    g = compute_greeks(r.S, r.K, T, r.rate / 100, r.iv / 100, r.type)
    return {
        "price": round(g.price, 2), "delta": round(g.delta, 4), "gamma": round(g.gamma, 6),
        "theta_per_day": round(g.theta_per_day, 2), "vega_per_1pct": round(g.vega_per_1pct, 2),
        "rho_per_1pct": round(g.rho_per_1pct, 2),
        "lot_premium": round(g.price * r.lot, 0), "lot_theta": round(g.theta_per_day * r.lot, 0),
    }


@app.post("/api/iv")
def api_iv(r: IVReq):
    T = max(r.dte, 0) / 365
    iv = implied_vol(r.price, r.S, r.K, T, r.rate / 100, r.type)
    return {"iv_pct": round(iv * 100, 2) if iv else None}


@app.post("/api/angel/login")
def api_angel_login(r: AngelLogin):
    cfg = AngelConfig(api_key=r.api_key, client_code=r.client_code, pin=r.pin, totp_secret=r.totp_secret)
    b = AngelBroker(cfg); ok, msg = b.login()
    if ok:
        _BROKER["b"] = b
    return {"ok": ok, "message": msg}


@app.get("/api/angel/greeks")
def api_angel_greeks(name: str, expiry: str):
    b = _BROKER.get("b")
    if not b:
        raise HTTPException(401, "Not logged in to Angel One")
    try:
        return {"rows": b.option_greeks(name, expiry).to_dict(orient="records")}
    except Exception as e:
        raise HTTPException(400, str(e))


@app.get("/api/angel/pcr")
def api_angel_pcr():
    b = _BROKER.get("b")
    if not b:
        raise HTTPException(401, "Not logged in to Angel One")
    try:
        return {"rows": b.put_call_ratio().to_dict(orient="records")}
    except Exception as e:
        raise HTTPException(400, str(e))


@app.get("/")
def index():
    return FileResponse(str(HERE / "index.html"))


@app.get("/manifest.json")
def manifest():
    return FileResponse(str(HERE / "manifest.json"), media_type="application/manifest+json")


@app.get("/sw.js")
def service_worker():
    return FileResponse(str(HERE / "sw.js"), media_type="application/javascript")


app.mount("/static", StaticFiles(directory=str(HERE)), name="static")


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8000"))
    print(f"\n  TradeLens running:  http://localhost:{port}\n")
    uvicorn.run(app, host="0.0.0.0", port=port)
