"""Decision journal (append-only JSONL) and open-position state.

Every observation, LLM decision, order, and exit is journaled — this is the
audit trail behind the hackathon write-up and demo.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

from .config import settings

STATE_FILE = settings.journal_dir / "state.json"


def _today_log() -> Path:
    return settings.journal_dir / f"{datetime.now(timezone.utc):%Y-%m-%d}.jsonl"


def log_event(kind: str, payload: dict) -> None:
    settings.journal_dir.mkdir(parents=True, exist_ok=True)
    record = {"ts": datetime.now(timezone.utc).isoformat(), "event": kind, **payload}
    with _today_log().open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, default=str) + "\n")


def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return {"open_spreads": []}


def save_state(state: dict) -> None:
    settings.journal_dir.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2, default=str), encoding="utf-8")
