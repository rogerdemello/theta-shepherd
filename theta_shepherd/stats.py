"""Contest tally, computed from the journal rather than counted by hand.

Every 【】 placeholder in WRITEUP.md, the slides, the video script and the
submission form is filled from one command:

    python run_agent.py --stats

Hand-counting trades out of a 1,000-line JSONL at 6 PM on deadline day is how
a submission ends up quoting a number the audit trail contradicts.
"""

import json
from datetime import datetime, timezone

from .config import settings

START_EQUITY = 100_000.0  # the paper account's opening balance


def _normalize(e: dict) -> dict:
    """Adapt first-session records written before the event-key fix: they used
    'kind' as the event name, and order submissions had it clobbered by the
    candidate's own kind (call_credit/put_credit)."""
    if "event" not in e and "kind" in e:
        if e["kind"] in ("call_credit", "put_credit") and "order_id" in e:
            e["event"] = "order_submitted"
        else:
            e["event"] = e["kind"]
    return e


def read_all_events() -> list[dict]:
    events = []
    for path in sorted(settings.journal_dir.glob("*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                events.append(_normalize(json.loads(line)))
            except json.JSONDecodeError:
                continue
    return events


def max_drawdown(equity_series: list[dict]) -> float:
    """Worst peak-to-trough decline as a fraction. Mark-to-market on short
    options is noisy intraday, so this is an upper bound on the real pain —
    quote it as such."""
    peak = worst = 0.0
    for point in equity_series:
        equity = float(point["equity"])
        peak = max(peak, equity)
        if peak > 0:
            worst = max(worst, (peak - equity) / peak)
    return worst


def _pnls(events: list[dict]) -> list[float]:
    return [float(e["realized_pnl"]) for e in events
            if e.get("event") in ("spread_closed", "satellite_closed")
            and isinstance(e.get("realized_pnl"), (int, float))]


def compute_stats(events: list[dict], state: dict | None = None,
                  live_equity: float | None = None,
                  lessons: str | None = None) -> dict:
    """Every number the submission quotes, derived from the audit trail."""
    state = state or {}
    equity_series = [{"ts": e["ts"], "equity": float(e["equity"])} for e in events
                     if e.get("event") == "cycle_start"
                     and isinstance(e.get("equity"), (int, float))]
    if live_equity is not None:
        equity_series.append({"ts": datetime.now(timezone.utc).isoformat(),
                              "equity": live_equity})
    equity = (live_equity if live_equity is not None
              else (equity_series[-1]["equity"] if equity_series else START_EQUITY))

    submitted = {e.get("client_order_id"): e for e in events
                 if e.get("event") == "order_submitted"}
    premium = 0.0
    for e in events:
        if e.get("event") == "entry_filled":
            sub = submitted.get(e.get("client_order_id"), {})
            qty = int(e.get("qty") or sub.get("qty") or 1)
            premium += float(e.get("filled_credit", 0)) * 100 * qty

    pnls = _pnls(events)
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]

    debates = [e for e in events if e.get("event") == "committee_debate"]
    approvals = sum(len(e.get("decision", {}).get("approved", [])) for e in debates)
    no_trade = sum(1 for e in debates
                   if not e.get("decision", {}).get("approved"))

    def count(*names: str) -> int:
        return sum(1 for e in events if e.get("event") in names)

    if lessons is None:
        lessons_file = settings.journal_dir / "lessons.md"
        lessons = lessons_file.read_text(encoding="utf-8") if lessons_file.exists() else ""

    underlyings = sorted({e.get("underlying") for e in submitted.values()
                          if e.get("underlying")})

    return {
        "equity": round(equity, 2),
        "total_pnl": round(equity - START_EQUITY, 2),
        "total_pnl_pct": round((equity - START_EQUITY) / START_EQUITY * 100, 3),
        "realized_pnl": round(sum(pnls), 2),
        "premium_collected": round(premium, 2),
        "max_drawdown_pct": round(max_drawdown(equity_series) * 100, 2),
        "spreads_submitted": len(submitted),
        "spreads_filled": count("entry_filled", "satellite_filled"),
        "spreads_closed": len(pnls),
        "wins": len(wins), "losses": len(losses),
        "win_rate_pct": round(len(wins) / len(pnls) * 100, 1) if pnls else 0.0,
        "avg_win": round(sum(wins) / len(wins), 2) if wins else 0.0,
        "avg_loss": round(sum(losses) / len(losses), 2) if losses else 0.0,
        "best_trade": round(max(pnls), 2) if pnls else 0.0,
        "worst_trade": round(min(pnls), 2) if pnls else 0.0,
        "underlyings": underlyings,
        "cycles": count("cycle_start"),
        "debates": len(debates),
        "committee_approvals": approvals,
        "committee_no_trade_rulings": no_trade,
        "risk_gate_vetoes": count("risk_veto", "satellite_veto"),
        "entry_blackouts": count("entry_blackout"),
        "flattens": count("flatten_all"),
        "kill_switch_trips": count("kill_switch"),
        "lessons_days": lessons.count("\n## "),
        "open_now": sum(1 for s in state.get("open_spreads", [])
                        if s.get("status") == "open"),
    }


def _money(value: float, signed: bool = False) -> str:
    """-1234.5 -> -$1,234.50 (the sign belongs outside the currency symbol)."""
    sign = "-" if value < 0 else ("+" if signed else "")
    return f"{sign}${abs(value):,.2f}"


def format_report(s: dict) -> str:
    """Markdown block; the values map 1:1 onto the 【】 in the submission docs."""
    return f"""# Theta Shepherd — contest tally
_Generated {datetime.now(timezone.utc):%Y-%m-%d %H:%M UTC} from the decision journal._

## Headline (for the write-up, slides 7, video close)

| Metric | Value |
|---|---|
| Final equity | {_money(s['equity'])} |
| Total P&L | {_money(s['total_pnl'], signed=True)} ({s['total_pnl_pct']:+.2f}% on $100k) |
| Realized P&L (closed) | {_money(s['realized_pnl'], signed=True)} |
| Premium collected | {_money(s['premium_collected'])} |
| Max drawdown (mark-to-market) | {s['max_drawdown_pct']:.2f}% |
| Spreads closed | {s['spreads_closed']} ({s['wins']}W / {s['losses']}L) |
| Win rate | {s['win_rate_pct']:.1f}% |
| Avg win / avg loss | {_money(s['avg_win'], signed=True)} / {_money(s['avg_loss'], signed=True)} |
| Best / worst trade | {_money(s['best_trade'], signed=True)} / {_money(s['worst_trade'], signed=True)} |
| Underlyings traded | {', '.join(s['underlyings']) or 'none'} |

## Agent behaviour (the "knew when not to trade" story)

| Metric | Value |
|---|---|
| Decision cycles run | {s['cycles']} |
| Committee debates | {s['debates']} |
| Trades approved by the committee | {s['committee_approvals']} |
| No-trade rulings | {s['committee_no_trade_rulings']} |
| Hard risk-gate vetoes | {s['risk_gate_vetoes']} |
| Econ-calendar entry blackouts | {s['entry_blackouts']} |
| Flatten events | {s['flattens']} |
| Kill-switch trips | {s['kill_switch_trips']} |
| Nightly retrospectives written | {s['lessons_days']} |
| Spreads open right now | {s['open_now']} |
"""


def run_stats() -> str:
    from .journal import load_state
    live = None
    try:
        from .execution import make_trading_client
        live = float(make_trading_client().get_account().equity)
    except Exception:
        pass  # journal-only tally still works offline
    return format_report(compute_stats(read_all_events(), load_state(), live))
