"""reconcile() against a fake broker: every pending-order path."""

from alpaca.trading.enums import OrderStatus

from theta_shepherd.agent import reconcile
from theta_shepherd.config import settings

from conftest import FakeOrder, FakeTradingClient


def spread(**over) -> dict:
    base = {
        "client_order_id": "shepherd-abc", "order_id": "o1", "qty": 2,
        "limit_credit": 0.80, "width": 5.0, "status": "pending_fill",
        "short_symbol": "SPY260902P00630000", "long_symbol": "SPY260902P00625000",
    }
    return {**base, **over}


def test_pending_entry_that_filled_becomes_open():
    trading = FakeTradingClient({"o1": FakeOrder(status=OrderStatus.FILLED,
                                                 filled_avg_price=-1.01)})
    state = {"open_spreads": [spread()]}
    reconcile(trading, state)
    (s,) = state["open_spreads"]
    assert s["status"] == "open"
    assert s["filled_credit"] == 1.01


def test_pending_entry_that_died_is_dropped():
    trading = FakeTradingClient({"o1": FakeOrder(status=OrderStatus.CANCELED,
                                                 filled_avg_price=None)})
    state = {"open_spreads": [spread()]}
    reconcile(trading, state)
    assert state["open_spreads"] == []


def test_stale_entry_is_repriced_one_step():
    trading = FakeTradingClient({"o1": FakeOrder(status=OrderStatus.NEW,
                                                 filled_avg_price=None)})
    state = {"open_spreads": [spread(limit_credit=0.80)]}
    reconcile(trading, state)
    (s,) = state["open_spreads"]
    assert "o1" in trading.cancelled
    assert s["limit_credit"] == 0.77            # one REPRICE_STEP cheaper
    assert s["order_id"].startswith("resub-")   # fresh order at the broker
    assert s["status"] == "pending_fill"


def test_stale_entry_below_credit_floor_is_abandoned():
    trading = FakeTradingClient({"o1": FakeOrder(status=OrderStatus.NEW,
                                                 filled_avg_price=None)})
    # Derive from the floor rather than hardcoding it: start exactly at the
    # floor so the next REPRICE_STEP drops the entry under it. Pinning a
    # literal credit here silently stopped testing abandonment when
    # min_credit_frac was retuned.
    floor = settings.min_credit_frac * 5.0
    state = {"open_spreads": [spread(limit_credit=round(floor, 2))]}
    reconcile(trading, state)
    assert state["open_spreads"] == []
    assert trading.submitted == []


def test_race_fill_during_cancel_is_adopted():
    """Order fills between our decision to reprice and the cancel."""
    class RacyClient(FakeTradingClient):
        def get_order_by_id(self, order_id):
            order = self.orders[order_id]
            if self.cancelled:  # second look, after cancel attempt: it filled
                order.status = OrderStatus.FILLED
                order.filled_avg_price = -0.79
            return order

    trading = RacyClient({"o1": FakeOrder(status=OrderStatus.NEW, filled_avg_price=None)})
    state = {"open_spreads": [spread()]}
    reconcile(trading, state)
    (s,) = state["open_spreads"]
    assert s["status"] == "open"
    assert s["filled_credit"] == 0.79


def test_filled_exit_is_removed_from_book():
    trading = FakeTradingClient({"x1": FakeOrder(status=OrderStatus.FILLED,
                                                 filled_avg_price=0.40)})
    state = {"open_spreads": [spread(status="closing", close_order_id="x1",
                                     filled_credit=1.01)]}
    reconcile(trading, state)
    assert state["open_spreads"] == []


def test_stuck_exit_reverts_to_open_for_retry():
    trading = FakeTradingClient({"x1": FakeOrder(status=OrderStatus.NEW,
                                                 filled_avg_price=None)})
    state = {"open_spreads": [spread(status="closing", close_order_id="x1",
                                     filled_credit=1.01)]}
    reconcile(trading, state)
    (s,) = state["open_spreads"]
    assert s["status"] == "open"
    assert "close_order_id" not in s
