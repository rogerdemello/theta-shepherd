"""Ops hardening: atomic state, cycle lock, escalating exit pads."""

import time
from types import SimpleNamespace

from alpaca.trading.enums import OrderStatus

import theta_shepherd.agent as agent
import theta_shepherd.journal as journal
from theta_shepherd.agent import close_pad, cycle_lock, reconcile
from theta_shepherd.journal import load_state, save_state

from conftest import FakeOrder, FakeTradingClient


def test_save_state_is_atomic_with_backup(tmp_journal):
    save_state({"open_spreads": [], "v": 1})
    save_state({"open_spreads": [], "v": 2})
    assert load_state()["v"] == 2
    assert (tmp_journal / "state.json.bak").exists()
    assert "1" in (tmp_journal / "state.json.bak").read_text(encoding="utf-8")
    assert not (tmp_journal / "state.json.tmp").exists()


def test_corrupt_state_falls_back_to_backup(tmp_journal):
    save_state({"open_spreads": [], "v": 1})
    save_state({"open_spreads": [], "v": 2})
    (tmp_journal / "state.json").write_text("{corrupt", encoding="utf-8")
    assert load_state()["v"] == 1


def test_missing_state_starts_empty(tmp_journal):
    assert load_state() == {"open_spreads": []}


def test_cycle_lock_blocks_concurrent_runs(tmp_path, monkeypatch):
    monkeypatch.setattr(agent, "settings", SimpleNamespace(journal_dir=tmp_path))
    (tmp_path / "cycle.lock").write_text("123", encoding="utf-8")  # fresh lock
    with cycle_lock() as acquired:
        assert acquired is False
    assert (tmp_path / "cycle.lock").exists()  # not ours to remove


def test_cycle_lock_breaks_stale_lock_and_cleans_up(tmp_path, monkeypatch):
    monkeypatch.setattr(agent, "settings", SimpleNamespace(journal_dir=tmp_path))
    lock = tmp_path / "cycle.lock"
    lock.write_text("123", encoding="utf-8")
    old = time.time() - agent.LOCK_MAX_AGE - 60
    import os
    os.utime(lock, (old, old))
    with cycle_lock() as acquired:
        assert acquired is True
        assert lock.exists()
    assert not lock.exists()


def test_close_pad_escalates_and_caps():
    assert close_pad(0) == 0.03
    assert close_pad(1) == 0.05
    assert close_pad(2) == 0.07
    assert close_pad(10) == 0.15


def test_stuck_exit_increments_close_attempts():
    trading = FakeTradingClient({"x1": FakeOrder(status=OrderStatus.NEW,
                                                 filled_avg_price=None)})
    spread = {"client_order_id": "shepherd-abc", "order_id": "o1", "qty": 2,
              "limit_credit": 0.80, "width": 5.0, "status": "closing",
              "close_order_id": "x1", "filled_credit": 1.01,
              "short_symbol": "SPY260902P00630000",
              "long_symbol": "SPY260902P00625000"}
    state = {"open_spreads": [spread]}
    reconcile(trading, state)
    assert state["open_spreads"][0]["close_attempts"] == 1
    reconcile_again = FakeTradingClient({"x2": FakeOrder(status=OrderStatus.NEW,
                                                         filled_avg_price=None)})
    state["open_spreads"][0].update(status="closing", close_order_id="x2")
    reconcile(reconcile_again, state)
    assert state["open_spreads"][0]["close_attempts"] == 2
