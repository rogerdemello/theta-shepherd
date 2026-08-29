from datetime import datetime

from theta_shepherd.econ_calendar import ET, entry_blackout, must_flatten, upcoming


def et(*args) -> datetime:
    return datetime(*args, tzinfo=ET)


def test_blackout_inside_ism_window():
    assert entry_blackout(et(2026, 9, 1, 9, 45)) == "ISM Manufacturing PMI"


def test_no_blackout_on_quiet_monday_morning():
    assert entry_blackout(et(2026, 8, 31, 12, 0)) is None


def test_blackout_clears_after_release():
    assert entry_blackout(et(2026, 9, 1, 10, 1)) != "ISM Manufacturing PMI"


def test_nfp_blackout_spans_overnight():
    assert entry_blackout(et(2026, 9, 3, 16, 0)) == "Nonfarm Payrolls (NFP)"
    assert entry_blackout(et(2026, 9, 4, 8, 0)) == "Nonfarm Payrolls (NFP)"


def test_must_flatten_fires_at_sep3_1530_et():
    assert not must_flatten(et(2026, 9, 3, 15, 29))
    assert must_flatten(et(2026, 9, 3, 15, 30))
    assert must_flatten(et(2026, 9, 4, 9, 0))


def test_upcoming_shrinks_as_events_pass():
    assert len(upcoming(et(2026, 8, 31, 9, 0))) == 4
    assert len(upcoming(et(2026, 9, 3, 12, 0))) == 1  # only NFP left
    assert upcoming(et(2026, 9, 4, 12, 0)) == []
