"""Operational readiness: a go/no-go preflight before the session, and a
self-healing health watchdog during it.

  python run_agent.py --preflight   # run before Monday's open
  python run_agent.py --health      # scheduled every 30 min in-session:
                                    # if the last cycle is stale, run one NOW
"""

import json
import subprocess
from datetime import datetime, timedelta, timezone

from rich.console import Console
from rich.table import Table

from . import cli_ops
from .config import settings
from .journal import log_event

console = Console()

STALE_AFTER = timedelta(minutes=30)
SCHEDULED_TASKS = ["ThetaShepherd Cycle", "ThetaShepherd Retro",
                   "ThetaShepherd Health", "ThetaShepherd Publish"]


def _check_env() -> tuple[bool, str]:
    missing = [n for n, v in [("ALPACA_API_KEY", settings.alpaca_api_key),
                              ("ALPACA_SECRET_KEY", settings.alpaca_secret_key),
                              ("AZURE_OPENAI_ENDPOINT", settings.azure_endpoint),
                              ("AZURE_OPENAI_API_KEY", settings.azure_api_key)] if not v]
    return (not missing, "all keys present" if not missing else f"missing: {missing}")


def _check_trading() -> tuple[bool, str]:
    from .execution import make_trading_client
    clock = make_trading_client().get_clock()
    return True, f"clock ok — market {'OPEN' if clock.is_open else 'closed'}, next open {clock.next_open:%a %H:%M ET}"


def _check_market_data() -> tuple[bool, str]:
    from .market import MarketData
    price = MarketData().last_price("SPY")
    return price > 0, f"SPY last {price}"


def _check_azure() -> tuple[bool, str]:
    from .llm import azure_client, chat_json
    out = chat_json(azure_client(), 'Reply exactly {"ok": true}', "ping")
    return out.get("ok") is True, f"model {settings.azure_deployment} responded"


def _check_cli() -> tuple[bool, str]:
    out = cli_ops.market_clock()
    ok = "unavailable" not in out
    return ok, "alpaca-cli reachable" if ok else out[:80]


def _check_journal() -> tuple[bool, str]:
    log_event("preflight_probe", {})
    return True, f"journal writable at {settings.journal_dir}"


def _check_stop_file() -> tuple[bool, str]:
    from .agent import STOP_FILE
    return (not STOP_FILE.exists(),
            "no STOP file" if not STOP_FILE.exists() else f"STOP present: {STOP_FILE}")


def _check_schtasks() -> tuple[bool, str]:
    missing = []
    for name in SCHEDULED_TASKS:
        proc = subprocess.run(["schtasks", "/query", "/tn", name],
                              capture_output=True, text=True)
        if proc.returncode != 0:
            missing.append(name)
    return (not missing,
            "all scheduled tasks registered" if not missing else f"missing: {missing}")


CHECKS = [
    ("env keys", _check_env),
    ("Trading API", _check_trading),
    ("Market Data API", _check_market_data),
    ("Azure OpenAI", _check_azure),
    ("alpaca-cli", _check_cli),
    ("journal", _check_journal),
    ("STOP file", _check_stop_file),
    ("scheduled tasks", _check_schtasks),
]


def run_preflight() -> bool:
    table = Table(title="Theta Shepherd — preflight")
    table.add_column("check")
    table.add_column("status")
    table.add_column("detail")
    all_ok = True
    results = {}
    for name, fn in CHECKS:
        try:
            ok, detail = fn()
        except Exception as e:
            ok, detail = False, f"{type(e).__name__}: {e}"
        all_ok &= ok
        results[name] = {"ok": ok, "detail": detail}
        table.add_row(name, "[green]PASS[/]" if ok else "[red]FAIL[/]", detail)
    console.print(table)
    log_event("preflight", {"all_ok": all_ok, "results": results})
    console.print("[bold green]GO[/]" if all_ok else "[bold red]NO-GO — fix failures above[/]")
    return all_ok


def _last_cycle_start() -> datetime | None:
    path = settings.journal_dir / f"{datetime.now(timezone.utc):%Y-%m-%d}.jsonl"
    if not path.exists():
        return None
    latest = None
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            continue
        if e.get("event") == "cycle_start":
            latest = datetime.fromisoformat(e["ts"])
    return latest


def run_health() -> None:
    """Watchdog: when the market is open and no cycle has started within the
    staleness window, the scheduler has died — run a cycle right here.
    The cycle lockfile makes this safe against races."""
    from .agent import run_cycle
    from .execution import make_trading_client

    clock = make_trading_client().get_clock()
    if not clock.is_open:
        console.print("Health: market closed — nothing to watch.")
        return
    last = _last_cycle_start()
    age = (datetime.now(timezone.utc) - last) if last else None
    if age is not None and age < STALE_AFTER:
        console.print(f"Health: OK — last cycle {age.seconds // 60} min ago.")
        return
    console.print("[bold red]Health: cycles are STALE — self-healing by running one now.[/]")
    log_event("health_stale_cycle", {"last_cycle": str(last)})
    run_cycle()
