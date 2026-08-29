"""Risk ladder: cap starts small, earns headroom on green days only."""

from datetime import datetime

import theta_shepherd.econ_calendar as econ_calendar
from theta_shepherd.agent import update_risk_ladder
from theta_shepherd.config import settings
from theta_shepherd.econ_calendar import ET


def at_day(monkeypatch, day: int):
    monkeypatch.setattr(econ_calendar, "now_et",
                        lambda: datetime(2026, 8, day, 12, 0, tzinfo=ET))


def test_ladder_initializes_at_base(monkeypatch):
    at_day(monkeypatch, 31)
    state = {}
    assert update_risk_ladder(state, 100_000.0) == settings.ladder_base_risk
    assert state["ladder"]["ref_equity"] == 100_000.0


def test_ladder_stable_within_a_day(monkeypatch):
    at_day(monkeypatch, 31)
    state = {}
    update_risk_ladder(state, 100_000.0)
    assert update_risk_ladder(state, 105_000.0) == settings.ladder_base_risk


def test_ladder_steps_up_after_green_day(monkeypatch):
    at_day(monkeypatch, 31)
    state = {}
    update_risk_ladder(state, 100_000.0)
    monkeypatch.setattr(econ_calendar, "now_et",
                        lambda: datetime(2026, 9, 1, 12, 0, tzinfo=ET))
    cap = update_risk_ladder(state, 100_500.0)  # green day
    assert cap == settings.ladder_base_risk + settings.ladder_step


def test_ladder_holds_after_red_day(monkeypatch):
    at_day(monkeypatch, 31)
    state = {}
    update_risk_ladder(state, 100_000.0)
    monkeypatch.setattr(econ_calendar, "now_et",
                        lambda: datetime(2026, 9, 1, 12, 0, tzinfo=ET))
    assert update_risk_ladder(state, 99_500.0) == settings.ladder_base_risk


def test_ladder_rebases_when_config_base_raised(monkeypatch):
    at_day(monkeypatch, 31)
    stale = {"ladder": {"cap": settings.ladder_base_risk - 1_000.0,
                        "date": "2026-08-31", "ref_equity": 100_000.0}}
    assert update_risk_ladder(stale, 100_000.0) == settings.ladder_base_risk


def test_ladder_never_exceeds_hard_ceiling(monkeypatch):
    at_day(monkeypatch, 31)
    state = {"ladder": {"cap": settings.max_portfolio_risk,
                        "date": "2026-08-30", "ref_equity": 99_000.0}}
    assert update_risk_ladder(state, 100_000.0) == settings.max_portfolio_risk
