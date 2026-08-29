"""Read the athlete's Google Calendar. Read-only, by design and by scope.

This is the *what*; `calendar_sync` is the *where it lands*. The split mirrors
google_health / wellness_sync: a thin API client with no opinion about the
vault, and a job that shapes the result for the coach.

Which calendars to read is configurable because a Google account is usually
cluttered with things that say nothing about training availability — holiday
feeds, week numbers, birthdays. Default is the primary calendar alone; set
GOOGLE_CALENDAR_IDS to a comma-separated list to widen it.
"""
import os
import urllib.parse
from datetime import date, datetime, timedelta

import httpx

from . import google_oauth

BASE = "https://www.googleapis.com/calendar/v3/calendars"

# Three weeks: `week-planner` builds one week but needs to see the edge of the
# next one, so it does not put a long ride the day before a 06:00 flight.
DEFAULT_HORIZON_DAYS = 21


def calendar_ids() -> list[str]:
    raw = os.environ.get("GOOGLE_CALENDAR_IDS", "primary")
    return [c.strip() for c in raw.split(",") if c.strip()]


def access_token() -> str:
    """Calendar-scoped token — a separate grant from the health one."""
    return google_oauth.access_token("GOOGLE_CALENDAR_REFRESH_TOKEN")


def _declined(event: dict) -> bool:
    """True if Steffan himself declined. Someone else's decline is not his free time."""
    return any(
        a.get("self") and a.get("responseStatus") == "declined"
        for a in event.get("attendees", [])
    )


def _parse(event: dict) -> dict | None:
    """Flatten one event. All-day and timed events carry different keys."""
    start, end = event.get("start") or {}, event.get("end") or {}
    summary = (event.get("summary") or "(no title)").strip()

    if start.get("date"):  # all-day; `end.date` is exclusive
        try:
            first = date.fromisoformat(start["date"])
            last = date.fromisoformat(end.get("date") or start["date"]) - timedelta(days=1)
        except ValueError:
            return None
        return {"day": first, "last_day": max(first, last), "all_day": True,
                "start": None, "end": None, "summary": summary,
                "free": event.get("transparency") == "transparent"}

    if not start.get("dateTime"):
        return None
    try:
        begins = datetime.fromisoformat(start["dateTime"])
        finishes = datetime.fromisoformat(end.get("dateTime") or start["dateTime"])
    except ValueError:
        return None
    return {"day": begins.date(), "last_day": finishes.date(), "all_day": False,
            "start": begins, "end": finishes, "summary": summary,
            "free": event.get("transparency") == "transparent"}


def events(token: str, horizon_days: int = DEFAULT_HORIZON_DAYS) -> list[dict]:
    """Every event from now to the horizon, across the configured calendars.

    `singleEvents` expands recurring series into individual instances, which is
    the only form worth planning around.
    """
    now = datetime.now().astimezone()
    window = {
        "timeMin": now.isoformat(),
        "timeMax": (now + timedelta(days=horizon_days)).isoformat(),
        "singleEvents": "true",
        "orderBy": "startTime",
        "maxResults": 250,
    }

    out: list[dict] = []
    for cal in calendar_ids():
        page_token = None
        while True:
            params = dict(window)
            if page_token:
                params["pageToken"] = page_token
            resp = httpx.get(
                f"{BASE}/{urllib.parse.quote(cal, safe='')}/events",
                params=params,
                headers={"Authorization": f"Bearer {token}"},
                timeout=30,
            )
            resp.raise_for_status()
            body = resp.json()
            for raw in body.get("items", []):
                if raw.get("status") == "cancelled" or _declined(raw):
                    continue
                parsed = _parse(raw)
                if parsed:
                    out.append(parsed)
            page_token = body.get("nextPageToken")
            if not page_token:
                break

    out.sort(key=lambda e: (e["day"], e["start"].time() if e["start"] else datetime.min.time()))
    return out
