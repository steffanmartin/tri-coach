"""Evening job: close the day out. Fixed 21:00, no waiting.

The morning brief is a prediction; this is the record. It writes
`20 Daily/YYYY-MM-DD.md` and nothing else.

**It no longer writes `30 Sessions/`, and no longer waits for uploads.** Both
changed for the same reason: `session_debrief` now runs per activity, triggered
by the intervals.icu ACTIVITY_UPLOADED webhook, so a session is analysed minutes
after it finishes instead of hours later in a batch. The old shape polled
intervals.icu from 21:00 until every planned session had an activity against it,
giving up at 23:00 — that poll existed purely to answer "is there more still
coming?" before spending one big agent run on the whole day. With the notes
already written as the day went, there is nothing left to wait for, so this runs
at 21:00 and reads what is there.

What it must still do is be honest about the gaps, and there are now two kinds:

- a planned session with no activity at all — the upload never arrived, or the
  session did not happen, and this job must not decide which
- an activity that uploaded but has no `30 Sessions/` note — the webhook did not
  reach us, or the debrief failed. Worth saying out loud, because it is the only
  place that failure becomes visible; the webhook itself is fire-and-forget.

Both are counted here and passed into the prompt rather than left for the agent
to infer, so the numbers come from the same REST reads the rest of the package
uses rather than from the model's reading of a folder listing.

    python -m coach.daily_debrief    # run it now
"""
import argparse
import asyncio
import logging
from datetime import date

from . import agent, daily_brief, intervals, session_debrief, wellness_sync

log = logging.getLogger(__name__)


def gaps(day: date) -> tuple[int, int]:
    """(planned sessions with no activity, activities with no session note).

    The first is a count, not a matching: intervals.icu does not reliably link an
    activity back to the event it fulfilled, and planned events are already
    narrowed to sports that produce an upload (`intervals.TRACKED_SPORTS`), so a
    gym-only day counts zero rather than looking like a missed session. Floored
    at zero so an unplanned extra session cannot make it negative.
    """
    activities = intervals.activities(day)
    planned = intervals.planned_workouts(day)
    missing_uploads = max(0, len(planned) - len(activities))
    undebriefed = sum(
        1
        for activity in activities
        if activity.get("id")
        and not session_debrief.already_debriefed(str(activity["id"]))
    )
    return missing_uploads, undebriefed


def prompt(missing_uploads: int = 0, undebriefed: int = 0) -> str:
    """Built per run, never at import — see the note in `daily_brief.prompt`."""
    gap = ""
    if missing_uploads:
        gap += (
            f"\n{missing_uploads} planned session(s) for today have no matching "
            "activity on intervals.icu. Say that plainly. Do not assume they were "
            "skipped, and do not invent duration, load or intervals for them — an "
            "upload that has not arrived is not the same as a session that did not "
            "happen.\n"
        )
    if undebriefed:
        gap += (
            f"\n{undebriefed} activity/activities recorded today have no note in "
            "`30 Sessions/`, which means the per-activity debrief never ran for "
            "them. Name them in the change log as un-debriefed rather than "
            "analysing them here, and report what intervals.icu holds for them at "
            "summary level only.\n"
        )
    return f"""Run the `daily-debrief` skill for {date.today().isoformat()}.
{gap}
Finish with a Telegram-ready summary between <telegram> and </telegram> tags:
max 8 short lines, no markdown headings, no emoji spam (one status emoji is fine).
"""


async def main() -> None:
    try:
        missing_uploads, undebriefed = await asyncio.to_thread(gaps, date.today())
        # Today's steps are worth writing now: unlike at 06:00, the count is
        # essentially final by the evening. `wellness_sync.main` reports its own
        # failures to Telegram, so a dead sync leaves the debrief standing.
        await wellness_sync.main(include_today_steps=True)
        reply = await agent.run(prompt(missing_uploads, undebriefed))
        header = daily_brief.header("De-brief")
        await daily_brief.send(f"{header}\n{daily_brief.extract_telegram(reply)}")
    except Exception as exc:  # never fail silently
        await daily_brief.send(f"Coach debrief failed: {type(exc).__name__}: {exc}")


def _cli() -> None:
    # No --no-wait any more: there is no wait to skip. The flag is gone rather
    # than kept as a no-op, so an old invocation fails loudly instead of looking
    # like it did something.
    argparse.ArgumentParser(description=__doc__).parse_args()
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())


if __name__ == "__main__":
    _cli()
