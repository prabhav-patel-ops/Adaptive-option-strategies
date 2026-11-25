"""Short-option experiment with futures orders decided at close and filled next open."""

from math import ceil, isfinite, sqrt

import pandas as pd

POLICIES = ("unhedged", "daily", "adaptive")


def adaptive_band(gamma, future, band, shock):
    """Shrink the delta deadband as gamma implies larger delta moves under stress."""
    return band / (1 + abs(gamma * future * shock) / band)


def simulate(frame, policy="adaptive", band=.15, shock=.01, cost_bps=2,
             option_lot=1, futures_lot=1, option_cost_bps=0, option_lots=1):
    if policy not in POLICIES:
        raise ValueError("unknown policy")
    settings = (band, shock, cost_bps, option_lot, futures_lot, option_cost_bps, option_lots)
    if (not all(map(isfinite, settings)) or not 0 < band <= 1
            or min(shock, cost_bps, option_cost_bps) < 0
            or any(n <= 0 or int(n) != n for n in (option_lot, futures_lot, option_lots))):
        raise ValueError("invalid hedge parameters or lot sizes")
    f = frame.copy()
    f["date"] = pd.to_datetime(f.date, errors="raise")
    f = f.sort_values("date")
    if len(f) < 2 or f.date.duplicated().any() or f.date.isna().any():
        raise ValueError("at least two observations on unique dates are required")
    # A panel saved by the original prepare.py has close marks only.
    next_open_entry = "option_open" in f
    price_fields = ["future_open", "future_close", "option_close"]
    if next_open_entry:
        price_fields.append("option_open")
    fields = price_fields + ["delta", "gamma"]
    if not f[fields].apply(lambda col: col.map(isfinite)).all().all():
        raise ValueError("non-finite observation")
    if (f[price_fields] <= 0).any().any():
        raise ValueError("positive execution and marking prices required")

    option_units = option_lot * option_lots
    hedge = target = 0
    rows = []
    previous = None
    for i, x in enumerate(f.itertuples(index=False)):
        final = i == len(f) - 1
        change = target - hedge
        future_pnl = option_pnl = 0.0
        entry = i == (1 if next_open_entry else 0)
        entry_mark = (x.option_open if next_open_entry else x.option_close) if entry else 0
        if previous is not None:
            opening_mark = entry_mark if entry else previous.option_close
            option_pnl = option_units * (opening_mark - x.option_close)
            future_pnl = futures_lot * (
                hedge * (x.future_open - previous.future_close)
                + target * (x.future_close - x.future_open)
            )
        future_cost = abs(change) * futures_lot * x.future_open * cost_bps / 10_000
        turnover = abs(change)
        hedge = target
        if final:
            future_cost += abs(hedge) * futures_lot * x.future_close * cost_bps / 10_000
            turnover += abs(hedge)
            hedge = 0
        option_cost = option_units * (entry_mark + (x.option_close if final else 0)) * option_cost_bps / 10_000
        tolerance = adaptive_band(x.gamma, x.future_close, band, shock)
        residual = x.delta - hedge * futures_lot / option_units
        if not final and (policy == "daily" or (policy == "adaptive" and abs(residual) > tolerance)):
            target = round(x.delta * option_units / futures_lot)
        cost = future_cost + option_cost
        rows.append(dict(date=x.date, pnl=option_pnl + future_pnl - cost, cost=cost,
                         option_cost=option_cost, future_cost=future_cost, hedge=hedge,
                         turnover=turnover))
        previous = x
    out = pd.DataFrame(rows)
    out["cumulative_pnl"] = out.pnl.cumsum()
    return out


def summarize(ledger, capital):
    """Return INR metrics and fixed-capital daily Sharpe with a zero excess hurdle."""
    if not isfinite(capital) or capital <= 0 or ledger.empty:
        raise ValueError("positive capital and a nonempty ledger required")
    pnl = ledger.pnl
    equity = capital + pnl.cumsum()
    peak = equity.cummax().clip(lower=capital)
    drawdown = equity - peak
    daily_return = pnl / capital
    volatility = daily_return.std()
    tail_count = ceil(len(pnl) / 20)
    worst_losses = (-pnl).nlargest(tail_count)
    return {
        "pnl": float(pnl.sum()),
        "cost": float(ledger.cost.sum()),
        "hedge_cost": float(ledger.future_cost.sum()),
        "turnover": int(ledger.turnover.sum()),
        "sharpe": float(sqrt(252) * daily_return.mean() / volatility) if volatility > 0 else None,
        "max_drawdown": float(-drawdown.min()),
        "max_drawdown_pct": float((-drawdown / peak).max()),
        "var_95": float(worst_losses.iloc[-1]),
        "es_95": float(worst_losses.mean()),
        "tail_observations": tail_count,
    }
