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
    except Exception as e:
        # These snapshots are observability, not control flow — they run
        # between the exit engine and the hard guards, so anything that
        # escapes here would skip the flatten and the kill switch.
        return f"alpaca-cli unavailable: {type(e).__name__}: {e}"


def snapshot_account() -> str:
    out = _run(["trading", "account", "status"])
    log_event("cli_account_snapshot", {"output": out})
    return out


def snapshot_positions() -> str:
    out = _run(["trading", "positions", "list"])
    log_event("cli_positions_snapshot", {"output": out})
    return out


def snapshot_options(symbols: list[str]) -> str:
    """Greeks/IV spot-check on our own short legs, via the same CLI command an
    operator would run — journaled so a human can audit the agent's marks."""
    if not symbols:
        return ""
    out = _run(["data", "options", "snapshot", ",".join(symbols)])
    log_event("cli_options_snapshot", {"symbols": symbols, "output": out})
    return out


def market_clock() -> str:
    return _run(["clock"])
