"""Debrief one completed activity, as soon as it lands.

This is the per-activity half of the evening job, pulled out so it can run the
moment Coros uploads rather than waiting for 21:00. `daily_debrief` no longer
writes `30 Sessions/` at all — it summarises the notes this module has already
written — so this is now the **only** writer of a session note.

Deliberately trigger-agnostic. `webhook.py` calls it on ACTIVITY_UPLOADED, and
the `/debrief` Telegram command still goes through `agent.run` directly; nothing
here knows or cares which woke it. That seam is the point: if intervals.icu
webhooks ever stop being viable, a poller can call `debrief_activity` on the
same terms without touching the debrief logic.

Idempotency is the whole problem here, because a webhook is not a promise of
exactly-once delivery: intervals.icu re-fires with exponential backoff until it
gets a 2xx, so the same activity can arrive twice. Two guards:

- `already_debriefed` greps `30 Sessions/` for the activity id in a note's
  frontmatter. The vault is the state store, so the record of "this was done"
  is the note itself — no side table to fall out of step with what exists, and
  deleting a note is all it takes to get it rebuilt.
- `_in_flight` covers the window the first guard cannot: between starting a run
  and the note being committed, the vault still says nothing has been written.
"""
import logging

from . import agent, daily_brief, vault

log = logging.getLogger(__name__)

SESSIONS = "30 Sessions"

# Activity ids currently being debriefed by this process. `already_debriefed`
# cannot see these yet — the note does not exist until the agent turn finishes
# and commits — and a redelivery three seconds after the first POST is exactly
# the case that would otherwise start a second, concurrent run for one session.
_in_flight: set[str] = set()


def already_debriefed(activity_id: str) -> bool:
    """True if `30 Sessions/` already holds a note for this activity.

    Matches on the `activity_id:` frontmatter field rather than the filename,
    which is a date-and-slug and says nothing about which upload produced it.
    `session-debrief` is required to write that field — see the skill.
    """
    folder = vault.VAULT_PATH / SESSIONS
    if not folder.is_dir():
        return False
    needle = f"activity_id: {activity_id}"
    for note in folder.glob("*.md"):
        try:
            if needle in note.read_text(encoding="utf-8", errors="ignore"):
                return True
        except OSError as exc:  # a note being rewritten under us is not fatal
            log.warning("could not read %s: %s", note, exc)
    return False


def prompt(activity_id: str, name: str | None, sport: str | None) -> str:
    """Built per call, never at import — the scheduler and the webhook server
    both hold this module in memory for months. Same reason as `daily_brief.prompt`."""
    described = " ".join(filter(None, (sport, name))) or "the activity"
    return f"""Run the `session-debrief` skill on intervals.icu activity {activity_id} ({described}).

Write the session note to `{SESSIONS}/`, and put `activity_id: {activity_id}` in
its frontmatter — that field is how a redelivery of this same activity is
recognised as already handled, so the note is not usable without it.

Do not write `20 Daily/`. The evening debrief owns the daily note and will read
this one when it closes the day out.

Finish with a Telegram-ready summary between <telegram> and </telegram> tags:
max 8 short lines, no markdown headings, no emoji spam (one status emoji is fine).
"""


async def debrief_activity(
    activity_id: str, name: str | None = None, sport: str | None = None
) -> bool:
    """Debrief one activity and send it to Telegram. True if a run happened.

    Returns False rather than raising when the activity has already been
    debriefed, so a redelivery is a no-op the caller can acknowledge normally.
    """
    if activity_id in _in_flight:
        log.info("%s: already being debriefed, skipping", activity_id)
        return False
    _in_flight.add(activity_id)
    try:
        # Pull before the check, not after: Obsidian and the scheduled jobs both
        # push to this repo, so the local tree may not yet know about a note
        # written elsewhere. `agent.run` pulls again on its own.
        vault.pull()
        if already_debriefed(activity_id):
            log.info("%s: note already in %s, skipping", activity_id, SESSIONS)
            return False
        log.info("%s: debriefing", activity_id)
        reply = await agent.run(prompt(activity_id, name, sport))
        await daily_brief.send(
            f"{daily_brief.header('Session')}\n{daily_brief.extract_telegram(reply)}"
        )
        return True
    except Exception as exc:  # never fail silently — same rule as the daily jobs
        await daily_brief.send(
            f"Session debrief failed for {activity_id}: {type(exc).__name__}: {exc}"
        )
        return False
    finally:
        _in_flight.discard(activity_id)
