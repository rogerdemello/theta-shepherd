from datetime import date

import pytest

from theta_shepherd.market import parse_occ


def test_parse_occ_put():
    root, exp, cp, strike = parse_occ("SPY250903P00640000")
    assert (root, exp, cp, strike) == ("SPY", date(2025, 9, 3), "put", 640.0)


def test_parse_occ_call():
    root, exp, cp, strike = parse_occ("QQQ260904C00728000")
    assert (root, exp, cp, strike) == ("QQQ", date(2026, 9, 4), "call", 728.0)


def test_parse_occ_fractional_strike():
    assert parse_occ("IWM260904P00220500")[3] == 220.5


@pytest.mark.parametrize("bad", ["AAPL", "SPY2509", "spy250903p00640000", ""])
def test_parse_occ_rejects_garbage(bad):
    with pytest.raises(ValueError):
        parse_occ(bad)
