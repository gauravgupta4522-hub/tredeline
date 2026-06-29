"""
greeks.py
---------
Black-Scholes option pricing + Greeks (Delta, Gamma, Theta, Vega, Rho)
and implied volatility (IV) solver.

This is the standard textbook Black-Scholes-Merton model. It is what most
option analytics tools use under the hood. Useful for understanding how an
option position behaves, but real markets have skew/smile that a single-vol
model does not fully capture.

Conventions:
  S     = spot price
  K     = strike
  T     = time to expiry in YEARS (e.g. 7 days = 7/365)
  r     = risk-free rate (annual, decimal). India ~ 0.065
  sigma = volatility (annual, decimal). e.g. 0.15 = 15%
  Theta returned PER DAY (more intuitive than per year).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from scipy.stats import norm


def _d1_d2(S, K, T, r, sigma):
    if T <= 0 or sigma <= 0:
        # degenerate; return large/small so N(d) saturates
        return (math.inf if S > K else -math.inf), (math.inf if S > K else -math.inf)
    d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    return d1, d2


def bs_price(S, K, T, r, sigma, option_type="call") -> float:
    if T <= 0:
        # intrinsic value at expiry
        return max(0.0, S - K) if option_type == "call" else max(0.0, K - S)
    d1, d2 = _d1_d2(S, K, T, r, sigma)
    if option_type == "call":
        return S * norm.cdf(d1) - K * math.exp(-r * T) * norm.cdf(d2)
    else:
        return K * math.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1)


@dataclass
class Greeks:
    price: float
    delta: float
    gamma: float
    theta_per_day: float
    vega_per_1pct: float
    rho_per_1pct: float


def compute_greeks(S, K, T, r, sigma, option_type="call") -> Greeks:
    price = bs_price(S, K, T, r, sigma, option_type)

    if T <= 0 or sigma <= 0:
        delta = (1.0 if S > K else 0.0) if option_type == "call" else (-1.0 if S < K else 0.0)
        return Greeks(price, delta, 0.0, 0.0, 0.0, 0.0)

    d1, d2 = _d1_d2(S, K, T, r, sigma)
    pdf_d1 = norm.pdf(d1)
    sqrtT = math.sqrt(T)

    if option_type == "call":
        delta = norm.cdf(d1)
        theta_year = (-(S * pdf_d1 * sigma) / (2 * sqrtT)
                      - r * K * math.exp(-r * T) * norm.cdf(d2))
        rho = K * T * math.exp(-r * T) * norm.cdf(d2)
    else:
        delta = norm.cdf(d1) - 1.0
        theta_year = (-(S * pdf_d1 * sigma) / (2 * sqrtT)
                      + r * K * math.exp(-r * T) * norm.cdf(-d2))
        rho = -K * T * math.exp(-r * T) * norm.cdf(-d2)

    gamma = pdf_d1 / (S * sigma * sqrtT)
    vega = S * pdf_d1 * sqrtT            # per 1.0 (100%) change in vol
    return Greeks(
        price=price,
        delta=delta,
        gamma=gamma,
        theta_per_day=theta_year / 365.0,
        vega_per_1pct=vega / 100.0,      # per 1% change in vol
        rho_per_1pct=rho / 100.0,
    )


def implied_vol(market_price, S, K, T, r, option_type="call",
                tol=1e-5, max_iter=100) -> float | None:
    """
    Solve for IV using bisection (robust, no derivative needed).
    Returns annualized vol as decimal, or None if it can't be found.
    """
    if T <= 0 or market_price <= 0:
        return None

    intrinsic = (max(0.0, S - K) if option_type == "call" else max(0.0, K - S))
    if market_price < intrinsic - 1e-6:
        return None  # price below intrinsic -> no valid IV

    lo, hi = 1e-4, 5.0  # 0.01% to 500% vol
    p_lo = bs_price(S, K, T, r, lo, option_type) - market_price
    p_hi = bs_price(S, K, T, r, hi, option_type) - market_price
    if p_lo * p_hi > 0:
        return None

    for _ in range(max_iter):
        mid = 0.5 * (lo + hi)
        p_mid = bs_price(S, K, T, r, mid, option_type) - market_price
        if abs(p_mid) < tol:
            return mid
        if p_lo * p_mid < 0:
            hi = mid
        else:
            lo, p_lo = mid, p_mid
    return 0.5 * (lo + hi)


def max_pain(oi_by_strike: dict[float, dict]) -> float | None:
    """
    Compute 'max pain' strike given open interest.
    oi_by_strike = {strike: {'call_oi': x, 'put_oi': y}, ...}
    Max pain = strike where total option holder payout is minimized.
    """
    strikes = sorted(oi_by_strike.keys())
    if not strikes:
        return None
    best_strike, best_pain = None, math.inf
    for expiry_price in strikes:
        pain = 0.0
        for k, oi in oi_by_strike.items():
            call_oi = oi.get("call_oi", 0)
            put_oi = oi.get("put_oi", 0)
            pain += max(0.0, expiry_price - k) * call_oi   # call writers' loss
            pain += max(0.0, k - expiry_price) * put_oi    # put writers' loss
        if pain < best_pain:
            best_pain, best_strike = pain, expiry_price
    return best_strike


if __name__ == "__main__":
    g = compute_greeks(S=23500, K=23500, T=7/365, r=0.065, sigma=0.13, option_type="call")
    print(g)
    iv = implied_vol(market_price=g.price, S=23500, K=23500, T=7/365, r=0.065, option_type="call")
    print("recovered IV:", round(iv, 4) if iv else None)
