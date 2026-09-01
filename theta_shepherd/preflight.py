"""Operational readiness: a go/no-go preflight before the session, and a
self-healing health watchdog during it.

  python run_agent.py --preflight   # run before Monday's open
  python run_agent.py --health      # scheduled every 30 min in-session:
                                    # if the last cycle is stale, run one NOW
"""

import json
import re
import subprocess
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path

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


def _ac_sleep_settings(powercfg_output: str) -> dict[str, int]:
    """Alias -> AC setting index, parsed from `powercfg /q SCHEME_CURRENT
    SUB_SLEEP`. Values are seconds; 0 means never."""
    values: dict[str, int] = {}
    alias = None
    for line in powercfg_output.splitlines():
        line = line.strip()
        if line.startswith("GUID Alias:"):
            alias = line.split(":", 1)[1].strip()
        elif line.startswith("Current AC Power Setting Index:") and alias:
            try:
                values[alias] = int(line.split(":", 1)[1].strip(), 16)
            except ValueError:
                pass
    return values


def _check_power() -> tuple[bool, str]:
    """Sleep is the one failure the health watchdog cannot heal: a sleeping
    laptop runs no scheduled task, so the agent stops managing live positions
    while the market is open and nothing on the machine is awake to notice.
    Idle sleep and hibernate must be disabled on AC for the session window."""
    proc = subprocess.run(["powercfg", "/q", "SCHEME_CURRENT", "SUB_SLEEP"],
                          capture_output=True, text=True, errors="replace")
    if proc.returncode != 0:
        return False, "powercfg unavailable — cannot verify the machine stays awake"
    values = _ac_sleep_settings(proc.stdout)
    awake = {k: values[k] for k in ("STANDBYIDLE", "HIBERNATEIDLE") if k in values}
    asleep = {k: v for k, v in awake.items() if v}
    if asleep:
        fixes = " ".join(f"powercfg /change {'standby' if k == 'STANDBYIDLE' else 'hibernate'}"
                         f"-timeout-ac 0" for k in asleep)
        return False, f"machine sleeps on AC ({asleep}) — fix: {fixes}"
    return True, f"no idle sleep/hibernate on AC ({awake or 'not reported'})"


"""A task can be registered and still be incapable of running. On Mon Aug 31
all four were registered (this check passed) yet none had ever executed: the
paths were stored unquoted, so Windows tried to launch `E:\\Alapaca` and failed
with 0x80070002 every 20 min, and DisallowStartIfOnBatteries left them Queued
forever on an unplugged laptop. Registration is not readiness — verify the task
can actually launch."""
TASK_NS = {"t": "http://schemas.microsoft.com/windows/2004/02/mit/task"}
LAUNCH_FAILURE = {-2147024894, 2147942402}  # 0x80070002 — file not found


def _task_xml(name: str):
    """Task XML comes back UTF-16 from schtasks. None if not registered."""
    proc = subprocess.run(["schtasks", "/query", "/tn", name, "/xml"],
                          capture_output=True)
    if proc.returncode != 0:
        return None
    for encoding in ("utf-16", "utf-8"):
        try:
            return ET.fromstring(proc.stdout.decode(encoding).lstrip("\ufeff"))
        except (UnicodeError, ET.ParseError):
            continue
    return None


def _launched_target(root) -> str:
    """The script the action really invokes, unwrapped from any cmd.exe /c."""
    command = (root.findtext(".//t:Exec/t:Command", "", TASK_NS) or "").strip()
    args = (root.findtext(".//t:Exec/t:Arguments", "", TASK_NS) or "").strip()
    if Path(command).name.lower() != "cmd.exe":
        return command.strip('"')
    quoted = re.findall(r'"([^"]+)"', args)
    return (quoted[0] if quoted else args.removeprefix("/c").strip()).strip('"')


def _last_result(name: str) -> int | None:
    proc = subprocess.run(["schtasks", "/query", "/tn", name, "/fo", "list", "/v"],
                          capture_output=True, text=True, errors="replace")
    for line in proc.stdout.splitlines():
        if line.startswith("Last Result:"):
            try:
                return int(line.split(":", 1)[1].strip())
            except ValueError:
                return None
    return None


def _check_schtasks() -> tuple[bool, str]:
    problems = []
    for name in SCHEDULED_TASKS:
        root = _task_xml(name)
        if root is None:
            problems.append(f"{name}: not registered")
            continue
        settings_el = root.find("t:Settings", TASK_NS)
        if settings_el is not None:
            if (settings_el.findtext("t:DisallowStartIfOnBatteries", "", TASK_NS)
                    or "").lower() == "true":
                problems.append(f"{name}: won't start on battery")
            if (settings_el.findtext("t:Enabled", "", TASK_NS) or "").lower() == "false":
                problems.append(f"{name}: disabled")
        target = _launched_target(root)
        if target and not Path(target).exists():
            problems.append(f"{name}: target missing ({target})")
        if _last_result(name) in LAUNCH_FAILURE:
            problems.append(f"{name}: last run failed to launch (0x80070002)")
    return (not problems,
            "all tasks registered and launchable" if not problems
            else "; ".join(problems))


CHECKS = [
    ("env keys", _check_env),
    ("Trading API", _check_trading),
    ("Market Data API", _check_market_data),
    ("Azure OpenAI", _check_azure),
    ("alpaca-cli", _check_cli),
    ("journal", _check_journal),
    ("STOP file", _check_stop_file),
    ("scheduled tasks", _check_schtasks),
    ("power (stays awake)", _check_power),
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
