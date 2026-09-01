"""Session-2 hardening: market-time dating, crash safety, cancel races,
broker-read paranoia, retries and the liquidity floor.

Every test here corresponds to a way the live agent could have lost money or
lost track of a position without anyone noticing until the next morning.
"""

from datetime import date, datetime, timedelta

import pytest
from alpaca.trading.enums import OrderStatus

import theta_shepherd.agent as agent
import theta_shepherd.econ_calendar as econ_calendar
import theta_shepherd.resilience as resilience
import theta_shepherd.strategy as strategy
from theta_shepherd.agent import (
    execute_approvals,
    flatten_all,
    manage_exits,
    reconcile,
    should_force_close,
    sync_with_broker,
)
from theta_shepherd.econ_calendar import ET, today_et
from theta_shepherd.journal import load_state
from theta_shepherd.market import OptionQuote
from theta_shepherd.resilience import retry
from theta_shepherd.risk import AccountRisk
from theta_shepherd.strategy import effective_max_dte, illiquid

from conftest import FakeOrder, FakeTradingClient, make_candidate, make_quote


@pytest.fixture
def no_wait(monkeypatch):
    """Strip every backoff/poll delay out of the paths under test."""
    monkeypatch.setattr(agent, "CANCEL_CONFIRM_DELAY", 0)
    monkeypatch.setattr(resilience.time, "sleep", lambda *_: None)
    monkeypatch.setattr(agent.time, "sleep", lambda *_: None)


def freeze_et(monkeypatch, when: datetime) -> None:
    monkeypatch.setattr(econ_calendar, "now_et", lambda: when)


def spread(**over) -> dict:
    base = {
        "client_order_id": "shepherd-abc", "order_id": "o1", "qty": 2,
        "limit_credit": 0.80, "width": 5.0, "status": "pending_fill",
        "short_symbol": "SPY260903P00630000", "long_symbol": "SPY260903P00625000",
    }
    return {**base, **over}


# --- Market-time dating -----------------------------------------------------
# The machine runs in IST, where local midnight is 14:30 ET — mid-session.
# Every DTE measured against the local date is a day short for the last 90
# minutes of every session.

def test_today_et_is_the_market_date_not_the_local_one(monkeypatch):
    # 00:15 IST on Sep 3 is 14:45 ET on Sep 2. The market's date is Sep 2.
    freeze_et(monkeypatch, datetime(2026, 9, 2, 14, 45, tzinfo=ET))
    assert today_et() == date(2026, 9, 2)


def test_tomorrows_expiry_is_not_treated_as_expiry_day_after_ist_midnight(monkeypatch):
    """The regression: a Sep-3 spread read as dte=0 at 14:45 ET on Sep 2, and
    the expiry-day rule (>= 14:00 ET) force-closed it a full day early —
    surrendering the richest day of theta the strategy exists to collect."""
    now = datetime(2026, 9, 2, 14, 45, tzinfo=ET)
    freeze_et(monkeypatch, now)
    quote = OptionQuote(symbol="SPY260903P00630000", underlying="SPY",
                        expiration=date(2026, 9, 3), contract_type="put",
                        strike=630.0, bid=0.95, ask=1.05, delta=-0.18,
                        theta=-0.05, iv=0.15)
    assert quote.dte == 1
    assert not should_force_close(quote.dte, now)


def test_scout_horizon_uses_market_date(monkeypatch):
    """Same skew emptied the board: effective_max_dte hit 0 (below min_dte)
    during the last 90 minutes of the Sep-2 session."""
    freeze_et(monkeypatch, datetime(2026, 9, 2, 14, 45, tzinfo=ET))
    assert effective_max_dte() == 1


# --- Cancel races -----------------------------------------------------------

class StubbornClient(FakeTradingClient):
    """A broker that accepts the cancel request but never settles it — the
    order is still live and can fill at any moment."""

    def cancel_order_by_id(self, order_id):
        self.cancelled.append(order_id)  # requested, not honoured


def test_unconfirmed_entry_cancel_is_not_repriced(no_wait):
    trading = StubbornClient({"o1": FakeOrder(status=OrderStatus.NEW,
                                              filled_avg_price=None)})
    state = {"open_spreads": [spread()]}
    reconcile(trading, state)
    (s,) = state["open_spreads"]
    assert trading.submitted == []          # no second spread at the broker
    assert s["status"] == "pending_fill"
    assert s["limit_credit"] == 0.80        # untouched, retried next cycle


def test_unconfirmed_exit_cancel_keeps_the_close_order(no_wait):
    trading = StubbornClient({"x1": FakeOrder(status=OrderStatus.NEW,
                                              filled_avg_price=None)})
    state = {"open_spreads": [spread(status="closing", close_order_id="x1",
                                     filled_credit=1.01)]}
    reconcile(trading, state)
    (s,) = state["open_spreads"]
    # Reverting to "open" here would submit a second close next cycle; if the
    # first one then fills we are short the inverse spread.
    assert s["status"] == "closing"
    assert s["close_order_id"] == "x1"
    assert "close_attempts" not in s


def test_stuck_exit_is_journaled_after_repeated_failures(no_wait, tmp_journal):
    trading = FakeTradingClient({"x1": FakeOrder(status=OrderStatus.NEW,
                                                 filled_avg_price=None)})
    state = {"open_spreads": [spread(status="closing", close_order_id="x1",
                                     filled_credit=1.01, close_attempts=4)]}
    reconcile(trading, state)
    assert state["open_spreads"][0]["close_attempts"] == 5
    assert any("exit_stuck" in line
               for p in tmp_journal.glob("*.jsonl")
               for line in p.read_text(encoding="utf-8").splitlines())


# --- Fault containment ------------------------------------------------------

def test_one_unreadable_order_does_not_abort_the_pass(no_wait):
    class FlakyClient(FakeTradingClient):
        def get_order_by_id(self, order_id):
            if order_id == "bad":
                raise RuntimeError("500 from the orders endpoint")
            return self.orders[order_id]

    trading = FlakyClient({"o2": FakeOrder(status=OrderStatus.FILLED,
                                           filled_avg_price=-0.90)})
    state = {"open_spreads": [
        spread(order_id="bad", client_order_id="shepherd-bad"),
        spread(order_id="o2", client_order_id="shepherd-ok"),
    ]}
    reconcile(trading, state)
    by_id = {s["client_order_id"]: s for s in state["open_spreads"]}
    assert by_id["shepherd-bad"]["status"] == "pending_fill"  # kept, still tracked
    assert by_id["shepherd-ok"]["status"] == "open"           # the healthy one progressed


def test_one_failing_exit_does_not_block_the_others(monkeypatch, tmp_journal):
    calls = []

    def fake_close(trading, s, reason, price, pad=0.03):
        calls.append(s["short_symbol"])
        if s["short_symbol"].endswith("P00630000"):
            raise RuntimeError("order rejected")
        return "close-1"

    monkeypatch.setattr(agent, "close_spread", fake_close)
    monkeypatch.setattr(agent, "spread_close_cost", lambda md, s: 0.10)  # profit target
    state = {"open_spreads": [
        spread(status="open", filled_credit=1.00),
        spread(status="open", filled_credit=1.00, client_order_id="shepherd-two",
               short_symbol="QQQ260903P00700000", long_symbol="QQQ260903P00695000"),
    ]}
    manage_exits(FakeTradingClient(), None, state)
    assert len(calls) == 2
    assert state["open_spreads"][1]["status"] == "closing"
    # The exit order that exists at the broker is on disk before we move on.
    assert load_state()["open_spreads"][1]["close_order_id"] == "close-1"


def test_flatten_closes_the_rest_when_one_leg_fails(monkeypatch):
    def fake_close(trading, s, reason, price, pad=0.03):
        if s["short_symbol"].endswith("P00630000"):
            raise RuntimeError("unquotable")
        return "flat-1"

    monkeypatch.setattr(agent, "close_spread", fake_close)
    monkeypatch.setattr(agent, "spread_close_cost", lambda md, s: 0.50)
    state = {"open_spreads": [
        spread(status="open", filled_credit=1.00),
        spread(status="open", filled_credit=1.00, client_order_id="shepherd-two",
               short_symbol="QQQ260903P00700000", long_symbol="QQQ260903P00695000"),
    ]}
    flatten_all(FakeTradingClient(), None, state, "test")
    assert state["open_spreads"][0]["status"] == "open"       # failed, retried next cycle
    assert state["open_spreads"][1]["status"] == "closing"    # the rest still went


def test_flatten_pays_up_on_a_spread_that_keeps_refusing(monkeypatch):
    pads = []
    monkeypatch.setattr(agent, "spread_close_cost", lambda md, s: 0.50)
    monkeypatch.setattr(agent, "close_spread",
                        lambda t, s, r, p, pad=0.03: pads.append(pad) or "x")
    state = {"open_spreads": [spread(status="open", filled_credit=1.00,
                                     close_attempts=6)]}
    flatten_all(FakeTradingClient(), None, state, "test")
    assert pads == [0.15]  # escalated, not the flat 0.10


# --- Broker-read paranoia ---------------------------------------------------

class PositionClient(FakeTradingClient):
    def __init__(self, symbols):
        super().__init__()
        self.symbols = symbols

    def get_all_positions(self):
        from types import SimpleNamespace
        return [SimpleNamespace(symbol=s, qty="1") for s in self.symbols]


def test_single_empty_position_read_does_not_evict():
    state = {"open_spreads": [spread(status="open")]}
    sync_with_broker(PositionClient([]), state)
    assert len(state["open_spreads"]) == 1  # deferred, not deleted
    assert state["empty_position_reads"] == 1


def test_second_empty_read_confirms_the_eviction():
    state = {"open_spreads": [spread(status="open")]}
    trading = PositionClient([])
    sync_with_broker(trading, state)
    sync_with_broker(trading, state)
    assert state["open_spreads"] == []


def test_a_good_read_resets_the_suspicion_counter():
    state = {"open_spreads": [spread(status="open")]}
    sync_with_broker(PositionClient([]), state)
    sync_with_broker(PositionClient(["SPY260903P00630000",
                                     "SPY260903P00625000"]), state)
    assert state["empty_position_reads"] == 0
    assert len(state["open_spreads"]) == 1


# --- Entry execution --------------------------------------------------------

def approvals(n: int) -> dict:
    return {"approved": [{"index": i, "size_factor": 1.0} for i in range(n)]}


def test_directional_gate_sees_this_cycles_own_entries(monkeypatch):
    """Three put spreads approved in one cycle used to all pass a gate whose
    whole purpose is to stop the book going one-way: open_kinds was a snapshot
    taken before the first fill."""
    monkeypatch.setattr(agent, "open_spread",
                        lambda t, c, q: {"limit_credit": 1.0, "max_loss_total": 100})
    risk = AccountRisk(equity=100_000, day_pnl=0, open_spreads=0,
                       committed_risk=0, open_kinds=())
    cands = [make_candidate(kind="put_credit") for _ in range(3)]
    opened = execute_approvals(FakeTradingClient(), {"open_spreads": []}, risk,
                               cands, approvals(3), 25_000)
    assert opened == 2
    assert risk.open_kinds == ("put_credit", "put_credit")


def test_failed_submission_does_not_stop_the_next_approval(monkeypatch):
    attempts = []

    def flaky_open(trading, cand, qty):
        attempts.append(cand.underlying)
        if len(attempts) == 1:
            raise RuntimeError("422 rejected")
        return {"limit_credit": 1.0, "max_loss_total": 100}

    monkeypatch.setattr(agent, "open_spread", flaky_open)
    risk = AccountRisk(equity=100_000, day_pnl=0, open_spreads=0,
                       committed_risk=0, open_kinds=())
    cands = [make_candidate(kind="put_credit"), make_candidate(kind="call_credit")]
    state = {"open_spreads": []}
    assert execute_approvals(FakeTradingClient(), state, risk, cands,
                             approvals(2), 25_000) == 1
    assert len(attempts) == 2


def test_every_submitted_order_is_on_disk_before_the_next_one(monkeypatch):
    """A live order missing from state.json is an unmanaged position: no stop,
    no profit target, no flatten."""
    seen_on_disk = []

    def open_and_check(trading, cand, qty):
        seen_on_disk.append(len(load_state().get("open_spreads", [])))
        return {"limit_credit": 1.0, "max_loss_total": 100}

    monkeypatch.setattr(agent, "open_spread", open_and_check)
    risk = AccountRisk(equity=100_000, day_pnl=0, open_spreads=0,
                       committed_risk=0, open_kinds=())
    cands = [make_candidate(kind="put_credit"), make_candidate(kind="call_credit")]
    execute_approvals(FakeTradingClient(), {"open_spreads": []}, risk, cands,
                      approvals(2), 25_000)
    assert seen_on_disk == [0, 1]  # the first was persisted before the second went out


# --- Retries ----------------------------------------------------------------

def test_retry_survives_a_transient_failure(no_wait):
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise ConnectionError("reset by peer")
        return "quotes"

    assert retry(flaky, what="test") == "quotes"
    assert calls["n"] == 3


def test_retry_reraises_a_persistent_outage(no_wait):
    with pytest.raises(ConnectionError):
        retry(lambda: (_ for _ in ()).throw(ConnectionError("down")), what="test")


# --- Power (the failure the watchdog cannot heal) ---------------------------

POWERCFG_AWAKE = """
Power Scheme GUID: fb5220ff  (HP Optimized)
  Subgroup GUID: 238c9fa8
    GUID Alias: SUB_SLEEP
      GUID Alias: STANDBYIDLE
    Current AC Power Setting Index: 0x00000000
    Current DC Power Setting Index: 0x00000384
      GUID Alias: HIBERNATEIDLE
    Current AC Power Setting Index: 0x00000000
"""
POWERCFG_SLEEPS = POWERCFG_AWAKE.replace(
    "      GUID Alias: STANDBYIDLE\n    Current AC Power Setting Index: 0x00000000",
    "      GUID Alias: STANDBYIDLE\n    Current AC Power Setting Index: 0x00000708")


def test_power_settings_are_parsed_per_alias():
    from theta_shepherd.preflight import _ac_sleep_settings
    assert _ac_sleep_settings(POWERCFG_AWAKE) == {"STANDBYIDLE": 0, "HIBERNATEIDLE": 0}
    assert _ac_sleep_settings(POWERCFG_SLEEPS)["STANDBYIDLE"] == 1800


def test_preflight_fails_when_the_machine_can_sleep(monkeypatch):
    from types import SimpleNamespace

    import theta_shepherd.preflight as preflight
    monkeypatch.setattr(preflight.subprocess, "run",
                        lambda *a, **k: SimpleNamespace(returncode=0,
                                                        stdout=POWERCFG_SLEEPS))
    ok, detail = preflight._check_power()
    assert not ok
    assert "standby-timeout-ac 0" in detail


def test_preflight_passes_when_sleep_is_disabled(monkeypatch):
    from types import SimpleNamespace

    import theta_shepherd.preflight as preflight
    monkeypatch.setattr(preflight.subprocess, "run",
                        lambda *a, **k: SimpleNamespace(returncode=0,
                                                        stdout=POWERCFG_AWAKE))
    assert preflight._check_power()[0]


# --- Liquidity floor --------------------------------------------------------

def test_untradeable_quote_is_rejected():
    assert illiquid(make_quote(bid=0.05, ask=0.60))


def test_normal_market_passes():
    assert not illiquid(make_quote(bid=0.95, ask=1.05))
    assert not illiquid(make_quote(bid=0.03, ask=0.07))  # cheap long leg, tight


def test_pairing_skips_a_spread_with_an_unexitable_long_leg(monkeypatch):
    short = make_quote(strike=630.0, bid=1.10, ask=1.15, delta=-0.20)
    wide_long = make_quote(strike=625.0, bid=0.05, ask=0.70, delta=-0.10)
    assert strategy._pair_spreads([short, wide_long], "put_credit", 643.0, 5.0) == []
    tight_long = make_quote(strike=625.0, bid=0.20, ask=0.25, delta=-0.10)
    assert len(strategy._pair_spreads([short, tight_long], "put_credit", 643.0, 5.0)) == 1
