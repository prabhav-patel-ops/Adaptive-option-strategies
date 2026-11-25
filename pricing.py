"""Black-76 European option valuation with futures-price sensitivities."""

from math import exp, isfinite, log, pi, sqrt

from scipy.optimize import brentq
from scipy.special import ndtr


def _inputs(F, K, T, r, kind):
    if not all(map(isfinite, (F, K, T, r))) or min(F, K) <= 0 or T < 0:
        raise ValueError("finite positive futures and strike, and nonnegative time required")
    if kind not in ("CE", "PE"):
        raise ValueError("invalid option type")
    return (1 if kind == "CE" else -1), exp(-r * T)


def _d(F, K, T, sigma):
    width = sigma * sqrt(T)
    midpoint = (log(F) - log(K)) / width
    return midpoint + width / 2, midpoint - width / 2


def price(F, K, T, r, sigma, kind="CE"):
    """Return option points. Volatility and continuously compounded rate are decimals."""
    sign, discount = _inputs(F, K, T, r, kind)
    if not isfinite(sigma) or sigma < 0:
        raise ValueError("finite nonnegative volatility required")
    intrinsic = max(sign * (F - K), 0)
    if T == 0 or sigma == 0:
        return discount * intrinsic
    d1, d2 = _d(F, K, T, sigma)
    # Evaluate the OTM leg and recover the ITM leg by put-call parity.
    if F <= K:
        time_value = F * ndtr(d1) - K * ndtr(d2)
    else:
        time_value = K * ndtr(-d2) - F * ndtr(-d1)
    return discount * (intrinsic + max(time_value, 0))


def iv(p, F, K, T, r, kind="CE"):
    sign, discount = _inputs(F, K, T, r, kind)
    lower = discount * max(sign * (F - K), 0)
    upper = discount * (F if sign == 1 else K)
    if T == 0 or not isfinite(p) or not lower <= p < upper:
        raise ValueError("price outside Black-76 implied volatility bounds")
    if p == lower:
        return 0.0
    high = 1 / sqrt(T)
    while price(F, K, T, r, high, kind) < p:
        high *= 2
    return brentq(lambda sigma: price(F, K, T, r, sigma, kind) - p, 0, high)


def greeks(F, K, T, r, sigma, kind="CE"):
    """Return futures delta, futures gamma and vega per unit of decimal volatility."""
    sign, discount = _inputs(F, K, T, r, kind)
    if T == 0 or not isfinite(sigma) or sigma <= 0:
        raise ValueError("positive time and volatility required for smooth Greeks")
    d1, _ = _d(F, K, T, sigma)
    density = exp(-d1 * d1 / 2) / sqrt(2 * pi)
    return (sign * discount * ndtr(sign * d1),
            discount * density / (F * sigma * sqrt(T)),
            discount * F * density * sqrt(T))
