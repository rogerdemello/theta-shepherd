"""The autonomous loop: reconcile -> sync with broker -> manage exits ->
guards -> scout -> LLM gate -> risk gate -> execute. Designed to run one cycle
per invocation (cron/Task Scheduler friendly) or continuously with --loop."""

from datetime import date

from alpaca.trading.enums import OrderStatus
from rich.console import Console

import traceback

from . import cli_ops, econ_calendar
from .committee import Committee
from .config import settings
from .execution import (
    close_spread,
    make_trading_client,
    open_spread,
    resubmit_spread,
    spread_close_cost,
)
from .journal import load_state, log_event, save_state
from .llm import Gatekeeper
from .market import MarketData, parse_occ
from .risk import account_risk, entry_gates, size_trade
from .strategy import find_candidates

console = Console()

TERMINAL = {OrderStatus.CANCELED, OrderStatus.EXPIRED, OrderStatus.REJECTED, OrderStatus.REPLACED}
REPRICE_STEP = 0.03  # credit given up per reprice of an unfilled entry


def _cancel_and_confirm_dead(trading, order_id: str):
    """Cancel an order and return its final state (it may have filled first)."""
    try:
        trading.cancel_order_by_id(order_id)
    except Exception:
        pass  # already terminal
    return trading.get_order_by_id(order_id)


def reconcile(trading, state: dict) -> None:
    """Resolve pending entry/exit orders against their actual broker status."""
    remaining = []
    for s in state["open_spreads"]:
        order_id = s.get("close_order_id") or s["order_id"]
        order = trading.get_order_by_id(order_id)

        if s["status"] == "pending_fill":
            if order.status == OrderStatus.FILLED:
                s["status"] = "open"
                s["filled_credit"] = abs(float(order.filled_avg_price or s["limit_credit"]))
                log_event("entry_filled", {"client_order_id": s["client_order_id"],
                                           "filled_credit": s["filled_credit"],
                                           "qty": s["qty"],
                                           "short_symbol": s["short_symbol"]})
                remaining.append(s)
            elif order.status in TERMINAL:
                log_event("entry_dead", {"client_order_id": s["client_order_id"],
                                         "status": str(order.status)})
            else:
                # Unfilled from a previous cycle: work the order toward the
                # executable price rather than churning it.
                final = _cancel_and_confirm_dead(trading, order_id)
                if final.status == OrderStatus.FILLED:
                    s["status"] = "open"
                    s["filled_credit"] = abs(float(final.filled_avg_price or s["limit_credit"]))
                    log_event("entry_filled", {"client_order_id": s["client_order_id"],
                                               "filled_credit": s["filled_credit"],
                                               "qty": s["qty"],
                                               "short_symbol": s["short_symbol"]})
                    remaining.append(s)
                    continue
                new_credit = round(s["limit_credit"] - REPRICE_STEP, 2)
                floor = settings.min_credit_frac * s["width"]
                if new_credit >= floor:
                    remaining.append(resubmit_spread(trading, s, new_credit))
                else:
                    log_event("entry_abandoned", {"client_order_id": s["client_order_id"],
                                                  "reason": "credit_floor"})

        elif s["status"] == "closing":
            if order.status == OrderStatus.FILLED:
                debit = abs(float(order.filled_avg_price or 0))
                pnl = (s.get("filled_credit", s["limit_credit"]) - debit) * 100 * s["qty"]
                log_event("spread_closed", {"client_order_id": s["client_order_id"],
                                            "close_debit": debit, "realized_pnl": pnl})
            else:
                final = _cancel_and_confirm_dead(trading, order_id) \
                    if order.status not in TERMINAL else order
                if final.status == OrderStatus.FILLED:
                    debit = abs(float(final.filled_avg_price or 0))
                    pnl = (s.get("filled_credit", s["limit_credit"]) - debit) * 100 * s["qty"]
                    log_event("spread_closed", {"client_order_id": s["client_order_id"],
                                                "close_debit": debit, "realized_pnl": pnl})
                else:
                    s["status"] = "open"  # retry the exit next pass with fresh quotes
                    s.pop("close_order_id", None)
                    remaining.append(s)
        else:
            remaining.append(s)
    state["open_spreads"] = remaining


def sync_with_broker(trading, state: dict) -> None:
    """State file vs broker positions: flag orphan legs and evict spreads whose
    legs no longer exist at the broker (e.g. closed externally)."""
    positions = {p.symbol: float(p.qty) for p in trading.get_all_positions()
                 if len(p.symbol) > 12}  # OCC symbols only
    tracked: set[str] = set()
    kept = []
    for s in state["open_spreads"]:
        tracked.update((s["short_symbol"], s["long_symbol"]))
        if s["status"] == "open" and s["short_symbol"] not in positions:
            log_event("spread_evicted", {"client_order_id": s["client_order_id"],
                                         "reason": "legs_missing_at_broker"})
            continue
        kept.append(s)
    state["open_spreads"] = kept

    orphans = {sym: q for sym, q in positions.items() if sym not in tracked}
    if orphans:
        console.print(f"[red]Orphan option positions (untracked):[/] {orphans}")
        log_event("orphan_positions", {"positions": orphans})


def manage_exits(trading, md: MarketData, state: dict) -> None:
    for s in state["open_spreads"]:
        if s["status"] != "open":
            continue
        credit = s.get("filled_credit", s["limit_credit"])
        cost = spread_close_cost(md, s)
        _, exp, _, _ = parse_occ(s["short_symbol"])
        dte = (exp - date.today()).days

        reason = None
        if cost is not None and cost <= credit * (1 - settings.profit_target_frac):
            reason = "profit_target"
        elif cost is not None and cost >= credit * settings.stop_loss_mult:
            reason = "stop_loss"
        elif dte <= settings.force_close_dte:
            reason = "expiry_close"

        if reason:
            s["close_order_id"] = close_spread(trading, s, reason, cost if cost is not None else credit)
            s["status"] = "closing"
            console.print(f"[yellow]Exit ({reason}):[/] {s['short_symbol']} cost={cost}")


def flatten_all(trading, md: MarketData, state: dict, reason: str) -> None:
    """Cancel pending entries and close every open spread aggressively."""
    console.print(f"[bold red]FLATTEN ALL — {reason}[/]")
    log_event("flatten_all", {"reason": reason})
    remaining = []
    for s in state["open_spreads"]:
        if s["status"] == "pending_fill":
            _cancel_and_confirm_dead(trading, s["order_id"])
            log_event("entry_cancelled_flatten", {"client_order_id": s["client_order_id"]})
        elif s["status"] == "open":
            cost = spread_close_cost(md, s)
            fallback = s.get("filled_credit", s["limit_credit"])
            s["close_order_id"] = close_spread(
                trading, s, f"flatten:{reason}",
                cost if cost is not None else fallback, pad=0.10,
            )
            s["status"] = "closing"
            remaining.append(s)
        else:
            remaining.append(s)
    state["open_spreads"] = remaining
    save_state(state)


def check_kill_switch(risk, state: dict) -> bool:
    """Track peak equity; trip on >max_drawdown_frac drawdown from peak."""
    peak = max(state.get("peak_equity", 0.0), risk.equity)
    state["peak_equity"] = peak
    if risk.equity <= peak * (1 - settings.max_drawdown_frac):
        log_event("kill_switch", {"equity": risk.equity, "peak": peak})
        return True
    return False


def update_risk_ladder(state: dict, equity: float) -> float:
    """Portfolio risk cap that starts small and earns headroom on green days.

    Uses the ET calendar date so the cap never steps mid-session (IST cycles
    cross local midnight). Returns the cap to use for this cycle."""
    today = econ_calendar.now_et().date().isoformat()
    ladder = state.get("ladder")
    if ladder is None:
        ladder = {"cap": settings.ladder_base_risk, "date": today, "ref_equity": equity}
        state["ladder"] = ladder
        log_event("risk_ladder", {"action": "init", **ladder})
    elif ladder["date"] != today:
        green = equity > ladder["ref_equity"]
        if green:
            ladder["cap"] = min(ladder["cap"] + settings.ladder_step,
                                settings.max_portfolio_risk)
        ladder.update(date=today, ref_equity=equity)
        log_event("risk_ladder", {"action": "step_up" if green else "hold", **ladder})
    return min(ladder["cap"], settings.max_portfolio_risk)


def gate_decision(account_summary: dict, open_spreads: list[dict],
                  candidates: list[dict], headlines: list[str]) -> dict:
    """Committee first; single gatekeeper as fallback if the debate errors."""
    try:
        return Committee().decide(account_summary, open_spreads, candidates, headlines)
    except Exception:
        log_event("committee_error", {"traceback": traceback.format_exc()})
        console.print("[red]Committee failed — falling back to single gatekeeper.[/]")
        return Gatekeeper().decide(account_summary, open_spreads, candidates, headlines)


def run_cycle(force: bool = False) -> None:
    trading = make_trading_client()
    md = MarketData()

    clock = trading.get_clock()
    console.print(f"[bold]Theta Shepherd[/] | market {'OPEN' if clock.is_open else 'CLOSED'}")
    if not clock.is_open and not force:
        log_event("cycle_skipped", {"reason": "market_closed"})
        return

    state = load_state()
    reconcile(trading, state)
    sync_with_broker(trading, state)
    manage_exits(trading, md, state)
    save_state(state)

    risk = account_risk(trading, state)
    portfolio_cap = update_risk_ladder(state, risk.equity)
    account_summary = {"equity": risk.equity, "day_pnl": round(risk.day_pnl, 2),
                       "open_spreads": risk.open_spreads, "committed_risk": risk.committed_risk,
                       "portfolio_risk_cap": portfolio_cap}
    log_event("cycle_start", account_summary)
    cli_ops.snapshot_account()
    cli_ops.snapshot_positions()

    # --- Hard guards, in priority order ---
    if econ_calendar.must_flatten():
        flatten_all(trading, md, state, "pre_NFP_flatten")
        return
    if check_kill_switch(risk, state):
        flatten_all(trading, md, state, "drawdown_kill_switch")
        return
    save_state(state)  # persist peak equity
    if risk.day_pnl <= -settings.daily_loss_limit:
        console.print("[red]Daily loss limit hit — no new entries today.[/]")
        log_event("halted", {"reason": "daily_loss_limit", **account_summary})
        return
    blackout = econ_calendar.entry_blackout()
    if blackout:
        console.print(f"[yellow]Entry blackout:[/] {blackout}")
        log_event("entry_blackout", {"event": blackout})
        return

    candidates = find_candidates(md)
    console.print(f"Candidates: {len(candidates)}")
    if not candidates:
        log_event("no_candidates", {})
        return

    headlines = md.recent_headlines(settings.underlyings + ["SPX"])
    account_summary["upcoming_macro_events"] = econ_calendar.upcoming()
    decision = gate_decision(
        account_summary,
        [{k: s.get(k) for k in ("kind", "underlying", "short_symbol", "qty", "status")}
         for s in state["open_spreads"]],
        [c.describe() for c in candidates],
        headlines,
    )
    console.print(f"[cyan]Committee view:[/] {decision.get('market_view', 'n/a')}")
    if decision.get("debate_summary"):
        console.print(f"[magenta]Debate:[/] {decision['debate_summary']}")

    for approval in decision["approved"]:
        cand = candidates[approval["index"]]
        qty = max(1, int(size_trade(cand) * approval["size_factor"])) if size_trade(cand) else 0
        violations = entry_gates(risk, cand, qty, portfolio_cap)
        if violations:
            console.print(f"[red]Risk gate veto:[/] {violations}")
            log_event("risk_veto", {"candidate": cand.describe(), "violations": violations})
            continue
        record = open_spread(trading, cand, qty)
        record["status"] = "pending_fill"
        state["open_spreads"].append(record)
        risk.committed_risk += cand.max_loss * qty
        risk.open_spreads += 1
        console.print(f"[green]Opened:[/] {cand.kind} {cand.underlying} "
                      f"{cand.short.strike}/{cand.long.strike} x{qty} "
                      f"credit~{record['limit_credit']} | {approval.get('rationale', '')}")

    save_state(state)
    log_event("cycle_end", {"open_spreads": len(state["open_spreads"])})


def run_flatten() -> None:
    """Manual flatten entry point (run_agent.py --flatten)."""
    trading = make_trading_client()
    md = MarketData()
    state = load_state()
    reconcile(trading, state)
    flatten_all(trading, md, state, "manual")
