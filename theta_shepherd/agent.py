"""The autonomous loop: reconcile -> sync with broker -> manage exits ->
guards -> scout -> LLM gate -> risk gate -> execute. Designed to run one cycle
per invocation (cron/Task Scheduler friendly) or continuously with --loop."""

from datetime import date

from alpaca.trading.enums import OrderStatus
from rich.console import Console

import os
import time
import traceback
from contextlib import contextmanager

from . import cli_ops, econ_calendar
from .committee import Committee
from .config import settings
from .execution import (
    close_satellite,
    close_spread,
    make_trading_client,
    open_satellite,
    open_spread,
    resubmit_spread,
    satellite_value,
    spread_close_cost,
)
from .journal import load_state, log_event, save_state
from .llm import Gatekeeper
from .market import MarketData, parse_occ
from .risk import account_risk, entry_gates, satellite_gates, size_satellite, size_trade
from .strategy import find_candidates, find_satellite_candidate

console = Console()

TERMINAL = {OrderStatus.CANCELED, OrderStatus.EXPIRED, OrderStatus.REJECTED, OrderStatus.REPLACED}
REPRICE_STEP = 0.03  # credit given up per reprice of an unfilled entry
LOCK_MAX_AGE = 900   # a lock older than 15 min is from a dead process

# Manual emergency brake: `touch STOP` in the project root halts new entries
# (exits and guards keep running); delete the file to resume.
STOP_FILE = settings.journal_dir.parent / "STOP"


@contextmanager
def cycle_lock():
    """One decision cycle at a time: an overlapping scheduler firing or a
    manual run alongside it must never double-submit orders. Yields False
    (skip) when another live cycle holds the lock; stale locks are broken."""
    lock = settings.journal_dir / "cycle.lock"
    if lock.exists() and time.time() - lock.stat().st_mtime < LOCK_MAX_AGE:
        log_event("cycle_skipped", {"reason": "another_cycle_running"})
        yield False
        return
    settings.journal_dir.mkdir(parents=True, exist_ok=True)
    lock.write_text(str(os.getpid()), encoding="utf-8")
    try:
        yield True
    finally:
        lock.unlink(missing_ok=True)


def _cancel_and_confirm_dead(trading, order_id: str):
    """Cancel an order and return its final state (it may have filled first)."""
    try:
        trading.cancel_order_by_id(order_id)
    except Exception:
        pass  # already terminal
    return trading.get_order_by_id(order_id)


def _is_satellite(s: dict) -> bool:
    return s.get("sleeve") == "satellite"


def _adopt_fill(s: dict, avg_price) -> None:
    """Mark a pending entry as open with its actual fill price."""
    s["status"] = "open"
    if _is_satellite(s):
        s["filled_debit"] = abs(float(avg_price or s["limit_debit"]))
        log_event("satellite_filled", {"client_order_id": s["client_order_id"],
                                       "filled_debit": s["filled_debit"],
                                       "qty": s["qty"],
                                       "long_symbol": s["long_symbol"]})
    else:
        s["filled_credit"] = abs(float(avg_price or s["limit_credit"]))
        log_event("entry_filled", {"client_order_id": s["client_order_id"],
                                   "filled_credit": s["filled_credit"],
                                   "qty": s["qty"],
                                   "short_symbol": s["short_symbol"]})


def _log_closed(s: dict, avg_price) -> None:
    """Journal a filled exit with its realized P&L."""
    px = abs(float(avg_price or 0))
    if _is_satellite(s):
        pnl = (px - s.get("filled_debit", s["limit_debit"])) * 100 * s["qty"]
        log_event("satellite_closed", {"client_order_id": s["client_order_id"],
                                       "close_credit": px, "realized_pnl": pnl})
    else:
        pnl = (s.get("filled_credit", s["limit_credit"]) - px) * 100 * s["qty"]
        log_event("spread_closed", {"client_order_id": s["client_order_id"],
                                    "close_debit": px, "realized_pnl": pnl})


def reconcile(trading, state: dict) -> None:
    """Resolve pending entry/exit orders against their actual broker status."""
    remaining = []
    for s in state["open_spreads"]:
        order_id = s.get("close_order_id") or s["order_id"]
        order = trading.get_order_by_id(order_id)

        if s["status"] == "pending_fill":
            if order.status == OrderStatus.FILLED:
                _adopt_fill(s, order.filled_avg_price)
                remaining.append(s)
            elif order.status in TERMINAL:
                log_event("entry_dead", {"client_order_id": s["client_order_id"],
                                         "status": str(order.status)})
            else:
                # Unfilled from a previous cycle: work the order toward the
                # executable price rather than churning it.
                final = _cancel_and_confirm_dead(trading, order_id)
                if final.status == OrderStatus.FILLED:
                    _adopt_fill(s, final.filled_avg_price)
                    remaining.append(s)
                    continue
                if _is_satellite(s):
                    # A directional trade that didn't fill at our price is not
                    # chased — the edge was the price.
                    log_event("satellite_abandoned",
                              {"client_order_id": s["client_order_id"]})
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
                _log_closed(s, order.filled_avg_price)
            else:
                final = _cancel_and_confirm_dead(trading, order_id) \
                    if order.status not in TERMINAL else order
                if final.status == OrderStatus.FILLED:
                    _log_closed(s, final.filled_avg_price)
                else:
                    s["status"] = "open"  # retry the exit next pass with fresh quotes
                    s["close_attempts"] = s.get("close_attempts", 0) + 1
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


def close_pad(attempts: int) -> float:
    """Exit orders pay up as retries mount — a stop that isn't filling is a
    position still bleeding: 0.03, 0.05, 0.07 … capped at 0.15."""
    return round(min(0.03 + 0.02 * attempts, 0.15), 2)


def should_force_close(dte: int, now_et=None) -> bool:
    """Expiry-day spreads ride the morning's accelerated theta (profit target
    and stop still run every cycle) but never the final-hours gamma: hard
    close from force_close_et_hour onward. Anything past expiry closes now."""
    if dte < settings.force_close_dte:
        return True
    if dte == settings.force_close_dte:
        now = now_et or econ_calendar.now_et()
        return now.hour >= settings.force_close_et_hour
    return False


def satellite_exit_reason(value: float | None, debit: float, dte: int) -> str | None:
    """Exit rule for the directional sleeve: take the win at 1.5x the debit,
    cut at half, never carry into the final day."""
    if value is not None and value >= debit * settings.satellite_profit_mult:
        return "profit_target"
    if value is not None and value <= debit * settings.satellite_stop_mult:
        return "stop_loss"
    if dte <= settings.satellite_force_close_dte:
        return "expiry_close"
    return None


def manage_exits(trading, md: MarketData, state: dict) -> None:
    for s in state["open_spreads"]:
        if s["status"] != "open":
            continue
        _, exp, _, _ = parse_occ(s["short_symbol"])
        dte = (exp - date.today()).days

        if _is_satellite(s):
            value = satellite_value(md, s)
            debit = s.get("filled_debit", s["limit_debit"])
            reason = satellite_exit_reason(value, debit, dte)
            if reason:
                s["close_order_id"] = close_satellite(
                    trading, s, reason, value if value is not None else debit,
                    pad=close_pad(s.get("close_attempts", 0)))
                s["status"] = "closing"
                console.print(f"[yellow]Satellite exit ({reason}):[/] "
                              f"{s['long_symbol']} value={value}")
            continue

        credit = s.get("filled_credit", s["limit_credit"])
        cost = spread_close_cost(md, s)

        reason = None
        if cost is not None and cost <= credit * (1 - settings.profit_target_frac):
            reason = "profit_target"
        elif cost is not None and cost >= credit * settings.stop_loss_mult:
            reason = "stop_loss"
        elif should_force_close(dte):
            reason = "expiry_close"

        if reason:
            s["close_order_id"] = close_spread(trading, s, reason,
                                               cost if cost is not None else credit,
                                               pad=close_pad(s.get("close_attempts", 0)))
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
            if _is_satellite(s):
                value = satellite_value(md, s)
                fallback = s.get("filled_debit", s["limit_debit"])
                s["close_order_id"] = close_satellite(
                    trading, s, f"flatten:{reason}",
                    value if value is not None else fallback, pad=0.10,
                )
            else:
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
    if ladder is not None and ladder["cap"] < settings.ladder_base_risk:
        # Config raised the base after this ladder was persisted — the base
        # is a floor, never a haircut on earned headroom.
        ladder["cap"] = settings.ladder_base_risk
        log_event("risk_ladder", {"action": "rebase", **ladder})
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
    with cycle_lock() as acquired:
        if not acquired:
            console.print("[yellow]Another cycle holds the lock — skipping.[/]")
            return
        _run_cycle(force)


def _run_cycle(force: bool = False) -> None:
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
    cli_ops.snapshot_options([s["short_symbol"] for s in state["open_spreads"]
                              if s.get("status") == "open"][:6])

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
    if STOP_FILE.exists():
        console.print("[red]STOP file present — exits managed, no new entries.[/]")
        log_event("halted", {"reason": "manual_stop_file"})
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
    account_summary["sessions_remaining_before_mandatory_flatten"] = \
        econ_calendar.sessions_remaining()
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

    maybe_open_satellite(trading, md, risk, state, decision)

    save_state(state)
    log_event("cycle_end", {"open_spreads": len(state["open_spreads"])})


def maybe_open_satellite(trading, md: MarketData, risk, state: dict,
                         decision: dict) -> None:
    """Open the directional sleeve only when the committee proposed it AND all
    three personas independently called the same direction (verified in
    committee.py) AND the hard sleeve gates pass."""
    sat = decision.get("satellite")
    if not sat:
        return
    console.print(f"[bold cyan]Satellite proposed:[/] {sat.get('direction')} "
                  f"{sat.get('underlying')} — {sat.get('rationale', '')}")
    cand = find_satellite_candidate(md, sat["underlying"], sat["direction"])
    if cand is None:
        log_event("satellite_no_candidate", {"proposal": sat})
        return
    qty = size_satellite(cand)
    has_sat = any(_is_satellite(s) for s in state["open_spreads"])
    violations = satellite_gates(risk, cand, qty, has_sat)
    if violations:
        console.print(f"[red]Satellite veto:[/] {violations}")
        log_event("satellite_veto", {"candidate": cand.describe(),
                                     "violations": violations})
        return
    record = open_satellite(trading, cand, qty)
    record["status"] = "pending_fill"
    state["open_spreads"].append(record)
    console.print(f"[green]Satellite opened:[/] {cand.kind} {cand.underlying} "
                  f"{cand.buy.strike}/{cand.sell.strike} x{qty} "
                  f"debit~{record['limit_debit']}")


def run_flatten() -> None:
    """Manual flatten entry point (run_agent.py --flatten)."""
    trading = make_trading_client()
    md = MarketData()
    state = load_state()
    reconcile(trading, state)
    flatten_all(trading, md, state, "manual")
