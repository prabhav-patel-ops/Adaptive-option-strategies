from pricing import price,iv,greeks

def test_roundtrip():
    for kind in ("CE","PE"):
        p=price(25000,25000,.1,.06,.2,kind)
        assert abs(iv(p,25000,25000,.1,.06,kind)-.2)<1e-7

def test_parity():
    from math import exp
    assert abs(price(25100,25000,.1,.06,.2)-price(25100,25000,.1,.06,.2,"PE")-100*exp(-.006))<1e-8
