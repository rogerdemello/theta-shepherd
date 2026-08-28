"""Alpaca CLI integration. The agent shells out to `alpaca-cli` for account
snapshots and market clock — the same interface an operator uses in the
terminal, so journal entries and human checks always agree."""

import subprocess

from .journal import log_event


def _run(args: list[str]) -> str:
    try:
        proc = subprocess.run(
            ["alpaca-cli", *args], capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=60,
        )
        return (proc.stdout or "").strip() or (proc.stderr or "").strip()
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        return f"alpaca-cli unavailable: {e}"


def snapshot_account() -> str:
    out = _run(["trading", "account", "status"])
    log_event("cli_account_snapshot", {"output": out})
    return out


def snapshot_positions() -> str:
    out = _run(["trading", "positions", "list"])
    log_event("cli_positions_snapshot", {"output": out})
    return out


def market_clock() -> str:
    return _run(["clock"])
