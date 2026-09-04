"""Read-only intervals.icu REST client.

The agent reads every number through the intervals MCP — this module exists for
the one thing the agent cannot do: let a *scheduled job* decide whether it is
worth waking the agent at all. `daily_debrief` polls here to find out if today's
sessions have finished uploading from Coros before it spends a model run on
them.

Auth is the same shape `wellness_sync.push` already uses: HTTP basic with the
literal username `API_KEY` and the key as the password.

Deliberately not a general client. Adding tools here would give the coach a
second numbers source, which is exactly what the wellness sync exists to avoid.
"""
import logging
import os
from datetime import date

import httpx

log = logging.getLogger(__name__)

BASE = "https://intervals.icu/api/v1/athlete/{athlete}"

# Which planned events are worth waiting for an upload from. Gym, mobility and
# anything else the watch does not record would otherwise hold the debrief at the
# poll until the deadline every single time, waiting for a file that is never
# coming.
TRACKED_SPORTS = frozenset({"Run", "Ride", "Swim"})


def _get(path: str, **params) -> list[dict]:
    resp = httpx.get(
        BASE.format(athlete=os.environ["INTERVALS_ATHLETE_ID"]) + path,
        auth=("API_KEY", os.environ["INTERVALS_API_KEY"]),
        params=params,
        timeout=60,
    )
    resp.raise_for_status()
    payload = resp.json()
    return payload if isinstance(payload, list) else []


def activities(day: date) -> list[dict]:
    """Activities actually recorded on `day`. Coros is the only thing writing these."""
    stamp = day.isoformat()
    return _get("/activities", oldest=stamp, newest=stamp)


def planned_workouts(day: date) -> list[dict]:
    """Planned calendar events for `day`, narrowed to sports that upload a file.

    Note this hits the REST API directly rather than going through the intervals
    MCP. That is not a workaround: this runs inside the polling loop, before
    there is an agent turn to host an MCP tool call at all. It stays REST even
    though the MCP's calendar tools work again (see the patch in the Dockerfile).
    """
    stamp = day.isoformat()
    events = _get("/events", oldest=stamp, newest=stamp, category="WORKOUT")
    return [e for e in events if e.get("type") in TRACKED_SPORTS]
