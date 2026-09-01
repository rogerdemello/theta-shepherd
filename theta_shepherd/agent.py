"""The autonomous loop: reconcile -> sync with broker -> manage exits ->
guards -> scout -> LLM gate -> risk gate -> execute. Designed to run one cycle
per invocation (cron/Task Scheduler friendly) or continuously with --loop."""

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
from .resilience import retry
from .risk import account_risk, entry_gates, satellite_gates, size_satellite, size_trade
from .strategy import find_candidates, find_satellite_candidate

console = Console()

TERMINAL = {OrderStatus.CANCELED, OrderStatus.EXPIRED, OrderStatus.REJECTED, OrderStatus.REPLACED}
REPRICE_STEP = 0.03  # credit given up per reprice of an unfilled entry
LOCK_MAX_AGE = 900   # a lock older than 15 min is from a dead process
# A cancel is a request, not an event: the order can fill while it is in
# flight. Poll for a terminal (or filled) status before acting on it.
CANCEL_CONFIRM_TRIES = 4
CANCEL_CONFIRM_DELAY = 0.4
STUCK_EXIT_ATTEMPTS = 5   # an exit this reluctant needs a human to see it
# Two consecutive empty position reads before evicting a tracked spread: one
# empty read is as likely to be a bad response as an empty account.
EVICTION_CONFIRMATIONS = 2

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
    """Cancel an order and return its settled state (it may have filled first).

    Polls until the broker reports a terminal or filled status: a cancel that
    has been *requested* is not a cancel that has *happened*, and acting on an
    order still in flight is how one spread becomes two."""
    try:
        trading.cancel_order_by_id(order_id)
    except Exception:
        pass  # already terminal
    order = retry(trading.get_order_by_id, order_id, what="get_order_by_id")
    for _ in range(CANCEL_CONFIRM_TRIES - 1):
        if order.status == OrderStatus.FILLED or order.status in TERMINAL:
            return order
        time.sleep(CANCEL_CONFIRM_DELAY)
        order = retry(trading.get_order_by_id, order_id, what="get_order_by_id")
    return order


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
    """Resolve pending entry/exit orders against their actual broker status.

    Each spread is reconciled in isolation: one unreadable order (a transient
    broker error, a bad id) must not abort the pass and leave the rest of the
    book unexamined and unmanaged for the next 20 minutes."""
    remaining: list[dict] = []
    for s in state["open_spreads"]:
        try:
            _reconcile_one(trading, s, remaining)
        except Exception:
            log_event("reconcile_error", {"client_order_id": s.get("client_order_id"),
                                          "traceback": traceback.format_exc()})
            console.print(f"[red]Reconcile failed for {s.get('short_symbol')} "
                          f"— keeping it tracked.[/]")
            remaining.append(s)  # a live spread dropped from state is unmanaged
    state["open_spreads"] = remaining


def _reconcile_one(trading, s: dict, remaining: list[dict]) -> None:
    order_id = s.get("close_order_id") or s["order_id"]
    order = retry(trading.get_order_by_id, order_id, what="get_order_by_id")

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
                return
            if final.status not in TERMINAL:
                # The cancel never settled. Replacing the order now risks both
                # of them filling — hold this one and retry next cycle.
                log_event("entry_cancel_unconfirmed",
                          {"client_order_id": s["client_order_id"],
                           "status": str(final.status)})
                remaining.append(s)
                return
            if _is_satellite(s):
                # A directional trade that didn't fill at our price is not
                # chased — the edge was the price.
                log_event("satellite_abandoned",
                          {"client_order_id": s["client_order_id"]})
                return
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
            elif final.status not in TERMINAL:
                # Same race, worse consequence: a second close order against a
                # spread whose first close then fills leaves us short the
                # inverse. Leave it closing and look again next cycle.
                log_event("exit_cancel_unconfirmed",
                          {"client_order_id": s["client_order_id"],
                           "status": str(final.status)})
                remaining.append(s)
            else:
                s["status"] = "open"  # retry the exit next pass with fresh quotes
                s["close_attempts"] = s.get("close_attempts", 0) + 1
                s.pop("close_order_id", None)
                if s["close_attempts"] >= STUCK_EXIT_ATTEMPTS:
                    log_event("exit_stuck", {"client_order_id": s["client_order_id"],
                                             "short_symbol": s["short_symbol"],
                                             "close_attempts": s["close_attempts"]})
                    console.print(f"[bold red]Exit stuck ({s['close_attempts']} "
                                  f"attempts):[/] {s['short_symbol']}")
                remaining.append(s)
    else:
        remaining.append(s)


def sync_with_broker(trading, state: dict) -> None:
    """State file vs broker positions: flag orphan legs and evict spreads whose
    legs no longer exist at the broker (e.g. closed externally).

    Eviction is destructive — an evicted spread is one the agent will never
    stop out or close again — so a positions read that comes back empty while
    we still track open spreads must be corroborated by a second cycle before
    it is believed. A partial/blank response and a flat account look
    identical over one call."""
    positions = {p.symbol: float(p.qty)
                 for p in retry(trading.get_all_positions, what="get_all_positions")
                 if len(p.symbol) > 12}  # OCC symbols only
    tracked: set[str] = set()
    open_tracked = [s for s in state["open_spreads"] if s["status"] == "open"]

    if not positions and open_tracked:
        state["empty_position_reads"] = state.get("empty_position_reads", 0) + 1
        if state["empty_position_reads"] < EVICTION_CONFIRMATIONS:
            log_event("position_read_suspect",
                      {"tracked_open": len(open_tracked),
                       "consecutive_empty_reads": state["empty_position_reads"]})
            console.print("[yellow]Broker reports no option legs while state tracks "
                          f"{len(open_tracked)} open — deferring eviction one cycle.[/]")
            return
    else:
        state["empty_position_reads"] = 0

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
    """Exit rules for every open spread. Each is managed independently and the
    state file is written as soon as an exit order exists: an unquotable leg
    or a rejected order must not cost the rest of the book its stops, and a
    close order the state file doesn't know about gets submitted twice."""
    for s in state["open_spreads"]:
        try:
            _manage_exit_one(trading, md, s)
            if s["status"] == "closing":
                save_state(state)
        except Exception:
            log_event("exit_error", {"client_order_id": s.get("client_order_id"),
                                     "short_symbol": s.get("short_symbol"),
                                     "traceback": traceback.format_exc()})
            console.print(f"[red]Exit management failed for {s.get('short_symbol')}[/]")


def _manage_exit_one(trading, md: MarketData, s: dict) -> None:
    if s["status"] != "open":
        return
    _, exp, _, _ = parse_occ(s["short_symbol"])
    dte = (exp - econ_calendar.today_et()).days

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
        return

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
    """Cancel pending entries and close every open spread aggressively.

    This is the path that must never fail halfway: it runs on the drawdown
    kill switch and at the mandatory pre-NFP flatten. One spread that throws
    (unquotable leg, rejected order) is journaled and skipped so the rest of
    the book still gets closed, and every submitted exit is persisted
    immediately."""
    console.print(f"[bold red]FLATTEN ALL — {reason}[/]")
    log_event("flatten_all", {"reason": reason})
    remaining = []
    failures = 0
    for s in state["open_spreads"]:
        try:
            if s["status"] == "pending_fill":
                _cancel_and_confirm_dead(trading, s["order_id"])
                log_event("entry_cancelled_flatten",
                          {"client_order_id": s["client_order_id"]})
                continue
            if s["status"] == "open":
                # A flatten that keeps failing pays up like any other stuck
                # exit — being flat by the deadline outranks the last cent.
                pad = max(0.10, close_pad(s.get("close_attempts", 0)))
                if _is_satellite(s):
                    value = satellite_value(md, s)
                    fallback = s.get("filled_debit", s["limit_debit"])
                    s["close_order_id"] = close_satellite(
                        trading, s, f"flatten:{reason}",
                        value if value is not None else fallback, pad=pad,
                    )
                else:
                    cost = spread_close_cost(md, s)
                    fallback = s.get("filled_credit", s["limit_credit"])
                    s["close_order_id"] = close_spread(
                        trading, s, f"flatten:{reason}",
                        cost if cost is not None else fallback, pad=pad,
                    )
                s["status"] = "closing"
                save_state(state)  # the close order id must survive a crash here
            remaining.append(s)
        except Exception:
            failures += 1
            log_event("flatten_error", {"client_order_id": s.get("client_order_id"),
                                        "short_symbol": s.get("short_symbol"),
                                        "traceback": traceback.format_exc()})
            console.print(f"[bold red]FLATTEN FAILED for {s.get('short_symbol')} "
                          f"— retried next cycle.[/]")
            remaining.append(s)  # still ours; next cycle tries again
    state["open_spreads"] = remaining
    if failures:
        log_event("flatten_incomplete", {"reason": reason, "failures": failures})
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

    clock = retry(trading.get_clock, what="get_clock")
    console.print(f"[bold]Theta Shepherd[/] | market {'OPEN' if clock.is_open else 'CLOSED'}")
    if not clock.is_open and not force:
        log_event("cycle_skipped", {"reason": "market_closed"})
        return

    state = load_state()
    reconcile(trading, state)
    save_state(state)  # adopted fills and repriced orders, before anything else can throw
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

    execute_approvals(trading, state, risk, candidates, decision, portfolio_cap)

    try:
        maybe_open_satellite(trading, md, risk, state, decision)
    except Exception:
        log_event("satellite_error", {"traceback": traceback.format_exc()})
        console.print("[red]Satellite handling failed — core book unaffected.[/]")

    save_state(state)
    log_event("cycle_end", {"open_spreads": len(state["open_spreads"])})


def execute_approvals(trading, state: dict, risk, candidates: list,
                      decision: dict, portfolio_cap: float) -> int:
    """Submit the committee's approvals through the hard gates. Returns the
    number of orders that reached the broker.

    Each approval is independent: a rejected submission skips to the next one,
    and the running risk totals — including `open_kinds`, which the
    directional-balance gate reads — are updated as we go, so the gates see
    this cycle's own fills rather than a snapshot taken before it started."""
    opened = 0
    for approval in decision["approved"]:
        cand = candidates[approval["index"]]
        qty = max(1, int(size_trade(cand) * approval["size_factor"])) if size_trade(cand) else 0
        violations = entry_gates(risk, cand, qty, portfolio_cap)
        if violations:
            console.print(f"[red]Risk gate veto:[/] {violations}")
            log_event("risk_veto", {"candidate": cand.describe(), "violations": violations})
            continue
        try:
            record = open_spread(trading, cand, qty)
        except Exception:
            # A rejected or errored submission is not a reason to abandon the
            # remaining approvals — or to lose the ones already live.
            log_event("entry_submit_error", {"candidate": cand.describe(),
                                             "traceback": traceback.format_exc()})
            console.print(f"[red]Order submission failed:[/] {cand.underlying} {cand.kind}")
            continue
        record["status"] = "pending_fill"
        state["open_spreads"].append(record)
        save_state(state)  # an order at the broker that state doesn't know about is unmanaged
        opened += 1
        risk.committed_risk += cand.max_loss * qty
        risk.open_spreads += 1
        risk.open_kinds = risk.open_kinds + (cand.kind,)
        console.print(f"[green]Opened:[/] {cand.kind} {cand.underlying} "
                      f"{cand.short.strike}/{cand.long.strike} x{qty} "
                      f"credit~{record['limit_credit']} | {approval.get('rationale', '')}")
    return opened


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
    save_state(state)
    console.print(f"[green]Satellite opened:[/] {cand.kind} {cand.underlying} "
                  f"{cand.buy.strike}/{cand.sell.strike} x{qty} "
                  f"debit~{record['limit_debit']}")


def run_dry_run() -> None:
    """Rehearse the FULL decision pipeline with zero side effects: no orders,
    no cancels, no state writes. Everything else is real — broker reads,
    market data, guards, the scout, the committee debate, the risk gates."""
    trading = make_trading_client()
    md = MarketData()
    clock = trading.get_clock()
    console.print(f"[bold]DRY RUN[/] | market {'OPEN' if clock.is_open else 'CLOSED'}")
    log_event("dry_run_start", {"market_open": clock.is_open})

    state = load_state()

    console.print("[bold]1. Broker order truth[/] (read-only)")
    for s in state["open_spreads"]:
        order_id = s.get("close_order_id") or s["order_id"]
        try:
            order = trading.get_order_by_id(order_id)
            console.print(f"   {s['client_order_id']}: journal={s['status']} "
                          f"broker={order.status} filled_avg={order.filled_avg_price}")
        except Exception as e:
            console.print(f"   {s['client_order_id']}: [red]lookup failed[/] ({e})")

    console.print("[bold]2. Positions vs state[/]")
    positions = {p.symbol: float(p.qty)
                 for p in retry(trading.get_all_positions, what="get_all_positions")
                 if len(p.symbol) > 12}
    tracked = {sym for s in state["open_spreads"]
               for sym in (s["short_symbol"], s["long_symbol"])}
    orphans = set(positions) - tracked
    console.print(f"   broker legs={len(positions)} tracked={len(tracked)} "
                  f"orphans={orphans or 'none'}")

    console.print("[bold]3. Exit engine[/] (what would it do right now?)")
    for s in state["open_spreads"]:
        if s["status"] not in ("open", "pending_fill"):
            continue
        _, exp, _, _ = parse_occ(s["short_symbol"])
        dte = (exp - econ_calendar.today_et()).days
        if _is_satellite(s):
            mark = satellite_value(md, s)
            reason = satellite_exit_reason(mark, s.get("filled_debit", s["limit_debit"]), dte)
        else:
            credit = s.get("filled_credit", s["limit_credit"])
            mark = spread_close_cost(md, s)
            reason = None
            if mark is not None and mark <= credit * (1 - settings.profit_target_frac):
                reason = "profit_target"
            elif mark is not None and mark >= credit * settings.stop_loss_mult:
                reason = "stop_loss"
            elif should_force_close(dte):
                reason = "expiry_close"
        console.print(f"   {s['short_symbol']}: mark={mark} dte={dte} → "
                      f"{'[yellow]' + reason + '[/]' if reason else 'hold'}")

    console.print("[bold]4. Risk & guards[/]")
    risk = account_risk(trading, state)
    cap = update_risk_ladder(state, risk.equity)  # state not saved → ephemeral
    console.print(f"   equity={risk.equity:,.2f} day_pnl={risk.day_pnl:+.2f} "
                  f"committed={risk.committed_risk:,.0f} ladder_cap={cap:,.0f}")
    console.print(f"   must_flatten={econ_calendar.must_flatten()} "
                  f"blackout={econ_calendar.entry_blackout()} "
                  f"stop_file={STOP_FILE.exists()} "
                  f"sessions_left={econ_calendar.sessions_remaining()}")

    console.print("[bold]5. Scout[/]")
    candidates = find_candidates(md)
    for c in candidates:
        d = c.describe()
        console.print(f"   {d['kind']} {d['underlying']} "
                      f"{d['short_strike']}/{d['long_strike']} exp={d['expiration']} "
                      f"Δ={d['short_delta']} credit={d['credit_per_share']} "
                      f"score={c.score:.3f}")
    if not candidates:
        console.print("   none (stale weekend quotes or contest horizon)")
        log_event("dry_run_end", {"would_submit": 0})
        console.print("[bold green]DRY RUN COMPLETE — nothing submitted, nothing written[/]")
        return

    console.print("[bold]6. Committee[/] (real debate, journaled)")
    account_summary = {"equity": risk.equity, "day_pnl": round(risk.day_pnl, 2),
                       "open_spreads": risk.open_spreads,
                       "committed_risk": risk.committed_risk,
                       "portfolio_risk_cap": cap,
                       "upcoming_macro_events": econ_calendar.upcoming(),
                       "sessions_remaining_before_mandatory_flatten":
                           econ_calendar.sessions_remaining()}
    headlines = md.recent_headlines(settings.underlyings + ["SPX"])
    decision = gate_decision(
        account_summary,
        [{k: s.get(k) for k in ("kind", "underlying", "short_symbol", "qty", "status")}
         for s in state["open_spreads"]],
        [c.describe() for c in candidates], headlines)
    console.print(f"   view: {decision.get('market_view', 'n/a')}")
    if decision.get("debate_summary"):
        console.print(f"   debate: {decision['debate_summary']}")

    console.print("[bold]7. Would submit[/] (orders suppressed)")
    would = 0
    for approval in decision["approved"]:
        cand = candidates[approval["index"]]
        qty = max(1, int(size_trade(cand) * approval["size_factor"])) if size_trade(cand) else 0
        violations = entry_gates(risk, cand, qty, cap)
        if violations:
            console.print(f"   [red]veto[/] {cand.underlying} {cand.kind}: {violations}")
        else:
            would += 1
            console.print(f"   [green]WOULD OPEN[/] {cand.kind} {cand.underlying} "
                          f"{cand.short.strike}/{cand.long.strike} x{qty} "
                          f"credit~{cand.credit:.2f} risk={cand.max_loss * qty:,.0f}")
    sat = decision.get("satellite")
    if sat:
        console.print(f"   satellite proposed: {sat.get('direction')} {sat.get('underlying')}")
    log_event("dry_run_end", {"would_submit": would})
    console.print("[bold green]DRY RUN COMPLETE — nothing submitted, nothing written[/]")


def run_flatten() -> None:
    """Manual flatten entry point (run_agent.py --flatten)."""
    trading = make_trading_client()
    md = MarketData()
    state = load_state()
    reconcile(trading, state)
    flatten_all(trading, md, state, "manual")
