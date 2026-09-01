"""Shared fixtures: journal isolation, quote/candidate builders, fake broker."""

from datetime import timedelta
from types import SimpleNamespace

import pytest
from alpaca.trading.enums import OrderStatus

from theta_shepherd.econ_calendar import today_et
from theta_shepherd.market import OptionQuote
from theta_shepherd.strategy import SpreadCandidate


@pytest.fixture(autouse=True)
def tmp_journal(tmp_path, monkeypatch):
    """Point every journal write at a throwaway directory."""
    import theta_shepherd.journal as journal
    monkeypatch.setattr(journal, "settings", SimpleNamespace(journal_dir=tmp_path))
    monkeypatch.setattr(journal, "STATE_FILE", tmp_path / "state.json")
    monkeypatch.setattr(journal, "STATE_BACKUP", tmp_path / "state.json.bak")
    return tmp_path


def make_quote(underlying="SPY", strike=630.0, cp="put", bid=0.95, ask=1.05,
               delta=-0.18, dte=4, iv=0.15) -> OptionQuote:
    exp = today_et() + timedelta(days=dte)  # quotes are dated in market time
    ymd = exp.strftime("%y%m%d")
    occ = f"{underlying}{ymd}{'P' if cp == 'put' else 'C'}{int(strike * 1000):08d}"
    return OptionQuote(symbol=occ, underlying=underlying, expiration=exp,
                       contract_type=cp, strike=strike, bid=bid, ask=ask,
                       delta=delta, theta=-0.05, iv=iv)


def make_candidate(credit=1.0, width=5.0, delta=-0.20, underlying="SPY",
                   kind="put_credit", price=643.0) -> SpreadCandidate:
    short = make_quote(underlying=underlying, strike=630.0, bid=1.10, ask=1.20, delta=delta,
                       cp="put" if kind == "put_credit" else "call")
    long = make_quote(underlying=underlying, strike=625.0, bid=0.10, ask=0.20, delta=delta / 2,
                      cp="put" if kind == "put_credit" else "call")
    return SpreadCandidate(underlying=underlying, kind=kind, expiration=short.expiration,
                           short=short, long=long, credit=credit, width=width,
                           underlying_price=price)


class FakeOrder(SimpleNamespace):
    pass


class FakeTradingClient:
    """Minimal stand-in for alpaca TradingClient covering reconcile paths."""

    def __init__(self, orders: dict[str, FakeOrder] | None = None):
        self.orders = orders or {}
        self.submitted: list = []
        self.cancelled: list[str] = []

    def get_order_by_id(self, order_id):
        return self.orders[order_id]

    def cancel_order_by_id(self, order_id):
        """A real cancel moves the order to a terminal state. The old fake left
        it NEW forever, which made the cancel-confirmation path untestable and
        hid the double-submit risk it now guards against."""
        self.cancelled.append(order_id)
        order = self.orders.get(order_id)
        if order is not None and order.status not in (OrderStatus.FILLED,):
            order.status = OrderStatus.CANCELED

    def submit_order(self, order):
        self.submitted.append(order)
        new = FakeOrder(id=f"resub-{len(self.submitted)}", status="new",
                        filled_avg_price=None)
        self.orders[new.id] = new
        return new

    def get_all_positions(self):
        return []
