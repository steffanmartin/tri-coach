"""Mirror the run coach's TrainingPeaks plan into intervals.icu as Run events.

Runs are prescribed by a human coach in TrainingPeaks. Bike, swim and gym come
from the agent. Both have to end up on one calendar, and that calendar has to be
intervals.icu: the agent reads every number through the intervals MCP, and
handing it a second plan source is the same mistake `wellness_sync` exists to
avoid. This is the wellness sync's shape applied to the plan — pull from
upstream, upsert into intervals.icu, leave the agent unaware there was ever
another system involved.

**TrainingPeaks and not Coros**, even though these sessions land there too. The
chain is coach -> TrainingPeaks -> Coros, and Coros is the last and lossiest
link: TP holds the structure, the targets and the coach's comments, while the
Coros copy has been flattened into a training-plan entry. Reading the far end
would also buy nothing, since nothing carries Coros -> intervals.icu — the sync
job would still have to be written, just against worse input.

The fetching, the sport mapping and the %FTP/%LTHR/%threshold-pace -> absolute
watts/bpm/s-per-km conversion are all `tp-icu-sync`, pinned to a rev in
pyproject.toml. This module is the two things that package deliberately does not
have: the run-only filter, and the ownership marker that goes with it.

**Run-only is load-bearing, not a preference.** Everything TP holds for a
triathlete is visible here, including the bike and swim the agent itself
prescribed and pushed the other way. Widening `RUN_TYPES` would import those
back as a second copy of sessions intervals.icu already has, and the agent would
plan against both.

Deletes are narrow on purpose: this removes an event only when it carries our
own `tp:` external id, so nothing the agent or the athlete created is ever
touched. That is also the one exception to "never delete an intervals.icu
calendar event" in CLAUDE.md — TP is the source of truth for these, and a run
the coach withdrew has to disappear rather than linger as a session the agent
keeps grading against.

    python -m coach.trainingpeaks_sync --dry-run   # show the diff, write nothing
    python -m coach.trainingpeaks_sync             # apply
    python -m coach.trainingpeaks_sync --days 28   # look further ahead
"""
import argparse
import asyncio
import logging
import os
from dataclasses import dataclass, field
from datetime import date, timedelta

from tp_icu_sync.config import Config
from tp_icu_sync.icu.api import create_event, delete_event, list_events, update_event
from tp_icu_sync.icu.client import IcuApiError, IcuClient
from tp_icu_sync.icu.models import IcuEvent
from tp_icu_sync.mapping.sport import tp_sport_to_icu_type
from tp_icu_sync.sync import (
    EXTERNAL_ID_PREFIX,
    HASH_TAG_RE,
    TP_TYPE_DAY_OFF,
    TP_TYPE_RACE,
    build_icu_payload,
)
from tp_icu_sync.tp.api import list_workouts
from tp_icu_sync.tp.client import TPAuthError, TPClient
from tp_icu_sync.tp.models import TPWorkout

log = logging.getLogger(__name__)

# How far ahead to mirror. The coach works a week or two out; a longer window
# only widens the range in which a withdrawn session can sit as a stale event.
DEFAULT_DAYS = 14

# intervals.icu event types that count as a run. VirtualRun is TP's treadmill
# and virtual-run subtypes, which are still the coach's runs.
RUN_TYPES = frozenset({"Run", "VirtualRun"})

# Prepended to every mirrored description. This is what tells the skills the
# event is not theirs — `external_id` is the machine-readable marker, but the
# agent reads descriptions and may never see an external id through the MCP.
# Keep it byte-stable: it sits outside the tp-sync content hash, so a change
# here rewrites nothing, but a *varying* prefix would defeat reading the diff.
COACH_MARKER = (
    "COACH (TrainingPeaks) — prescribed by the run coach, mirrored automatically. "
    "Do not move, rewrite or delete this event; plan around it."
)


def enabled() -> bool:
    """Whether TP is configured at all.

    Same on-switch shape as the webhook receiver: with no cookie set this
    package behaves exactly as it did before TP existed, which is what a fresh
    checkout and every test run want.
    """
    return bool(os.environ.get("TP_AUTH_COOKIE"))


def _config() -> Config:
    """Build tp-icu-sync's config from this project's env vars.

    Constructed rather than `Config.load()`ed: that helper hunts for its own
    `.env` under three paths and expects `ICU_API_KEY`/`ICU_ATHLETE_ID`, which
    would mean a second credentials file holding a copy of keys `.env` already
    has.
    """
    athlete = os.environ["INTERVALS_ATHLETE_ID"].strip()
    return Config(
        tp_cookie=os.environ["TP_AUTH_COOKIE"].strip(),
        icu_api_key=os.environ["INTERVALS_API_KEY"].strip(),
        icu_athlete_id=athlete if athlete.startswith("i") else f"i{athlete}",
    )


def is_coach_run(w: TPWorkout) -> bool:
    """Whether a TP workout is a run session worth mirroring.

    Races and Day Off entries are excluded even when they map to Run. A TP race
    becomes a `RACE_A` event, which intervals.icu feeds into form and taper
    projections, and races are the athlete's own record in `50 Races/` — the run
    coach's calendar must not be able to reshape the season's peak. Day Off
    becomes a sport-less note, which says nothing the daily note does not.
    """
    if w.workoutTypeValueId in (TP_TYPE_DAY_OFF, TP_TYPE_RACE):
        return False
    return tp_sport_to_icu_type(w.workoutTypeValueId, w.workoutSubTypeId) in RUN_TYPES


def _tp_id(event: IcuEvent) -> int | None:
    """The TP workout id an event was mirrored from, or None if it is not ours."""
    external = event.external_id or ""
    if not external.startswith(EXTERNAL_ID_PREFIX):
        return None
    try:
        return int(external[len(EXTERNAL_ID_PREFIX) :])
    except ValueError:
        return None


def _content_hash(description: str | None) -> str | None:
    """The `[tp-sync hash=...]` footer tp-icu-sync stamps into every description.

    Comparing hashes rather than whole descriptions is what makes a re-run cheap:
    the hash covers exactly the fields being mirrored, so an unchanged session
    produces no PUT even if intervals.icu normalised the stored text.
    """
    match = HASH_TAG_RE.search(description or "")
    return match.group(1) if match else None


@dataclass
class SyncResult:
    created: int = 0
    updated: int = 0
    deleted: int = 0
    unchanged: int = 0
    errors: list[str] = field(default_factory=list)

    def __str__(self) -> str:
        return (
            f"created={self.created} updated={self.updated} "
            f"deleted={self.deleted} unchanged={self.unchanged}"
        )


def sync(days: int = DEFAULT_DAYS, dry_run: bool = False) -> SyncResult:
    """Mirror TP's runs for the next `days` days into intervals.icu.

    Blocking — call it through `asyncio.to_thread` from the scheduled jobs, whose
    loop is busy long-polling Telegram.
    """
    cfg = _config()
    today = date.today()
    end = today + timedelta(days=days)
    result = SyncResult()

    with TPClient(cfg.tp_cookie) as tp, IcuClient(cfg.icu_api_key, cfg.icu_athlete_id) as icu:
        thresholds = tp.thresholds()

        # TP returns everything in the window — bike, swim, notes, races — and
        # `list_workouts` has already dropped anything marked completed.
        planned = [w for w in list_workouts(tp, today, end) if is_coach_run(w)]
        log.info("TP: %d run session(s) in %s..%s", len(planned), today, end)

        ours = {
            tp_id: event
            for event in list_events(icu, today, end)
            if (tp_id := _tp_id(event)) is not None
        }
        log.info("intervals.icu: %d event(s) previously mirrored", len(ours))

        for w in planned:
            payload = build_icu_payload(w, thresholds)
            payload["description"] = f"{COACH_MARKER}\n\n{payload['description']}"
            existing = ours.pop(w.workoutId, None)

            if existing is None:
                log.info("+ create %s %s", w.day, payload["name"])
                if dry_run:
                    result.created += 1
                    continue
                try:
                    create_event(icu, payload)
                    result.created += 1
                except IcuApiError as exc:
                    result.errors.append(f"create wid={w.workoutId}: {exc}")
                continue

            if _content_hash(existing.description) == _content_hash(payload["description"]):
                result.unchanged += 1
                continue

            log.info("~ update %s %s", w.day, payload["name"])
            if dry_run:
                result.updated += 1
                continue
            try:
                update_event(icu, existing.id, payload)
                result.updated += 1
            except IcuApiError as exc:
                result.errors.append(f"update id={existing.id}: {exc}")

        # Whatever is left in `ours` was mirrored by an earlier run and TP no
        # longer has it as a run in this window: the coach withdrew it, moved it
        # out of range, or changed its sport. Only ever events carrying our own
        # external id — see the module docstring on why this delete is allowed.
        for tp_id, event in ours.items():
            log.info("- delete %s %s", event.start_date_local[:10], event.name)
            if dry_run:
                result.deleted += 1
                continue
            try:
                delete_event(icu, event.id)
                result.deleted += 1
            except IcuApiError as exc:
                result.errors.append(f"delete id={event.id} wid={tp_id}: {exc}")

    return result


async def main(days: int = DEFAULT_DAYS) -> None:
    """Scheduled entry point, called by the morning brief and the evening debrief.

    Failures are reported to Telegram and swallowed, never raised: a coach plan
    that did not refresh leaves yesterday's mirror in place, which is a stale
    brief — but a raise here would cost the brief entirely. The auth case is
    called out separately because it is the one that will actually happen: the
    TP cookie dies whenever the session ends, and the fix is a human pasting a
    new one into `.env`, so it must not read as a transient blip.
    """
    if not enabled():
        log.info("TP sync skipped: TP_AUTH_COOKIE not set")
        return

    from . import daily_brief

    try:
        result = await asyncio.to_thread(sync, days, False)
        log.info("TP sync: %s", result)
        if result.errors:
            await daily_brief.send(
                f"TrainingPeaks sync: {len(result.errors)} event(s) failed — "
                f"{result.errors[0]}"
            )
    except TPAuthError as exc:
        log.exception("TP sync auth failed")
        await daily_brief.send(
            "TrainingPeaks cookie expired — the run plan is no longer syncing. "
            f"Re-paste TP_AUTH_COOKIE into .env and restart. ({exc})"
        )
    except Exception as exc:
        log.exception("TP sync failed")
        await daily_brief.send(f"TrainingPeaks sync failed: {type(exc).__name__}: {exc}")


def _cli() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--days", type=int, default=DEFAULT_DAYS, help="how far ahead to mirror"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="print the diff, write nothing"
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)-7s %(message)s")
    if not enabled():
        raise SystemExit("TP_AUTH_COOKIE is not set — nothing to sync.")

    result = sync(args.days, dry_run=args.dry_run)
    print(f"\n[{'DRY-RUN' if args.dry_run else 'APPLIED'}] {result}")
    for error in result.errors:
        print(f"  - {error}")
    raise SystemExit(1 if result.errors else 0)


if __name__ == "__main__":
    _cli()
