import pandas as pd
import pytest

from backtest import adaptive_band, simulate, summarize


def observations():
    return pd.DataFrame({
        "date": ["2025-01-02", "2025-01-03", "2025-01-06"],
        "future_open": [100, 102, 107],
        "future_close": [100, 105, 109],
        "option_close": [9, 10, 12],
        "delta": [.55, .45, .38],
        "gamma": [.03, 0, .03],
    })


def test_hedge_timing_overnight_costs_and_liquidation():
    out = simulate(observations(), "daily", option_lots=10, cost_bps=100, option_cost_bps=100)
    # Python rounds ties to even. Day 2 takes six, day 3 trades from six to four.
    assert out.hedge.tolist() == [0, 6, 0]
    assert out.turnover.tolist() == [0, 6, 6]
    assert out.pnl.tolist() == pytest.approx([-.9, -10 + 18 - 6.12, -20 + 12 + 8 - 2.14 - 4.36 - 1.2])
    assert out.future_cost.sum() == pytest.approx(6.12 + 2.14 + 4.36)
    assert out.option_cost.sum() == pytest.approx(2.1)


def test_gamma_band_and_integer_lots():
    assert adaptive_band(0, 100, .15, .01) == .15
    assert adaptive_band(.3, 100, .15, .01) < adaptive_band(.03, 100, .15, .01)
    frame = observations()
    frame["delta"] = [.55, .49, .38]
    daily = simulate(frame, "daily", option_lots=10)
    adaptive = simulate(frame, "adaptive", option_lots=10)
    unhedged = simulate(frame, "unhedged", option_lots=10)
    assert daily.turnover.tolist() == [0, 6, 6]
    assert adaptive.turnover.tolist() == [0, 6, 6]
    assert daily.pnl.iloc[-1] != adaptive.pnl.iloc[-1]
    assert unhedged.pnl.tolist() == pytest.approx([0, -10, -20])
    assert unhedged.cost.sum() == 0
    frame["gamma"] = [.03, .3, .03]
    tighter = simulate(frame, "adaptive", option_lots=10)
    assert tighter.pnl.tolist() == pytest.approx(daily.pnl.tolist())


def test_risk_metrics_include_opening_capital_peak_and_loss_tail():
    frame = pd.DataFrame({"pnl": [-10, 30, -8, -30] + [0] * 17,
                          "cost": [1] * 21, "future_cost": [0] * 21, "turnover": [0] * 21})
    result = summarize(frame, 100)
    assert result["pnl"] == -18
    assert result["max_drawdown"] == pytest.approx(38)
    assert result["max_drawdown_pct"] == pytest.approx(38 / 120)
    assert result["var_95"] == 10
    assert result["es_95"] == 20
    assert result["tail_observations"] == 2


def test_option_entry_occurs_after_selection_at_prior_close():
    frame = observations()
    frame["option_open"] = [8, 11, 10]
    out = simulate(frame, "unhedged", option_lots=10, option_cost_bps=100)
    assert out.pnl.tolist() == pytest.approx([0, 10 - 1.1, -20 - 1.2])
    assert out.option_cost.tolist() == pytest.approx([0, 1.1, 1.2])
