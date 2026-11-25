from pricing import price,iv,greeks
from math import exp, log, pi, sqrt

import pytest
from scipy.integrate import quad

def test_roundtrip():
    for kind in ("CE","PE"):
        p=price(25000,25000,.1,.06,.2,kind)
        assert abs(iv(p,25000,25000,.1,.06,kind)-.2)<1e-7

def test_parity():
    assert abs(price(25100,25000,.1,.06,.2)-price(25100,25000,.1,.06,.2,"PE")-100*exp(-.006))<1e-8


@pytest.mark.parametrize("kind,sign", [("CE", 1), ("PE", -1)])
def test_price_against_discounted_lognormal_payoff(kind, sign):
    f, k, t, r, vol = 105, 97, .37, -.012, .43
    width = vol * sqrt(t)
    cutoff = (log(k / f) + width**2 / 2) / width

    def payoff(z):
        terminal = f * exp(-width**2 / 2 + width * z)
        return max(sign * (terminal - k), 0) * exp(-z**2 / 2) / sqrt(2 * pi)

    integral, _ = quad(payoff, cutoff, 14) if sign == 1 else quad(payoff, -14, cutoff)
    assert price(f, k, t, r, vol, kind) == pytest.approx(exp(-r * t) * integral, abs=1e-10)


@pytest.mark.parametrize("kind", ["CE", "PE"])
def test_greeks_against_central_differences(kind):
    f, k, t, r, vol = 101, 104, .29, .031, .23
    bump = .01
    center, up, down = [price(f + h, k, t, r, vol, kind) for h in (0, bump, -bump)]
    delta, gamma, vega = greeks(f, k, t, r, vol, kind)
    assert delta == pytest.approx((up - down) / (2 * bump), rel=1e-6)
    assert gamma == pytest.approx((up + down - 2 * center) / bump**2, rel=1e-6)
    up, down = [price(f, k, t, r, vol + h, kind) for h in (1e-5, -1e-5)]
    assert vega == pytest.approx((up - down) / 2e-5, rel=1e-6)


def test_degenerate_prices_bounds_and_iv_bracket():
    assert price(108, 100, 0, .03, .2) == 8
    floor = price(108, 100, .1, .03, 0)
    assert iv(floor, 108, 100, .1, .03) == 0
    assert iv(price(100, 100, 1 / 365, 0, 16), 100, 100, 1 / 365, 0) == pytest.approx(16)
    for option_price in [floor - .1, 108 * exp(-.003), float("nan")]:
        with pytest.raises(ValueError, match="bounds"):
            iv(option_price, 108, 100, .1, .03)
    with pytest.raises(ValueError, match="type"):
        greeks(108, 100, .1, .03, .2, "XX")
    with pytest.raises(ValueError, match="positive time"):
        greeks(108, 100, 0, .03, .2)
