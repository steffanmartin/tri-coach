"""Push Fitbit Air wellness into intervals.icu so it stays the single source of numbers.

Runs shortly before the daily brief. The agent is untouched by this: it keeps
reading wellness through the intervals MCP exactly as before, and
`daily-brief` keeps getting its 60-day baselines computed by intervals.icu
rather than by the model.

Writes are upserts keyed by date, so re-running any window is safe and is the
way to correct a bad day.

    python -m coach.wellness_sync --days 90 --dry-run   # inspect, write nothing
    python -m coach.wellness_sync --days 90             # backfill
    python -m coach.wellness_sync                       # last 7 days (the morning path)
    python -m coach.wellness_sync --today-steps         # ...plus today's steps (evening)
"""
import argparse
import asyncio
import json
import logging
import os

import httpx

from . import google_health
from . import LOG_FORMAT

log = logging.getLogger(__name__)

BULK_URL = "https://intervals.icu/api/v1/athlete/{athlete}/wellness-bulk"


def push(rows: list[dict]) -> int:
    """PUT rows to intervals.icu. Raises on anything other than success —
    a wellness sync that half-works must not look like one that worked."""
    if not rows:
        return 0
    resp = httpx.put(
        BULK_URL.format(athlete=os.environ["INTERVALS_ATHLETE_ID"]),
        auth=("API_KEY", os.environ["INTERVALS_API_KEY"]),
        json=rows,
        timeout=60,
    )
    resp.raise_for_status()
    return len(rows)


def sync(days: int, dry_run: bool = False, include_today_steps: bool = False) -> list[dict]:
    rows = google_health.wellness_rows(days, include_today_steps)
    if dry_run:
        return rows
    push(rows)
    return rows


async def main(days: int = 7, include_today_steps: bool = False) -> None:
    """Scheduled entry point, called by both the morning brief and the evening
    debrief. Failures are reported, never swallowed — a silent failure here shows
    up as a missing HRV reading the coach grades around.

    Only the evening passes `include_today_steps`; see `google_health.wellness_rows`
    for why the morning must not."""
    try:
        # Off-thread: these are blocking HTTP calls and the bot's event loop is
        # busy long-polling Telegram.
        rows = await asyncio.to_thread(sync, days, False, include_today_steps)
        log.info("wellness sync: wrote %d days", len(rows))
    except Exception as exc:
        log.exception("wellness sync failed")
        from . import daily_brief

        await daily_brief.send(f"Wellness sync failed: {type(exc).__name__}: {exc}")


def _cli() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=7, help="lookback window (max 90)")
    parser.add_argument("--dry-run", action="store_true", help="print rows, write nothing")
    parser.add_argument(
        "--today-steps",
        action="store_true",
        help="also write today's step count (only correct once the day is over)",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)
    rows = sync(args.days, dry_run=args.dry_run, include_today_steps=args.today_steps)

    print(json.dumps(rows, indent=2))
    missing = [k for k in ("hrv", "restingHR", "sleepSecs", "steps")
               if not any(k in r for r in rows)]
    print(f"\n{len(rows)} day(s) {'to write' if args.dry_run else 'written'}")
    if missing:
        print(f"WARNING: no values at all for {', '.join(missing)} — check the "
              f"Google Health app covers this window, and that the scopes were granted.")


if __name__ == "__main__":
    _cli()
