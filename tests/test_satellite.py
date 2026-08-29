"""Satellite sleeve: candidate construction, sizing, gates, exits, reconcile."""

from alpaca.trading.enums import OrderStatus

from theta_shepherd.agent import reconcile, satellite_exit_reason
from theta_shepherd.committee import unanimous_direction
from theta_shepherd.config import settings
from theta_shepherd.risk import AccountRisk, satellite_gates, size_satellite
from theta_shepherd.strategy import DebitCandidate, find_satellite_candidate

from conftest import FakeOrder, FakeTradingClient, make_quote


import pytest


@pytest.fixture(autouse=True)
def far_horizon(monkeypatch):
    """Keep candidate-construction tests date-stable: pretend the contest
    horizon is far away regardless of when the suite runs."""
    import theta_shepherd.strategy as strategy
    monkeypatch.setattr(strategy, "effective_max_dte", lambda today=None: 5)


class FakeMD:
    def __init__(self, price, quotes):
        self.price, self.quotes = price, quotes

    def last_price(self, symbol):
        return self.price

    def chain(self, underlying, contract_type, lo, hi, dte_lo, dte_hi):
        return self.quotes


def make_debit(debit=2.0, width=5.0, direction="bullish") -> DebitCandidate:
    buy = make_quote(strike=640.0, cp="call", bid=3.00, ask=3.20, delta=0.55)
    sell = make_quote(strike=645.0, cp="call", bid=1.20, ask=1.30, delta=0.35)
    return DebitCandidate(underlying="SPY", direction=direction,
                          expiration=buy.expiration, buy=buy, sell=sell,
                          debit=debit, width=width, underlying_price=641.0)


def test_find_satellite_builds_bull_call_spread():
    buy = make_quote(strike=640.0, cp="call", bid=3.00, ask=3.20, delta=0.55)
    sell = make_quote(strike=645.0, cp="call", bid=1.20, ask=1.30, delta=0.35)
    cand = find_satellite_candidate(FakeMD(641.0, [buy, sell]), "SPY", "bullish")
    assert cand is not None
    assert cand.buy.strike == 640.0 and cand.sell.strike == 645.0
    assert cand.debit == 2.00                      # buy ask - sell bid
    assert cand.max_loss == 200.0 and cand.max_gain == 300.0


def test_find_satellite_bearish_uses_puts_downward():
    buy = make_quote(strike=640.0, cp="put", bid=3.00, ask=3.20, delta=-0.50)
    sell = make_quote(strike=635.0, cp="put", bid=1.40, ask=1.50, delta=-0.30)
    cand = find_satellite_candidate(FakeMD(641.0, [buy, sell]), "SPY", "bearish")
    assert cand is not None
    assert cand.buy.strike == 640.0 and cand.sell.strike == 635.0
    assert cand.kind == "satellite_bear"


def test_find_satellite_rejects_overpriced_debit():
    # debit 3.30 > 60% of the $5 width
    buy = make_quote(strike=640.0, cp="call", bid=4.00, ask=4.20, delta=0.55)
    sell = make_quote(strike=645.0, cp="call", bid=0.90, ask=1.00, delta=0.30)
    assert find_satellite_candidate(FakeMD(641.0, [buy, sell]), "SPY", "bullish") is None


def test_find_satellite_requires_near_the_money_long():
    buy = make_quote(strike=640.0, cp="call", bid=0.80, ask=0.90, delta=0.20)  # too far OTM
    sell = make_quote(strike=645.0, cp="call", bid=0.30, ask=0.40, delta=0.10)
    assert find_satellite_candidate(FakeMD(660.0, [buy, sell]), "SPY", "bullish") is None


def test_size_satellite_respects_sleeve_budget():
    cand = make_debit(debit=2.0)  # $200 per lot
    assert size_satellite(cand) == int(settings.satellite_max_risk // 200)


def healthy() -> AccountRisk:
    return AccountRisk(equity=100_000.0, day_pnl=0.0, open_spreads=1,
                       committed_risk=1_600.0)


def test_satellite_gates_pass_when_clean():
    assert satellite_gates(healthy(), make_debit(), qty=5, has_satellite=False) == []


def test_satellite_gates_one_at_a_time():
    vio = satellite_gates(healthy(), make_debit(), 5, has_satellite=True)
    assert any("satellite_exists" in v for v in vio)


def test_satellite_gates_budget_cap():
    over = int(settings.satellite_max_risk // 200) + 1  # one lot past the budget
    vio = satellite_gates(healthy(), make_debit(debit=2.0), qty=over, has_satellite=False)
    assert any("satellite_risk_cap" in v for v in vio)


def test_satellite_gates_daily_loss():
    risk = AccountRisk(equity=97_000.0, day_pnl=-settings.daily_loss_limit,
                       open_spreads=0, committed_risk=0.0)
    vio = satellite_gates(risk, make_debit(), 5, has_satellite=False)
    assert any("daily_loss_limit" in v for v in vio)


def test_satellite_exit_thresholds():
    assert satellite_exit_reason(3.0, 2.0, dte=4) == "profit_target"   # 1.5x
    assert satellite_exit_reason(1.0, 2.0, dte=4) == "stop_loss"       # 0.5x
    assert satellite_exit_reason(2.0, 2.0, dte=1) == "expiry_close"
    assert satellite_exit_reason(None, 2.0, dte=1) == "expiry_close"   # unquotable
    assert satellite_exit_reason(2.2, 2.0, dte=4) is None
    assert satellite_exit_reason(None, 2.0, dte=4) is None


def test_unanimous_direction():
    ops = lambda a, b, c: {"m": {"directional_view": a},
                           "v": {"directional_view": b},
                           "r": {"directional_view": c}}
    assert unanimous_direction(ops("bullish", "bullish", "bullish")) == "bullish"
    assert unanimous_direction(ops("bearish", "bearish", "bearish")) == "bearish"
    assert unanimous_direction(ops("bullish", "bullish", "neutral")) is None
    assert unanimous_direction(ops("neutral", "neutral", "neutral")) is None
    assert unanimous_direction(ops("bullish", "bearish", "bullish")) is None


def sat_spread(**over) -> dict:
    base = {
        "client_order_id": "shepherd-sat-abc", "order_id": "o1", "qty": 5,
        "limit_debit": 2.00, "width": 5.0, "status": "pending_fill",
        "sleeve": "satellite", "kind": "satellite_bull",
        "long_symbol": "SPY260902C00640000", "short_symbol": "SPY260902C00645000",
    }
    return {**base, **over}


def test_reconcile_satellite_fill_adopted():
    trading = FakeTradingClient({"o1": FakeOrder(status=OrderStatus.FILLED,
                                                 filled_avg_price=1.95)})
    state = {"open_spreads": [sat_spread()]}
    reconcile(trading, state)
    (s,) = state["open_spreads"]
    assert s["status"] == "open"
    assert s["filled_debit"] == 1.95


def test_reconcile_stale_satellite_is_abandoned_not_repriced():
    trading = FakeTradingClient({"o1": FakeOrder(status=OrderStatus.NEW,
                                                 filled_avg_price=None)})
    state = {"open_spreads": [sat_spread()]}
    reconcile(trading, state)
    assert state["open_spreads"] == []       # dropped
    assert trading.submitted == []           # never chased
    assert "o1" in trading.cancelled


def test_reconcile_satellite_close_realizes_pnl():
    trading = FakeTradingClient({"x1": FakeOrder(status=OrderStatus.FILLED,
                                                 filled_avg_price=-3.10)})
    state = {"open_spreads": [sat_spread(status="closing", close_order_id="x1",
                                         filled_debit=2.00)]}
    reconcile(trading, state)
    assert state["open_spreads"] == []       # off the book, P&L journaled
