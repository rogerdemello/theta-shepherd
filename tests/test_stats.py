"""The contest tally: the numbers the submission quotes must come from the
audit trail, and must survive first-session records written with the old
event key."""

from theta_shepherd.stats import _normalize, compute_stats, format_report, max_drawdown


def cycle(ts: str, equity: float) -> dict:
    return {"ts": ts, "event": "cycle_start", "equity": equity}


EVENTS = [
    cycle("2026-08-31T13:00:00Z", 100_000),
    {"ts": "2026-08-31T13:01:00Z", "event": "order_submitted",
     "client_order_id": "a", "underlying": "QQQ", "kind": "put_credit", "qty": 5},
    {"ts": "2026-08-31T13:05:00Z", "event": "entry_filled",
     "client_order_id": "a", "filled_credit": 1.00, "qty": 5},
    {"ts": "2026-08-31T14:00:00Z", "event": "committee_debate",
     "decision": {"approved": [{"index": 0}]}},
    {"ts": "2026-08-31T14:30:00Z", "event": "committee_debate",
     "decision": {"approved": []}},
    {"ts": "2026-08-31T15:00:00Z", "event": "risk_veto", "violations": ["cap"]},
    cycle("2026-09-01T13:00:00Z", 99_500),          # the trough
    {"ts": "2026-09-01T14:00:00Z", "event": "spread_closed",
     "client_order_id": "a", "realized_pnl": 250.0},
    {"ts": "2026-09-01T14:30:00Z", "event": "spread_closed",
     "client_order_id": "b", "realized_pnl": -120.0},
    cycle("2026-09-01T15:00:00Z", 100_400),
]


def test_headline_numbers_come_from_the_journal():
    s = compute_stats(EVENTS)
    assert s["equity"] == 100_400
    assert s["total_pnl"] == 400
    assert s["total_pnl_pct"] == 0.4
    assert s["realized_pnl"] == 130.0        # +250 and -120
    assert s["premium_collected"] == 500.0   # 1.00 x 100 x 5
    assert s["spreads_closed"] == 2
    assert (s["wins"], s["losses"]) == (1, 1)
    assert s["win_rate_pct"] == 50.0
    assert s["best_trade"] == 250.0 and s["worst_trade"] == -120.0
    assert s["underlyings"] == ["QQQ"]


def test_behaviour_numbers_count_the_refusals():
    s = compute_stats(EVENTS)
    assert s["cycles"] == 3
    assert s["debates"] == 2
    assert s["committee_approvals"] == 1
    assert s["committee_no_trade_rulings"] == 1
    assert s["risk_gate_vetoes"] == 1


def test_max_drawdown_is_peak_to_trough():
    assert max_drawdown([{"equity": 100_000}, {"equity": 99_500},
                         {"equity": 100_400}]) == 0.005
    assert max_drawdown([]) == 0.0


def test_live_equity_overrides_the_last_journalled_cycle():
    s = compute_stats(EVENTS, live_equity=101_000)
    assert s["equity"] == 101_000
    assert s["total_pnl"] == 1_000


def test_first_session_records_are_normalized():
    """Session-1 events used `kind` as the event key, and order submissions had
    it clobbered by the candidate's own kind."""
    assert _normalize({"kind": "cycle_start"})["event"] == "cycle_start"
    assert _normalize({"kind": "put_credit", "order_id": "x"})["event"] \
        == "order_submitted"


def test_report_renders_every_headline_number():
    report = format_report(compute_stats(EVENTS, lessons=""))
    for fragment in ("$100,400.00", "+$400.00", "-$120.00", "50.0%", "QQQ"):
        assert fragment in report


def test_losses_read_as_negative_dollars_not_dollar_minus():
    from theta_shepherd.stats import _money
    assert _money(-1234.5) == "-$1,234.50"
    assert _money(1234.5, signed=True) == "+$1,234.50"
