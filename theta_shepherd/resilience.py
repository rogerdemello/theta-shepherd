"""Transient-failure handling for the broker and market-data APIs.

A cycle that dies on one HTTP 500 from the quote endpoint is a cycle that
manages no exits: every open spread then rides unstopped until the next
scheduled run 20 minutes later. Reads are idempotent, so retry them.

ONLY reads. Never wrap `submit_order` or `cancel_order_by_id` — a retried
submit that actually succeeded the first time is a duplicate position.
"""

import time

from .journal import log_event

RETRY_ATTEMPTS = 3
RETRY_BASE_DELAY = 0.6  # seconds; doubles per attempt


def retry(fn, *args, what: str = "", attempts: int = RETRY_ATTEMPTS,
          base_delay: float = RETRY_BASE_DELAY, **kwargs):
    """Call an idempotent read, retrying with exponential backoff. Re-raises
    the last exception once the attempts are spent — a persistent outage must
    still surface, not be silently swallowed."""
    label = what or getattr(fn, "__name__", "api_call")
    last: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            return fn(*args, **kwargs)
        except Exception as e:  # noqa: BLE001 — the point is to survive anything
            last = e
            log_event("api_retry", {"what": label, "attempt": attempt,
                                    "error": f"{type(e).__name__}: {e}"})
            if attempt < attempts:
                time.sleep(base_delay * 2 ** (attempt - 1))
    raise last  # type: ignore[misc]
