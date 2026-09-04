"""Evening job: wait for the day's sessions to upload, then close the day out.

The morning brief is a prediction; this is the record. It summarises what was
actually trained and what the body did, writes a note per activity into
`30 Sessions/`, and writes the day's `20 Daily/` note — which, unlike the brief,
is a description of a day that has happened.

It starts at 21:00 and polls for uploads rather than assuming they have landed.
A club session finishing at 19:30 reaches intervals.icu whenever the phone next
talks to Coros, which is not a time we control, and debriefing a session that
is not there yet is worse than debriefing it half an hour late. At 23:00 it
stops waiting and reports what never arrived instead of inventing it.

Polling intervals.icu here is right, and is not a contradiction of the morning
job polling Google Health instead. Wellness is in intervals.icu only because
`wellness_sync` puts it there, so polling for it would be watching our own
writes; activities come from Coros, which we do not write, so intervals.icu is
genuinely upstream of us for these.

    python -m coach.daily_debrief             # the cron path: wait, then debrief
    python -m coach.daily_debrief --no-wait   # debrief whatever is there now
"""
import argparse
import asyncio
import logging
import os
from datetime import date, datetime

from . import agent, daily_brief, intervals, polling, wellness_sync

log = logging.getLogger(__name__)

POLL_INTERVAL_MIN = int(os.environ.get("ACTIVITY_POLL_INTERVAL_MIN", 10))


def prompt(unlogged: int = 0) -> str:
    """Built per run, never at import — see the note in `daily_brief.prompt`."""
    gap = ""
    if unlogged:
        gap = (
            f"\n{unlogged} planned session(s) for today still have no matching "
            "activity on intervals.icu. Say that plainly. Do not assume they were "
            "skipped, and do not invent duration, load or intervals for them — an "
            "upload that has not arrived is not the same as a session that did not "
            "happen.\n"
        )
    return f"""Run the `daily-debrief` skill for {date.today().isoformat()}.
{gap}
Finish with a Telegram-ready summary between <telegram> and </telegram> tags:
max 8 short lines, no markdown headings, no emoji spam (one status emoji is fine).
"""


def _deadline() -> datetime:
    return polling.deadline_from_env(
        "DAILY_DEBRIEF_DEADLINE_HOUR", "DAILY_DEBRIEF_DEADLINE_MINUTE", 23, 0
    )


def pending_sessions(day: date) -> int:
    """How many of today's planned sessions have no activity recorded yet.

    A count, not a matching: intervals.icu does not reliably link an activity
    back to the event it fulfilled, and a coarse count is enough to answer the
    only question the poll asks — is there more still coming? Planned events are
    already narrowed to sports that produce an upload (see
    `intervals.TRACKED_SPORTS`), so a gym-only or rest day counts zero and
    debriefs immediately instead of waiting until 23:00 for nothing.

    Floored at zero, so an unplanned extra session does not make the count
    negative and stall the loop.
    """
    return max(0, len(intervals.planned_workouts(day)) - len(intervals.activities(day)))


async def wait_for_activities(deadline: datetime | None = None) -> int:
    """Poll until every planned session has uploaded, or until the deadline.

    Returns how many are still unaccounted for — 0 means the day is fully in.
    """
    day = date.today()
    return await polling.poll_until(
        check=lambda: pending_sessions(day),
        # Assume the whole day is outstanding on a failed read, so a transient
        # error keeps the loop waiting instead of ending it early.
        on_error=1,
        deadline=deadline or _deadline(),
        interval_min=POLL_INTERVAL_MIN,
        label="activities",
        describe=lambda n: f"{n} session(s)",
    )


async def main(wait: bool = True) -> None:
    try:
        # A deadline of "now" collapses the wait to a single check, so the manual
        # path and the scheduled one still run the same code.
        unlogged = await wait_for_activities(None if wait else datetime.now())
        # Today's steps are worth writing now: unlike at 06:00, the count is
        # essentially final by the evening. `wellness_sync.main` reports its own
        # failures to Telegram, so a dead sync leaves the debrief standing.
        await wellness_sync.main(include_today_steps=True)
        reply = await agent.run(prompt(unlogged))
        await daily_brief.send(daily_brief.extract_telegram(reply))
    except Exception as exc:  # never fail silently
        await daily_brief.send(f"Coach debrief failed: {type(exc).__name__}: {exc}")


def _cli() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--no-wait",
        action="store_true",
        help="debrief immediately instead of waiting for today's activities to upload",
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main(wait=not args.no_wait))


if __name__ == "__main__":
    _cli()
