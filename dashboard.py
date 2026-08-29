"""Generate the static Theta Shepherd dashboard (docs/dashboard.html) from the
decision journal, open-position state, and (when reachable) the live account.

  python dashboard.py            # writes docs/dashboard.html
  python dashboard.py --out X    # custom output path

Self-contained output: inline CSS/JS/SVG, no external requests, light + dark.
"""

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from theta_shepherd.config import settings
from theta_shepherd.journal import load_state

ACCOUNT_ID = "PA31OBPWA7MW"


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


def live_account() -> dict | None:
    try:
        from theta_shepherd.execution import make_trading_client
        acct = make_trading_client().get_account()
        return {"equity": float(acct.equity), "last_equity": float(acct.last_equity)}
    except Exception:
        return None


TIMELINE_EVENTS = {
    "order_submitted", "entry_filled", "entry_repriced", "entry_abandoned",
    "spread_closed", "close_submitted", "risk_veto", "entry_blackout",
    "flatten_all", "kill_switch", "halted", "retrospective", "risk_ladder",
    "spread_evicted", "orphan_positions",
    "satellite_submitted", "satellite_filled", "satellite_abandoned",
    "satellite_closed", "satellite_close_submitted", "satellite_veto",
    "satellite_no_candidate",
}


def _timeline_detail(e: dict) -> str:
    k = e.get("event")
    if k == "order_submitted":
        return (f"{e.get('kind', '?')} {e.get('underlying', '?')} "
                f"{e.get('short_strike')}/{e.get('long_strike')} x{e.get('qty')} "
                f"@ {e.get('limit_credit')} credit")
    if k == "entry_filled":
        return f"filled @ {e.get('filled_credit')} credit"
    if k == "entry_repriced":
        return f"working order, new credit {e.get('new_credit')}"
    if k == "spread_closed":
        pnl = e.get("realized_pnl")
        return f"closed @ {e.get('close_debit')} debit — P&L ${pnl:+,.0f}" \
            if isinstance(pnl, (int, float)) else "closed"
    if k == "close_submitted":
        return f"{e.get('reason', '')} @ {e.get('limit_debit')} debit"
    if k == "risk_veto":
        return "; ".join(e.get("violations", []))
    if k == "entry_blackout":
        return str(e.get("event_name") or e.get("event", ""))
    if k == "risk_ladder":
        return f"{e.get('action')}: cap ${e.get('cap', 0):,.0f}"
    if k == "retrospective":
        return e.get("summary", "")[:160]
    if k == "satellite_submitted":
        return (f"{e.get('direction')} {e.get('underlying')} "
                f"{e.get('buy_strike')}/{e.get('sell_strike')} x{e.get('qty')} "
                f"@ {e.get('limit_debit')} debit")
    if k == "satellite_filled":
        return f"filled @ {e.get('filled_debit')} debit"
    if k == "satellite_closed":
        pnl = e.get("realized_pnl")
        return f"sold @ {e.get('close_credit')} — P&L ${pnl:+,.0f}" \
            if isinstance(pnl, (int, float)) else "closed"
    if k == "satellite_veto":
        return "; ".join(e.get("violations", []))
    return json.dumps({x: y for x, y in e.items() if x not in ("ts", "event")},
                      default=str)[:160]


def build_data() -> dict:
    events = read_all_events()
    state = load_state()
    acct = live_account()

    equity_series = [{"ts": e["ts"], "equity": e["equity"]}
                     for e in events if e.get("event") == "cycle_start"
                     and isinstance(e.get("equity"), (int, float))]
    if acct:
        equity_series.append({"ts": datetime.now(timezone.utc).isoformat(),
                              "equity": acct["equity"]})

    # Premium collected: filled entries joined back to their submitted qty.
    submitted = {e.get("client_order_id"): e for e in events
                 if e.get("event") == "order_submitted"}
    premium = 0.0
    for e in events:
        if e.get("event") == "entry_filled":
            sub = submitted.get(e.get("client_order_id"), {})
            qty = int(e.get("qty") or sub.get("qty") or 1)
            premium += float(e.get("filled_credit", 0)) * 100 * qty

    realized = sum(float(e.get("realized_pnl", 0)) for e in events
                   if e.get("event") in ("spread_closed", "satellite_closed"))

    open_spreads = state.get("open_spreads", [])
    committed = sum(float(s.get("max_loss_total", 0)) for s in open_spreads
                    if s.get("status") in ("open", "pending_fill", "closing"))
    ladder = state.get("ladder") or {}
    risk_cap = min(float(ladder.get("cap", settings.ladder_base_risk)),
                   settings.max_portfolio_risk)

    def _strikes(s: dict) -> str:
        if s.get("sleeve") == "satellite":
            return f"{s.get('buy_strike')}/{s.get('sell_strike')}"
        return f"{s.get('short_strike')}/{s.get('long_strike')}"

    flock = [{
        "symbol": s.get("short_symbol", ""), "kind": s.get("kind", ""),
        "underlying": s.get("underlying", ""), "qty": s.get("qty", 0),
        "strikes": _strikes(s),
        "expiration": s.get("expiration", ""),
        "credit": s.get("filled_credit", s.get("limit_credit",
                        s.get("filled_debit", s.get("limit_debit")))),
        "max_loss": s.get("max_loss_total", 0), "status": s.get("status", ""),
    } for s in open_spreads]

    closed = []
    for e in events:
        if e.get("event") == "spread_closed":
            sub = submitted.get(e.get("client_order_id"), {})
            closed.append({
                "symbol": sub.get("short_symbol", e.get("client_order_id", "")),
                "kind": sub.get("kind", ""), "underlying": sub.get("underlying", ""),
                "qty": sub.get("qty", ""), "strikes":
                    f"{sub.get('short_strike')}/{sub.get('long_strike')}",
                "expiration": sub.get("expiration", ""),
                "close_debit": e.get("close_debit"),
                "pnl": e.get("realized_pnl"), "ts": e.get("ts"),
            })

    debates = [{"ts": e["ts"], "opinions": e.get("opinions", {}),
                "decision": e.get("decision", {})}
               for e in events if e.get("event") == "committee_debate"]

    timeline = [{"ts": e["ts"], "event": e["event"], "detail": _timeline_detail(e)}
                for e in events if e.get("event") in TIMELINE_EVENTS]

    lessons_file = settings.journal_dir / "lessons.md"
    lessons = lessons_file.read_text(encoding="utf-8") if lessons_file.exists() else ""

    day_pnl = (acct["equity"] - acct["last_equity"]) if acct else None
    equity = acct["equity"] if acct else \
        (equity_series[-1]["equity"] if equity_series else None)

    return {
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "account_id": ACCOUNT_ID,
        "stats": {
            "equity": equity, "day_pnl": day_pnl, "realized_pnl": realized,
            "premium_collected": premium, "committed_risk": committed,
            "risk_cap": risk_cap, "hard_cap": settings.max_portfolio_risk,
            "open_count": sum(1 for s in open_spreads if s.get("status") == "open"),
        },
        "equity_series": equity_series,
        "flock": flock, "closed": closed,
        "debates": debates[::-1],       # newest first
        "timeline": timeline[::-1][:80],
        "lessons": lessons,
    }


def render(data: dict) -> str:
    template = Path(__file__).with_name("dashboard_template.html") \
        .read_text(encoding="utf-8")
    return template.replace("__DATA__", json.dumps(data, default=str))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="docs/dashboard.html")
    args = parser.parse_args()

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(build_data()), encoding="utf-8")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
