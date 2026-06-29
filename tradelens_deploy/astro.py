"""
astro.py — Financial Astrology signals (HONEST version).
--------------------------------------------------------
Computes REAL astronomical events using PyEphem and turns common
"financial astrology" claims into testable buy/sell signals.

IMPORTANT HONESTY NOTE (read this):
  There is NO scientific or robust statistical evidence that planetary
  positions predict markets. This module exists so you can SEE FOR YOURSELF,
  via backtest, whether these classic claims held any edge on real data.
  Treat every result with heavy skepticism. Past patterns (even if found)
  are very likely coincidence and will not reliably repeat.

Signals implemented (each is a well-known astro-trading claim):
  1. Lunar phase   : bullish from New Moon -> Full Moon, bearish Full -> New
                     (the "lunar cycle" trading folklore)
  2. Mercury retro : flat/cautious during Mercury retrograde (popular claim)
  3. Combined      : lunar signal, but go flat during Mercury retrograde

Signal convention (same as rest of app): +1 long, 0 flat, -1 short.
"""

from __future__ import annotations

import datetime as dt

import ephem
import numpy as np
import pandas as pd


# --------------------------------------------------------------------------
# Core astronomical helpers
# --------------------------------------------------------------------------
def moon_phase_fraction(date: dt.date) -> float:
    """Illuminated fraction of the moon, 0 (new) .. 1 (full)."""
    m = ephem.Moon(ephem.Date(date))
    return float(m.phase) / 100.0


def moon_age_days(date: dt.date) -> float:
    """Days since last new moon (0..~29.53)."""
    d = ephem.Date(date)
    prev_new = ephem.previous_new_moon(d)
    return float(d - prev_new)


def is_waxing(date: dt.date) -> bool:
    """True if moon is waxing (New -> Full): classic 'bullish' half."""
    age = moon_age_days(date)
    return age < 14.765  # half of synodic month


def mercury_retrograde(date: dt.date) -> bool:
    """
    Approximate Mercury retrograde detection: compare ecliptic longitude
    today vs ~2 days later; if it decreases, Mercury appears retrograde.
    """
    d0 = ephem.Date(date)
    d1 = ephem.Date(date + dt.timedelta(days=2))
    m0 = ephem.Mercury(d0)
    m1 = ephem.Mercury(d1)
    lon0 = float(m0.hlong)
    lon1 = float(m1.hlong)
    # heliocentric longitude won't show retro; use geocentric ecliptic lon
    from math import degrees
    e0 = ephem.Ecliptic(ephem.Mercury(d0))
    e1 = ephem.Ecliptic(ephem.Mercury(d1))
    lon0 = degrees(float(e0.lon))
    lon1 = degrees(float(e1.lon))
    diff = (lon1 - lon0 + 540) % 360 - 180   # signed shortest delta
    return diff < 0


# --------------------------------------------------------------------------
# Signal strategies (operate on a price DataFrame indexed by date)
# --------------------------------------------------------------------------
def _dates(df: pd.DataFrame) -> list[dt.date]:
    return [ts.date() if hasattr(ts, "date") else ts for ts in df.index]


def astro_lunar(df: pd.DataFrame) -> pd.DataFrame:
    """Long while waxing (New->Full), flat while waning."""
    out = df.copy()
    sig = []
    for d in _dates(out):
        sig.append(1 if is_waxing(d) else 0)
    out["moon_frac"] = [moon_phase_fraction(d) for d in _dates(out)]
    out["signal"] = sig
    return out


def astro_lunar_short(df: pd.DataFrame) -> pd.DataFrame:
    """Long waxing, SHORT waning (more aggressive lunar claim)."""
    out = df.copy()
    out["signal"] = [1 if is_waxing(d) else -1 for d in _dates(out)]
    out["moon_frac"] = [moon_phase_fraction(d) for d in _dates(out)]
    return out


def astro_mercury(df: pd.DataFrame) -> pd.DataFrame:
    """Flat during Mercury retrograde, long otherwise."""
    out = df.copy()
    retro = [mercury_retrograde(d) for d in _dates(out)]
    out["mercury_retro"] = retro
    out["signal"] = [0 if r else 1 for r in retro]
    return out


def astro_combined(df: pd.DataFrame) -> pd.DataFrame:
    """Lunar long-signal, but force FLAT during Mercury retrograde."""
    out = df.copy()
    ds = _dates(out)
    wax = [is_waxing(d) for d in ds]
    retro = [mercury_retrograde(d) for d in ds]
    out["moon_frac"] = [moon_phase_fraction(d) for d in ds]
    out["mercury_retro"] = retro
    out["signal"] = [0 if r else (1 if w else 0) for w, r in zip(wax, retro)]
    return out


ASTRO_STRATEGIES = {
    "Lunar Cycle (long waxing)": astro_lunar,
    "Lunar Cycle (long/short)": astro_lunar_short,
    "Mercury Retrograde (avoid)": astro_mercury,
    "Lunar + Mercury Combined": astro_combined,
}


def list_astro() -> list[str]:
    return list(ASTRO_STRATEGIES.keys())


def run_astro(name: str, df: pd.DataFrame) -> pd.DataFrame:
    return ASTRO_STRATEGIES[name](df)


# --------------------------------------------------------------------------
# Upcoming astro events (for display)
# --------------------------------------------------------------------------
def upcoming_events(days_ahead: int = 45) -> list[dict]:
    """Next new/full moons and current Mercury retrograde status."""
    today = dt.date.today()
    d = ephem.Date(today)
    events = []
    nm = ephem.next_new_moon(d)
    fm = ephem.next_full_moon(d)
    events.append({"date": str(ephem.Date(nm)).split()[0], "event": "🌑 New Moon",
                   "note": "lunar-bullish phase begins (folklore)"})
    events.append({"date": str(ephem.Date(fm)).split()[0], "event": "🌕 Full Moon",
                   "note": "lunar-bearish phase begins (folklore)"})
    retro_now = mercury_retrograde(today)
    events.append({"date": str(today), "event": "☿ Mercury",
                   "note": "RETROGRADE now (caution claim)" if retro_now else "direct (normal)"})
    events.sort(key=lambda x: x["date"])
    return events


def today_snapshot() -> dict:
    today = dt.date.today()
    return {
        "moon_illumination_pct": round(moon_phase_fraction(today) * 100, 1),
        "moon_age_days": round(moon_age_days(today), 1),
        "phase": "Waxing 🌒 (bullish folklore)" if is_waxing(today) else "Waning 🌖 (bearish folklore)",
        "mercury_retrograde": mercury_retrograde(today),
    }


if __name__ == "__main__":
    print("Today:", today_snapshot())
    print("Upcoming:")
    for e in upcoming_events():
        print(" ", e)
