"""
angel_broker.py
---------------
Angel One SmartAPI wrapper for:
  * login (session)
  * intraday candle data (1m / 5m / 15m)
  * live option-chain Greeks (Delta, Gamma, Theta, Vega, IV) via optionGreek()
  * OI build-up + Put-Call Ratio (PCR)
  * instrument-token lookup (downloads Angel's scrip master once)

SAFETY / HONESTY:
  - This module ONLY READS data + computes signals. It does NOT place orders.
    (You wanted manual trading — so no order functions are exposed here.)
  - If credentials are missing or the network blocks SmartAPI, every function
    fails *gracefully* and the dashboard falls back to yfinance/Black-Scholes.
  - Never hardcode keys in code. Use the sidebar inputs or environment vars:
        ANGEL_API_KEY, ANGEL_CLIENT_CODE, ANGEL_PIN, ANGEL_TOTP_SECRET

Docs basis: smartapi-python v1.5.5 (generateSession, getCandleData,
optionGreek, putCallRatio, oIBuildup).
"""

from __future__ import annotations

import datetime as dt
import io
import os
from dataclasses import dataclass

import pandas as pd
import requests

SCRIP_MASTER_URL = (
    "https://margincalculator.angelbroking.com/OpenAPI_File/files/OpenAPIScripMaster.json"
)

INTERVAL_MAP = {
    "1m": "ONE_MINUTE",
    "3m": "THREE_MINUTE",
    "5m": "FIVE_MINUTE",
    "15m": "FIFTEEN_MINUTE",
    "30m": "THIRTY_MINUTE",
    "1h": "ONE_HOUR",
    "1d": "ONE_DAY",
}


@dataclass
class AngelConfig:
    api_key: str = ""
    client_code: str = ""
    pin: str = ""
    totp_secret: str = ""

    @classmethod
    def from_env(cls) -> "AngelConfig":
        return cls(
            api_key=os.getenv("ANGEL_API_KEY", ""),
            client_code=os.getenv("ANGEL_CLIENT_CODE", ""),
            pin=os.getenv("ANGEL_PIN", ""),
            totp_secret=os.getenv("ANGEL_TOTP_SECRET", ""),
        )

    def is_complete(self) -> bool:
        return all([self.api_key, self.client_code, self.pin, self.totp_secret])


class AngelBroker:
    """Thin, read-only wrapper. Construct, then call .login()."""

    def __init__(self, cfg: AngelConfig):
        self.cfg = cfg
        self.smart = None
        self.connected = False
        self._scrip: pd.DataFrame | None = None

    # -------------------------------------------------- session
    def login(self) -> tuple[bool, str]:
        if not self.cfg.is_complete():
            return False, "Missing credentials (api_key/client/pin/totp_secret)."
        try:
            from SmartApi import SmartConnect
            import pyotp
        except Exception as e:  # pragma: no cover
            return False, f"smartapi-python/pyotp not installed: {e}"
        try:
            self.smart = SmartConnect(api_key=self.cfg.api_key)
            otp = pyotp.TOTP(self.cfg.totp_secret).now()
            data = self.smart.generateSession(self.cfg.client_code, self.cfg.pin, otp)
            if not data or not data.get("status"):
                msg = data.get("message") if isinstance(data, dict) else "unknown"
                return False, f"Login failed: {msg}"
            self.connected = True
            return True, "Login OK"
        except Exception as e:
            return False, f"Login error: {type(e).__name__}: {e}"

    # -------------------------------------------------- scrip master
    def _load_scrip(self) -> pd.DataFrame:
        if self._scrip is not None:
            return self._scrip
        r = requests.get(SCRIP_MASTER_URL, timeout=30)
        r.raise_for_status()
        df = pd.DataFrame(r.json())
        self._scrip = df
        return df

    def find_token(self, exchange: str, tradingsymbol: str) -> str | None:
        """Look up symboltoken for an exact tradingsymbol on an exchange."""
        df = self._load_scrip()
        m = df[(df["exch_seg"] == exchange) &
               (df["symbol"].str.upper() == tradingsymbol.upper())]
        if m.empty:
            return None
        return str(m.iloc[0]["token"])

    def index_token(self, name: str) -> tuple[str, str] | None:
        """Return (exchange, token) for an index spot."""
        mapping = {
            "Nifty 50": ("NSE", "Nifty 50"),
            "Bank Nifty": ("NSE", "Nifty Bank"),
            "Sensex": ("BSE", "SENSEX"),
        }
        if name not in mapping:
            return None
        exch, sym = mapping[name]
        df = self._load_scrip()
        m = df[(df["exch_seg"] == exch) & (df["name"].str.upper() == sym.upper())]
        if m.empty:
            return None
        return exch, str(m.iloc[0]["token"])

    # -------------------------------------------------- candles (intraday)
    def candles(self, exchange: str, token: str, interval: str,
                lookback_days: int = 5) -> pd.DataFrame:
        if not self.connected:
            raise RuntimeError("Not logged in.")
        ang_int = INTERVAL_MAP.get(interval, "FIVE_MINUTE")
        to = dt.datetime.now()
        frm = to - dt.timedelta(days=lookback_days)
        params = {
            "exchange": exchange,
            "symboltoken": token,
            "interval": ang_int,
            "fromdate": frm.strftime("%Y-%m-%d %H:%M"),
            "todate": to.strftime("%Y-%m-%d %H:%M"),
        }
        resp = self.smart.getCandleData(params)
        if not resp or not resp.get("status") or not resp.get("data"):
            raise RuntimeError(f"No candle data: {resp.get('message') if resp else 'empty'}")
        df = pd.DataFrame(resp["data"],
                          columns=["Datetime", "Open", "High", "Low", "Close", "Volume"])
        df["Datetime"] = pd.to_datetime(df["Datetime"])
        df = df.set_index("Datetime")
        return df.astype({"Open": float, "High": float, "Low": float,
                          "Close": float, "Volume": float})

    # -------------------------------------------------- option greeks (live)
    def option_greeks(self, name: str, expiry: str) -> pd.DataFrame:
        """
        name   : 'NIFTY' / 'BANKNIFTY' / 'SENSEX'
        expiry : 'DDMMMYYYY' e.g. '03JUL2025'  (as Angel expects)
        Returns one row per strike/type with delta/gamma/theta/vega/iv.
        """
        if not self.connected:
            raise RuntimeError("Not logged in.")
        params = {"name": name.upper(), "expirydate": expiry.upper()}
        resp = self.smart.optionGreek(params)
        if not resp or not resp.get("status") or not resp.get("data"):
            raise RuntimeError(f"No greeks: {resp.get('message') if resp else 'empty'}")
        df = pd.DataFrame(resp["data"])
        # normalise numeric columns when present
        for c in ["delta", "gamma", "theta", "vega", "impliedVolatility",
                  "strikePrice", "tradeVolume"]:
            if c in df.columns:
                df[c] = pd.to_numeric(df[c], errors="coerce")
        return df

    # -------------------------------------------------- OI / PCR sentiment
    def put_call_ratio(self) -> pd.DataFrame:
        if not self.connected:
            raise RuntimeError("Not logged in.")
        resp = self.smart.putCallRatio()
        if not resp or not resp.get("status"):
            raise RuntimeError(f"PCR failed: {resp.get('message') if resp else 'empty'}")
        return pd.DataFrame(resp.get("data", []))

    def oi_buildup(self, expiry_type="NEAR", datatype="PercentOIGainers") -> pd.DataFrame:
        if not self.connected:
            raise RuntimeError("Not logged in.")
        params = {"expirytype": expiry_type, "datatype": datatype}
        resp = self.smart.oIBuildup(params)
        if not resp or not resp.get("status"):
            raise RuntimeError(f"OI buildup failed: {resp.get('message') if resp else 'empty'}")
        return pd.DataFrame(resp.get("data", []))


def quick_login_from_inputs(api_key, client_code, pin, totp_secret):
    cfg = AngelConfig(api_key=api_key, client_code=client_code,
                      pin=pin, totp_secret=totp_secret)
    b = AngelBroker(cfg)
    ok, msg = b.login()
    return (b if ok else None), msg
