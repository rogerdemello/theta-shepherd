"""Competition-week economic calendar guard.

Tier-1 US macro releases during Aug 31 - Sep 4 2026. New entries are blocked
inside each event's blackout window, and the NFP release (2 hours before the
submission deadline) triggers a mandatory flatten the prior afternoon.
"""

from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")


@dataclass(frozen=True)
class EconEvent:
    name: str
    at: datetime            # release time (ET)
    blackout_from: datetime # no new entries from here until release


EVENTS = [
    EconEvent("ISM Manufacturing PMI", datetime(2026, 9, 1, 10, 0, tzinfo=ET),
              datetime(2026, 9, 1, 9, 30, tzinfo=ET)),
    EconEvent("ADP Employment", datetime(2026, 9, 2, 8, 15, tzinfo=ET),
              datetime(2026, 9, 1, 15, 30, tzinfo=ET)),
    EconEvent("Jobless Claims + ISM Services", datetime(2026, 9, 3, 10, 0, tzinfo=ET),
              datetime(2026, 9, 3, 9, 30, tzinfo=ET)),
    EconEvent("Nonfarm Payrolls (NFP)", datetime(2026, 9, 4, 8, 30, tzinfo=ET),
              datetime(2026, 9, 3, 14, 0, tzinfo=ET)),
]

# Hard flatten-everything moment: Sep 3 shortly before the close, so the book
# is flat through NFP and the equity curve is frozen before judging.
FLATTEN_AT = datetime(2026, 9, 3, 15, 30, tzinfo=ET)


def now_et() -> datetime:
    return datetime.now(ET)


def entry_blackout(now: datetime | None = None) -> str | None:
    """Returns the blocking event name if new entries are currently barred."""
    now = now or now_et()
    for e in EVENTS:
        if e.blackout_from <= now < e.at:
            return e.name
    return None


def must_flatten(now: datetime | None = None) -> bool:
    now = now or now_et()
    return now >= FLATTEN_AT


def sessions_remaining(now: datetime | None = None) -> int:
    """Trading sessions left before the mandatory flatten (inclusive of a
    session currently underway)."""
    now = now or now_et()
    session_days = [datetime(2026, 8, 31, tzinfo=ET), datetime(2026, 9, 1, tzinfo=ET),
                    datetime(2026, 9, 2, tzinfo=ET), datetime(2026, 9, 3, tzinfo=ET)]
    if now >= FLATTEN_AT:
        return 0
    return sum(1 for d in session_days if d.date() >= now.date())


def upcoming(now: datetime | None = None) -> list[str]:
    """Human-readable upcoming events, for the LLM context and journal."""
    now = now or now_et()
    return [f"{e.at:%a %b %d %H:%M} ET — {e.name}" for e in EVENTS if e.at > now]
