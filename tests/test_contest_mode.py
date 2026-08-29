"""Contest-horizon logic: expiry caps, expiry-day close timing, sessions left."""

from datetime import date, datetime

from theta_shepherd.agent import should_force_close
from theta_shepherd.config import settings
from theta_shepherd.econ_calendar import ET, sessions_remaining
from theta_shepherd.strategy import effective_max_dte


def et(*args) -> datetime:
    return datetime(*args, tzinfo=ET)


def test_effective_max_dte_capped_by_contest_end():
    # Mon Aug 31: flatten day is 3 days out — never open past it
    assert effective_max_dte(date(2026, 8, 31)) == 3
    assert effective_max_dte(date(2026, 9, 2)) == 1
    assert effective_max_dte(date(2026, 9, 3)) == 0      # below min_dte → no entries
    assert effective_max_dte(date(2026, 9, 4)) < 0


def test_effective_max_dte_uses_max_dte_when_horizon_far():
    assert effective_max_dte(date(2026, 8, 20)) == settings.max_dte


def test_expiry_day_rides_morning_theta():
    assert not should_force_close(0, et(2026, 9, 2, 10, 0))
    assert not should_force_close(0, et(2026, 9, 2, 13, 59))


def test_expiry_day_closes_in_the_afternoon():
    assert should_force_close(0, et(2026, 9, 2, 14, 0))
    assert should_force_close(0, et(2026, 9, 2, 15, 30))


def test_past_expiry_closes_regardless_of_time():
    assert should_force_close(-1, et(2026, 9, 2, 9, 31))


def test_future_expiry_never_force_closed():
    assert not should_force_close(2, et(2026, 9, 2, 15, 59))


def test_sessions_remaining_counts_down():
    assert sessions_remaining(et(2026, 8, 29, 12, 0)) == 4   # weekend, week ahead
    assert sessions_remaining(et(2026, 8, 31, 12, 0)) == 4   # Monday underway
    assert sessions_remaining(et(2026, 9, 2, 12, 0)) == 2
    assert sessions_remaining(et(2026, 9, 3, 12, 0)) == 1
    assert sessions_remaining(et(2026, 9, 3, 15, 30)) == 0   # flatten fired
    assert sessions_remaining(et(2026, 9, 4, 9, 0)) == 0
