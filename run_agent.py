"""Entry point.

  python run_agent.py            # one decision cycle (cron / Task Scheduler)
  python run_agent.py --loop     # run continuously, one cycle every 30 min
  python run_agent.py --force    # run a cycle even when the market is closed
  python run_agent.py --scout    # dry run: show candidates, place no orders
  python run_agent.py --retro    # nightly retrospective: journal -> lessons.md
  python run_agent.py --preflight  # go/no-go operational checks
  python run_agent.py --health     # watchdog: run a cycle if the schedule died
"""

import argparse
import time
import traceback

from rich.console import Console
from rich.table import Table

console = Console()


def scout() -> None:
    from theta_shepherd.market import MarketData
    from theta_shepherd.strategy import find_candidates

    candidates = find_candidates(MarketData())
    table = Table(title="Spread candidates (no orders placed)")
    for col in ("underlying", "kind", "expiration", "short/long", "delta", "credit", "POP", "EV/lot", "score"):
        table.add_column(col)
    for c in candidates:
        d = c.describe()
        table.add_row(d["underlying"], d["kind"], d["expiration"],
                      f"{d['short_strike']}/{d['long_strike']}", str(d["short_delta"]),
                      str(d["credit_per_share"]), str(d["pop"]), str(d["ev_per_lot"]),
                      f"{c.score:.3f}")
    console.print(table)


def main() -> None:
    parser = argparse.ArgumentParser(description="Theta Shepherd trading agent")
    parser.add_argument("--loop", action="store_true", help="run continuously")
    parser.add_argument("--interval", type=int, default=1800, help="seconds between cycles in --loop mode")
    parser.add_argument("--force", action="store_true", help="run even if market closed")
    parser.add_argument("--scout", action="store_true", help="show candidates only, no orders")
    parser.add_argument("--flatten", action="store_true", help="cancel entries and close all open spreads")
    parser.add_argument("--retro", nargs="?", const="today", metavar="YYYY-MM-DD",
                        help="run the nightly retrospective (optionally for a past date)")
    parser.add_argument("--preflight", action="store_true", help="go/no-go operational checks")
    parser.add_argument("--health", action="store_true",
                        help="watchdog: run a cycle now if the schedule went stale")
    args = parser.parse_args()

    if args.preflight:
        import sys
        from theta_shepherd.preflight import run_preflight
        sys.exit(0 if run_preflight() else 1)
    if args.health:
        from theta_shepherd.preflight import run_health
        run_health()
        return

    if args.scout:
        scout()
        return
    if args.retro:
        from datetime import date
        from theta_shepherd.retro import run_retro
        day = None if args.retro == "today" else date.fromisoformat(args.retro)
        section = run_retro(day)
        console.print(section or "[yellow]No journal events for that day — nothing to learn.[/]")
        return
    if args.flatten:
        from theta_shepherd.agent import run_flatten
        run_flatten()
        return

    from theta_shepherd.agent import run_cycle

    while True:
        try:
            run_cycle(force=args.force)
        except Exception:
            console.print_exception()
            from theta_shepherd.journal import log_event
            log_event("cycle_error", {"traceback": traceback.format_exc()})
        if not args.loop:
            break
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
