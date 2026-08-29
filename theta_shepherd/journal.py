"""Decision journal (append-only JSONL) and open-position state.

Every observation, LLM decision, order, and exit is journaled — this is the
audit trail behind the hackathon write-up and demo.
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from .config import settings

STATE_FILE = settings.journal_dir / "state.json"
STATE_BACKUP = settings.journal_dir / "state.json.bak"


def _today_log() -> Path:
    return settings.journal_dir / f"{datetime.now(timezone.utc):%Y-%m-%d}.jsonl"


def log_event(kind: str, payload: dict) -> None:
    settings.journal_dir.mkdir(parents=True, exist_ok=True)
    record = {"ts": datetime.now(timezone.utc).isoformat(), "event": kind, **payload}
    with _today_log().open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, default=str) + "\n")


def load_state() -> dict:
    """Open-position state; a corrupted main file (crash mid-write on an old
    version, disk hiccup) falls back to the last good backup rather than
    silently orphaning live positions."""
    for path in (STATE_FILE, STATE_BACKUP):
        if path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                log_event("state_corrupt", {"file": str(path)})
    return {"open_spreads": []}


def save_state(state: dict) -> None:
    """Atomic write: tmp file + rename, previous version kept as .bak — a
    crash at any instant leaves a readable state file on disk."""
    settings.journal_dir.mkdir(parents=True, exist_ok=True)
    tmp = STATE_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, indent=2, default=str), encoding="utf-8")
    if STATE_FILE.exists():
        os.replace(STATE_FILE, STATE_BACKUP)
    os.replace(tmp, STATE_FILE)
