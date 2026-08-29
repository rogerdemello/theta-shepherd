"""Nightly retrospective: the shepherd learns from its own journal.

After the close, an LLM reads the day's decision journal and distills a few
concrete lessons into journal/lessons.md. The Trading Committee is handed the
most recent lessons at every future decision — so a mistake made on Monday
changes how the agent argues on Tuesday.
"""

import json
from datetime import date, datetime, timezone

from .config import settings
from .journal import log_event
from .llm import azure_client, chat_json

LESSONS_FILE = settings.journal_dir / "lessons.md"

# Bulky terminal snapshots add tokens but no decisions; the LLM never needs them.
SKIP_EVENTS = {"cli_account_snapshot", "cli_positions_snapshot"}
MAX_EVENTS = 250
MAX_FIELD_CHARS = 400

RETRO_PROMPT = """You are the nightly retrospective process of an autonomous
options premium-selling agent (credit spreads on liquid ETFs, Alpaca paper
account, one-week P&L competition). You receive today's full decision journal:
cycles, candidates, committee debates, orders, fills, exits, guard triggers.

Write the day's lessons for tomorrow's trading committee. Be concrete and
falsifiable — name underlyings, deltas, credits, times, events. Good lessons
sound like "QQQ call side at 0.22 delta filled instantly but sat at a loss
within an hour — prefer <=0.18 delta on the call side while momentum is up",
not "be careful with risk".

Respond ONLY with JSON:
{"summary": "<2-3 sentence narrative of the day>",
 "lessons": ["<lesson 1>", "<lesson 2>", ...],   // 3-6 items
 "keep_doing": ["<1-2 things that worked>"]}"""


def _compact(event: dict) -> dict:
    """Truncate long string fields so a day's journal fits in one prompt."""
    out = {}
    for k, v in event.items():
        if isinstance(v, str) and len(v) > MAX_FIELD_CHARS:
            v = v[:MAX_FIELD_CHARS] + "…"
        elif isinstance(v, dict):
            v = _compact(v)
        out[k] = v
    return out


def read_journal(day: date) -> list[dict]:
    path = settings.journal_dir / f"{day:%Y-%m-%d}.jsonl"
    if not path.exists():
        return []
    events = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            continue
        if e.get("event") in SKIP_EVENTS:
            continue
        events.append(_compact(e))
    return events[-MAX_EVENTS:]


def run_retro(day: date | None = None) -> str:
    """Distill `day`'s journal into lessons.md; returns the markdown section."""
    day = day or datetime.now(timezone.utc).date()
    events = read_journal(day)
    if not events:
        return ""

    result = chat_json(
        azure_client(), RETRO_PROMPT,
        json.dumps({"date": day.isoformat(), "journal": events}, indent=1),
        temperature=0.3,
    )
    lessons = [str(x) for x in result.get("lessons", [])]
    keep = [str(x) for x in result.get("keep_doing", [])]
    summary = result.get("summary", result.get("_error", ""))
    if not lessons and not summary:
        return ""

    section = f"## {day.isoformat()}\n\n{summary}\n\n"
    if lessons:
        section += "**Lessons:**\n" + "".join(f"- {l}\n" for l in lessons)
    if keep:
        section += "\n**Keep doing:**\n" + "".join(f"- {k}\n" for k in keep)

    settings.journal_dir.mkdir(parents=True, exist_ok=True)
    existing = LESSONS_FILE.read_text(encoding="utf-8") if LESSONS_FILE.exists() else \
        "# Shepherd's lessons\n\nWritten nightly by the retrospective; read by the committee.\n"
    # Re-running a retro for the same day replaces that day's section.
    parts = [p for p in existing.split("\n## ") if not p.startswith(day.isoformat())]
    existing = "\n## ".join(parts).rstrip()
    LESSONS_FILE.write_text(existing + "\n\n" + section, encoding="utf-8")

    log_event("retrospective", {"date": day.isoformat(), "summary": summary,
                                "lessons": lessons, "keep_doing": keep})
    return section


def load_lessons(max_days: int = 3) -> str:
    """The most recent daily sections of lessons.md, for committee prompts."""
    if not LESSONS_FILE.exists():
        return "No lessons recorded yet (first sessions)."
    parts = LESSONS_FILE.read_text(encoding="utf-8").split("\n## ")
    days = parts[1:]  # parts[0] is the file header
    return "\n\n## ".join(days[-max_days:]) if days else "No lessons recorded yet."
