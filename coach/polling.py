"""Wait-for-the-data loop shared by the morning brief and the evening debrief.

Both scheduled jobs have the same shape: start at a cron time, poll an external
service until the day's data has actually landed, and give up at a deadline
rather than never running. The differences are only *what* is polled and how the
outstanding work is described, so the loop itself lives here once.

Two rules this encodes, and neither is incidental:

- A failed poll is logged and retried, never raised. One 500 from Google at 06:10
  or from intervals.icu at 21:10 must not cost the day's message.
- The loop never sleeps past the deadline — the last poll lands exactly on it.
"""
import asyncio
import logging
import os
from datetime import datetime
from typing import Any, Callable

log = logging.getLogger(__name__)


def deadline_from_env(hour_var: str, minute_var: str, hour: int, minute: int) -> datetime:
    """Wall-clock time to stop waiting, today. A deadline already in the past
    (a manual run at noon, or a misconfigured hour) means one poll, then go."""
    return datetime.now().replace(
        hour=int(os.environ.get(hour_var, hour)),
        minute=int(os.environ.get(minute_var, minute)),
        second=0,
        microsecond=0,
    )


async def poll_until(
    check: Callable[[], Any],
    on_error: Any,
    deadline: datetime,
    interval_min: int,
    label: str,
    describe: Callable[[Any], str] = str,
) -> Any:
    """Poll `check` until it returns something falsy, or until `deadline` passes.

    `check` returns what is still outstanding — an empty list, or 0, means the
    data is all there. It is run via `asyncio.to_thread` because both callers do
    blocking HTTP on the event loop the bot uses for Telegram long polling.
    `on_error` is what to assume is outstanding when the call raises, and should
    be a value that keeps the loop waiting rather than one that ends it early.

    Returns whatever was still outstanding when it stopped: falsy if the wait
    succeeded, otherwise the work the caller must report as missing.
    """
    while True:
        try:
            outstanding = await asyncio.to_thread(check)
        except Exception as exc:
            log.warning("%s poll failed, retrying: %s: %s", label, type(exc).__name__, exc)
            outstanding = on_error
        if not outstanding:
            log.info("%s: complete, running now", label)
            return outstanding
        now = datetime.now()
        if now >= deadline:
            log.warning("%s: gave up waiting for %s", label, describe(outstanding))
            return outstanding
        log.info("%s: waiting on %s; next poll in %d min",
                 label, describe(outstanding), interval_min)
        await asyncio.sleep(min(interval_min * 60, (deadline - now).total_seconds()))
