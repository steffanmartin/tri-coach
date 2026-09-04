"""Morning job: wait for the night's wellness to publish, sync it, then brief.

The old shape was two fixed cron times — sync at 06:15, brief at 06:30 — which
assumed the Fitbit had already uploaded. It usually has; on a late sync, a flat
watch, or a phone that only reconnects at breakfast, the brief graded a night
that was not there yet. So the job now starts at 06:00 and polls every 10
minutes for today's HRV, resting HR and sleep, running the moment all three
exist. At 09:00 it stops waiting and briefs anyway, naming the fields that never
arrived: a brief that is late is worse than one that is honest about a gap.

Polling Google Health rather than intervals.icu is deliberate. intervals.icu
only holds these numbers because `wellness_sync` puts them there, so polling it
would be watching our own writes. The agent is still unaware of any of this — it
reads every number back through the intervals MCP, as always.
"""
import argparse
import asyncio
import logging
import os
from datetime import date, datetime

import httpx

from . import agent, google_health, polling, telegram_format, wellness_sync

log = logging.getLogger(__name__)

# The three overnight measurements `daily-readiness` grades against. Steps are
# not here on purpose: this job never writes today's steps (the evening debrief
# does, once the count is final), so waiting on them would wait forever.
REQUIRED_FIELDS = ("hrv", "restingHR", "sleepSecs")

POLL_INTERVAL_MIN = int(os.environ.get("WELLNESS_POLL_INTERVAL_MIN", 10))


def prompt(missing: list[str] | None = None) -> str:
    """Built per run, never at import. The scheduler holds this module in memory
    for months, so a module-level f-string would freeze `date.today()` at
    container start and every later brief would ask for the startup date."""
    gap = ""
    if missing:
        gap = (
            f"\nWellness never published for today: {', '.join(missing)}. "
            "intervals.icu will have no value for those fields — say so in one "
            "line, grade readiness on what does exist, and do not infer the "
            "missing numbers or fall back to an older day's.\n"
        )
    return f"""Run the `daily-readiness` skill for {date.today().isoformat()}.
{gap}
Finish with a Telegram-ready summary between <telegram> and </telegram> tags:
max 8 short lines, no markdown headings, no emoji spam (one status emoji is fine).
"""


def _deadline() -> datetime:
    return polling.deadline_from_env(
        "DAILY_BRIEF_DEADLINE_HOUR", "DAILY_BRIEF_DEADLINE_MINUTE", 9, 0
    )


def missing_fields(day: str) -> list[str]:
    """Which overnight metrics Google Health has not published for `day` yet.

    Deliberately the same read the sync performs, just over a two-day window, so
    the poll can never disagree with what would actually be written."""
    rows = google_health.wellness_rows(1)
    row = next((r for r in rows if r.get("id") == day), {})
    return [field for field in REQUIRED_FIELDS if field not in row]


async def wait_for_wellness(deadline: datetime | None = None) -> list[str]:
    """Poll until today's overnight metrics land, or until the deadline passes.

    Returns the fields still missing — empty means the night is complete. On a
    failed read the loop assumes nothing arrived and keeps waiting rather than
    raising: one 500 from Google at 06:10 must not cost the day's brief.
    """
    day = date.today().isoformat()
    return await polling.poll_until(
        check=lambda: missing_fields(day),
        on_error=list(REQUIRED_FIELDS),
        deadline=deadline or _deadline(),
        interval_min=POLL_INTERVAL_MIN,
        label="wellness",
        describe=", ".join,
    )


def extract_telegram(reply: str) -> str:
    """Pull the `<telegram>` block out of an agent reply. Shared with
    `daily_debrief`, which asks the agent for the same envelope."""
    if "<telegram>" in reply and "</telegram>" in reply:
        return reply.split("<telegram>", 1)[1].split("</telegram>", 1)[0].strip()
    return reply[:1500]


def header(label: str) -> str:
    """Bold '<label> Thu 04/09' line, built in code rather than asked of the
    model so the date/weekday can never drift or come out mis-formatted.
    `**` is real Markdown, which `telegram_format.text_chunks` turns into a
    bold entity — shared by `daily_brief` and `daily_debrief`."""
    return f"**{label} {date.today().strftime('%a %d/%m')}**"


async def send(text: str) -> None:
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    async with httpx.AsyncClient(timeout=30) as client:
        for chunk, entities in await telegram_format.text_chunks(text):
            await client.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={
                    "chat_id": os.environ["TELEGRAM_ALLOWED_CHAT_ID"],
                    "text": chunk,
                    "entities": entities,
                },
            )


async def main(wait: bool = True) -> None:
    try:
        # A deadline of "now" collapses the wait to a single check, so the manual
        # path and the scheduled one still run the same code.
        missing = await wait_for_wellness(None if wait else datetime.now())
        # Still a 7-day window: Fitbit revises a night's HRV after the fact, and
        # the upsert picks those corrections up. `wellness_sync.main` reports its
        # own failures to Telegram, so a dead sync leaves the brief standing.
        await wellness_sync.main()
        reply = await agent.run(prompt(missing))
        await send(f"{header('Brief')}\n{extract_telegram(reply)}")
    except Exception as exc:  # never fail silently in the morning
        await send(f"Coach job failed: {type(exc).__name__}: {exc}")


def _cli() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--no-wait",
        action="store_true",
        help="brief immediately instead of waiting for today's wellness to publish",
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main(wait=not args.no_wait))


if __name__ == "__main__":
    _cli()
