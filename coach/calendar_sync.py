"""Snapshot Google Calendar into the vault so the agent can read it as a file.

The agent has no network and no Bash — only Read/Write/Edit/Glob/Grep and the
intervals MCP. So the calendar arrives the way training numbers arrive at
intervals.icu: synced in by plain Python, then read as ordinary vault content.
`week-planner` consults it before placing a session.

The file is machine-owned: nothing else writes `00 Meta/calendar.md`, so it
never collides with Obsidian's auto-commit, and the agent treats it as read-only
input alongside the other `00 Meta/` files.

Rewritten only when the content actually changes, so an unchanged calendar does
not produce a commit on every message. The window line doubles as the freshness
stamp — its start date is the day the snapshot was last taken.

    python -m coach.calendar_sync --dry-run    # print it, write nothing
    python -m coach.calendar_sync              # refresh the vault file
"""
import argparse
import logging
from datetime import date, timedelta

from . import google_calendar, vault

log = logging.getLogger(__name__)

SNAPSHOT = "00 Meta/calendar.md"


def _when(event: dict) -> str:
    if event["all_day"]:
        if event["last_day"] > event["day"]:
            return f"all day (through {event['last_day'].isoformat()})"
        return "all day"
    start = event["start"].strftime("%H:%M")
    end = event["end"].strftime("%H:%M") if event["end"] else ""
    if event["end"] and event["end"].date() > event["start"].date():
        end += f" +{(event['end'].date() - event['start'].date()).days}d"
    return f"{start}–{end}" if end else start


def render(events: list[dict], horizon_days: int) -> str:
    """Markdown grouped by day. Days with nothing on them are listed as free —
    an absent day is ambiguous, and the coach needs to tell "no events" apart
    from "not synced"."""
    today = date.today()
    last = today + timedelta(days=horizon_days)
    by_day: dict[date, list[dict]] = {}
    for event in events:
        by_day.setdefault(event["day"], []).append(event)

    lines = [
        "# Calendar",
        "",
        f"Synced from Google Calendar. Window {today.isoformat()} → {last.isoformat()}.",
        "Read-only input: do not edit, it is overwritten on every sync.",
        "",
    ]
    for offset in range(horizon_days + 1):
        day = today + timedelta(days=offset)
        lines.append(f"## {day.isoformat()} ({day.strftime('%a')})")
        todays = by_day.get(day, [])
        if not todays:
            lines.append("- nothing scheduled")
        for event in todays:
            free = "  (marked free)" if event["free"] else ""
            lines.append(f"- {_when(event)} — {event['summary']}{free}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def refresh(horizon_days: int = google_calendar.DEFAULT_HORIZON_DAYS,
            dry_run: bool = False) -> tuple[str, bool]:
    """Returns (markdown, changed). Caller decides what to do with a failure."""
    token = google_calendar.access_token()
    body = render(google_calendar.events(token, horizon_days), horizon_days)
    if dry_run:
        return body, False

    path = vault.VAULT_PATH / SNAPSHOT
    if path.exists() and path.read_text() == body:
        return body, False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body)
    return body, True


def refresh_quietly() -> None:
    """Best-effort refresh for the top of an agent turn.

    Never raises: Google being unreachable must not take the bot down with it.
    The stale snapshot stays in place and its window line shows its age, which
    the coach can see and mention.
    """
    try:
        _, changed = refresh()
        if changed:
            log.info("calendar snapshot updated")
    except Exception as exc:
        log.warning("calendar refresh failed, using stale snapshot: %s", exc)


def _cli() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=google_calendar.DEFAULT_HORIZON_DAYS,
                        help="how far ahead to look (default: %(default)s)")
    parser.add_argument("--dry-run", action="store_true", help="print it, write nothing")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)
    body, changed = refresh(args.days, dry_run=args.dry_run)
    print(body)
    if args.dry_run:
        print(f"--- dry run, {SNAPSHOT} not written")
    else:
        print(f"--- {SNAPSHOT} {'updated' if changed else 'already current'}")


if __name__ == "__main__":
    _cli()
