# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

An always-on triathlon coach for one athlete (Steffan). A Telegram bot long-polls
for messages, hands each one to the Claude Agent SDK, and the agent reasons over
two data sources: **intervals.icu** (all numbers, via MCP) and a **git-backed
Obsidian vault** (all memory, via plain file tools). There is no database — the
vault repo *is* the state store. The process serves exactly one HTTP endpoint,
the intervals.icu webhook receiver, and nothing else.

## Commands

```bash
docker compose up -d --build          # build + run the bot (the only real "run" path)
docker compose logs -f
docker compose exec coach python -m coach.daily_brief --no-wait  # brief now, don't wait for wellness
docker compose exec coach python -m coach.daily_debrief          # close today out now (no wait to skip)
docker compose exec coach python -m coach.wellness_sync --days 7   # pull HRV/RHR/sleep now
docker compose exec coach python -m coach.calendar_sync --dry-run  # see the calendar snapshot
docker compose exec coach python -m coach.trainingpeaks_sync --dry-run  # see the run coach's diff
```

One-off setup for the Google grant (laptop, needs a browser once):

```bash
uv run python scripts/google_auth.py --scopes health   # mint GOOGLE_HEALTH_REFRESH_TOKEN
uv run python scripts/google_auth.py --scopes calendar # mint GOOGLE_CALENDAR_REFRESH_TOKEN
uv run python -m coach.wellness_sync --days 90 --dry-run  # check before writing
uv run python -m coach.wellness_sync --days 90            # backfill
```

Local runs need every var in `.env.example` exported, plus `VAULT_PATH` pointed
at a real cloned vault and the `claude` CLI + `uv` on PATH (the Dockerfile
installs both; the SDK shells out to the CLI):

```bash
uv sync
# Once: the intervals MCP is a build-time install in Docker, not a `uvx` fetch at
# runtime, so a local checkout needs the same pinned+patched copy on PATH. Keep
# this in step with the Dockerfile — it is the same package, rev and patch.
uv tool install --with "fastmcp<3" \
  "intervals-icu-mcp @ git+https://github.com/eddmann/intervals-icu-mcp@cb91d4a"
f="$(uv tool dir)"/intervals-icu-mcp/lib/python*/site-packages/intervals_icu_mcp/tools/events.py
sed -i '' -E 's/datetime\.strptime\((date|workout\.start_date_local), "%Y-%m-%d"\)/datetime.fromisoformat(\1)/' $f
# `sed -E` is the one form that means the same thing to BSD and GNU sed; the BRE
# spelling silently no-ops on macOS. Same check the Dockerfile makes.
! grep -q 'strptime(date\|strptime(workout' $f || echo "PATCH DID NOT APPLY"

uv run python -m coach.telegram_bot
```

Only `agent.run` talks to the MCP, so `wellness_sync`, `calendar_sync` and the
debrief's polling all work locally without that install.

There is no test suite, linter, or CI. Verification is manual: `/status` in
Telegram for the bot path, `python -m coach.daily_brief --no-wait` and
`python -m coach.daily_debrief` for the scheduled paths. Both write to the vault,
so a successful run leaves a commit behind.

For the webhook path, `/debrief` in Telegram exercises the same
`session-debrief` skill without needing an upload. To test delivery itself, POST
a payload shaped like the real one and watch for a `30 Sessions/` commit:

```bash
curl -sS -X POST http://localhost:8080/intervals/webhook \
  -H 'Content-Type: application/json' \
  -d '{"secret":"'"$INTERVALS_WEBHOOK_SECRET"'","events":[{"athlete_id":"'"$INTERVALS_ATHLETE_ID"'",
       "type":"ACTIVITY_UPLOADED","activity":{"id":"i123","name":"Test","type":"Run"}}]}'
```

It answers `accepted 1` immediately — that is delivery acknowledged, not the
debrief finished; the run happens after the response. A real id that already has
a note is a no-op, which is the dedupe working, not a failure.

## Architecture

**One process, four entry points.** `coach/telegram_bot.py:main` starts the
polling loop, an in-process `AsyncIOScheduler` holding two cron jobs
(`daily_brief.main` at 06:00, `daily_debrief.main` at 21:00), and the webhook
receiver (`webhook.serve`) on its own thread. Deliberate: the container is
already always-on, so separate scheduler infra would be wasted. This also means
**the host must not scale to zero** — long polling dies with the process, and
with it both jobs and the listener.

**Every request funnels through `agent.run`** (`coach/agent.py`), which is the
only place the SDK is touched. It wraps each turn in `vault.pull()` before and
`vault.commit_and_push()` after, so the agent's writes land in git automatically
and never diverge from what Obsidian sees. Each call is a fresh `query()` — there
is no conversation memory across messages; continuity comes entirely from the
agent re-reading the vault.

**Behaviour lives in markdown, not Python.** `agent.options()` sets
`setting_sources=["project"]` with `cwd=vault.VAULT_PATH`, and compose mounts
`./.claude` to `/vault/.claude`. So the skills in `.claude/skills/` are loaded
from *inside the vault* at runtime. Changing coaching logic means editing a
SKILL.md, not the Python. The Telegram commands are thin: `/today`, `/week`,
`/debrief`, `/day` are one-line prompts that just name a skill.

**Vault folder ownership is a hard contract**, enforced in `SYSTEM_PROMPT` and
mirrored in the skills. The agent writes only `10 Plan/`, `20 Daily/`,
`30 Sessions/`; `00 Meta/` is read-only input; `40 Journal/` and `50 Races/` are
the athlete's alone. This split is what keeps Obsidian's auto-commit and the
agent's commits from ever conflicting — do not widen the agent's write scope
without rethinking that. `00 Meta/calendar.md` is the one machine-written file:
`calendar_sync` owns it outright, nothing else writes it, and the agent reads it
like any other `00 Meta/` input.

**Wellness is synced in, not read live.** Coros supplies activities only. All
four wellness fields — `hrv`, `restingHR`, `sleepSecs`, `steps` — come from a
Fitbit Air via the Google Health API, and `coach/wellness_sync.py` PUTs them to
intervals.icu's `wellness-bulk` endpoint. Both scheduled jobs call it, and they
differ on one field: steps. HRV, resting HR and sleep are overnight measurements
and are final whenever either job runs, but steps accumulate through the day, so
at 06:00 writing today's would replace a real total with a near-zero. The morning
therefore skips today's steps and the evening debrief writes them
(`include_today_steps`). The agent is deliberately unaware of all this: it still reads every
number through the intervals MCP, so "numbers come from intervals.icu" stays
literally true and `daily-brief` gets its 60-day baselines computed by
intervals.icu rather than by the model. Writes are upserts keyed by date, so
re-running a window corrects it. **Do not give the agent a second numbers
source** — that is the whole point of the sync.

**The brief waits for the data instead of guessing when it lands.** There is no
fixed 06:30 send and no sync-runs-N-minutes-earlier lead any more; both were bets
on the watch having uploaded by a certain clock time, and a late Fitbit sync used
to hand `daily-brief` a night that did not exist yet. `daily_brief.main` now
starts at `DAILY_BRIEF_CRON_HOUR/MINUTE` (06:00), polls Google Health every
`WELLNESS_POLL_INTERVAL_MIN` (10) for today's `hrv`, `restingHR` and `sleepSecs`,
and the moment all three are published runs `wellness_sync` and then the brief.
At `DAILY_BRIEF_DEADLINE_HOUR/MINUTE` (09:00) it stops waiting and briefs anyway,
passing the missing field names into the prompt so the agent says what is absent
rather than grading around it — a late brief is worse than an honest one. Two
things to keep straight when editing this: it polls **Google Health, not
intervals.icu**, because intervals only holds these numbers once our own sync
writes them, so polling it would be watching our own writes; and a failed poll is
logged and retried, never raised, so one Google 500 at 06:10 does not cost the
day's brief. Steps are excluded from the wait on purpose — the morning does not
write them, so waiting on them would wait forever.

**Sessions are debriefed on upload, not in a nightly batch.** The intervals.icu
ACTIVITY_UPLOADED webhook POSTs to `coach/webhook.py`, which hands the activity
to `coach/session_debrief.py:debrief_activity` — one agent turn, one
`30 Sessions/` note, one Telegram message, minutes after the session ends. This
is the **only** writer of `30 Sessions/`.

Four things about that receiver are load-bearing:

- **It acknowledges before it works.** intervals.icu re-fires with exponential
  backoff until it gets a 2xx, and an agent turn takes tens of seconds, so
  holding the connection open would earn a retry and the retry would debrief the
  same session twice. The handler verifies, schedules, and returns 200. Never
  make it await the debrief. It also never returns 204, which intervals.icu has
  historically treated as a failure.
- **Idempotency lives in the vault, not a side table.** `already_debriefed`
  greps `30 Sessions/` for the `activity_id:` frontmatter field, so the record of
  "this was done" is the note itself; delete a note and it gets rebuilt. An
  in-process `_in_flight` set covers the gap before the note is committed. This
  is why `session-debrief` is *required* to write `activity_id` — a note without
  it means the next delivery debriefs the session again.
- **It fails closed.** No `INTERVALS_WEBHOOK_SECRET`, no listening socket. That
  is what makes the code safe to run on a laptop and safe to ship ahead of the
  webhook being registered.
- **`agent.run` is serialised** by a module-level lock. An upload can land
  mid-debrief, and two turns would rebase onto each other's half-written git
  state. Do not remove that lock to make things feel faster.

The receiver is stdlib `ThreadingHTTPServer` on purpose: a few POSTs a day from
one source did not justify putting a web framework in the dependencies of a
process whose only other inbound path is long polling.

**The debrief closes the day, and owns the daily note.** `daily_debrief.main`
runs at a fixed `DAILY_DEBRIEF_CRON_HOUR/MINUTE` (21:00) and writes
`20 Daily/YYYY-MM-DD.md` — nothing else. It used to poll intervals.icu until
every planned session had uploaded, giving up at 23:00; that wait existed only to
decide when to spend one big agent run on the whole day, and with notes written
as uploads land there is nothing left to wait for. **Do not reintroduce the
wait, and do not let this job write `30 Sessions/`** — it would produce a second
note for sessions that already have one.

What it must still do is name the gaps, and `daily_debrief.gaps` counts two
kinds: planned sessions with no activity (the upload never came, or the session
did not happen — the job must not decide which), and activities with no session
note (the webhook never arrived, or its debrief failed). The second is the only
place a silently-lost webhook becomes visible, since delivery is
fire-and-forget. Both counts go into the prompt as facts rather than being left
for the model to infer. `coach/intervals.py` is that read path — a single
snapshot now, not a loop — and it is not a second numbers source for the agent,
which still reads everything through the MCP. Planned events are narrowed to
Run/Ride/Swim (`intervals.TRACKED_SPORTS`) because gym and mobility never produce
an upload and would otherwise always look like a missed session. It uses REST
rather than the MCP because it runs before there is an agent turn to host a tool
call.

**The daily note is written once, in the evening.** `20 Daily/YYYY-MM-DD.md` used
to be written at 06:00 by `daily-brief`, which meant the vault's record of a
day was a prediction that nothing ever reconciled. Now `daily-debrief` is its
sole writer and `daily-brief` writes nothing to the vault: **do not restore its
`20 Daily/` write**, or the two jobs will fight over one file. Each file has
exactly one writer — `20 Daily/` the evening job, `30 Sessions/` the webhook
path, `00 Meta/calendar.md` `calendar_sync` — and that is what keeps them from
ever conflicting. The cost of this is that the
morning's reasoning prose is not archived; what survives is the Telegram message
and, when a session was changed, the `COACH:` note `daily-brief` puts on the
intervals.icu event description. That note is now load-bearing — it is what the
evening reads to judge execution against what was actually prescribed, rather
than against the untouched plan.

**The calendar is snapshotted, not queried.** The agent has no Bash and no
network tools, so `coach/calendar_sync.py` renders the next three weeks of
Google Calendar into `00 Meta/calendar.md` and the agent Reads it like any other
note. `agent.run` refreshes it after `vault.pull()` on *every* turn, not in the
`/week` handler, because `week-planner` is reachable by plain text too. The
refresh is best-effort: a Google outage leaves the stale snapshot in place
rather than taking the bot down, and the file is only rewritten when its content
changes, so an unchanged calendar produces no commit. Note that Steffan's
calendar contains real training (squad sessions), so entries are not uniformly
obstacles — `week-planner` is told to treat those as already-committed sessions.

**The run coach plans in TrainingPeaks, and it is mirrored in, not read live.**
Steffan's running is prescribed by a human coach in TrainingPeaks; everything
else is the agent's. `coach/trainingpeaks_sync.py` pulls TP's planned sessions
for the next 14 days, keeps only the runs, and upserts them onto the
intervals.icu calendar as `WORKOUT` events carrying a `tp:<id>` external id.
Both scheduled jobs call it. The agent is deliberately unaware there is a second
planning system: it reads these like any other calendar event through the MCP,
so "the plan lives on intervals.icu" stays literally true — the same trick, and
the same reason, as `wellness_sync`.

**Read TrainingPeaks, not Coros, even though the sessions land there too.** The
chain is coach -> TrainingPeaks -> Coros, and Coros is the last and lossiest
link: TP holds the structure, the targets and the coach's comments, while the
Coros copy has been flattened into a training-plan entry. Reading the far end
would also buy nothing, because nothing carries Coros -> intervals.icu — the
sync job has to exist either way, so it may as well read the good copy.

**Run-only is a correctness constraint, not a preference.** TP holds bike and
swim for a triathlete too, including sessions the agent itself prescribed and
pushed the other way. Widening `trainingpeaks_sync.RUN_TYPES` would import those
back as duplicates of events intervals.icu already has, and the agent would then
plan against both. Races and Day Off entries are excluded for their own reasons
(see `is_coach_run`): a TP race becomes a `RACE_A` event that reshapes
intervals.icu's form and taper projections, and races are the athlete's own
record in `50 Races/`.

**The mirror is one-way and the agent must not fight it.** `week-planner` and
`daily-brief` are told that a run whose description opens with
`COACH (TrainingPeaks)` is fixed: plan around it, count its load, never move or
replace it. `daily-brief` may still append its `COACH:` note — that survives,
because the sync diffs on the `[tp-sync hash=...]` footer rather than the whole
description, so an appended line does not look like a change. It is lost only if
the coach edits that same session in TP later the same day, which is why the
skill also asks for the reasoning in the Telegram block.

**Runs are filtered out of the intervals.icu -> Coros upload.** intervals.icu
pushes planned workouts to the watch, and TrainingPeaks pushes the same runs
there independently; with both on, every coach run landed on the Coros twice,
and neither API can delete the other's copy. The type filter on the intervals.icu
Coros connection now excludes Run, so runs reach the watch from TrainingPeaks and
everything else from intervals.icu. Two consequences to keep in mind: a run
`week-planner` prescribes itself will *not* appear on the watch (the skill is
told to say so), and if that filter is ever widened again the duplicates come
straight back.

**`week-planner` does not plan running on its own initiative.** The run coach
owns running by default; the agent owns swim, bike and gym and the shape of the
week around the runs, and builds bricks by placing a ride against one of the
coach's runs rather than writing a run leg. This is a default, not a
prohibition: **when Steffan explicitly asks for a run — a real brick, a shakeout,
a recovery jog — the agent writes it.** Such a run is the agent's own event, so
the mirror never touches it, and it will not reach the watch (runs are filtered
out of the intervals.icu -> Coros upload), which the skill is told to say. What
the agent must never do is decide by itself that the week needs more running.
What it *does* do unprompted is the thing the coach cannot:
judge the coach's running against the rest of the week's load and recommend which
runs to drop or shorten. That is a recommendation, never an action — it acts only
once Steffan agrees, and then only by recording the drop in
`10 Plan/week-YYYY-Www.md` and annotating the event. **A drop cannot be enacted on
the calendar**: the mirror re-creates anything deleted on its next run, so a
session only truly disappears when it comes out of TrainingPeaks.

**Tuesday, Thursday and Saturday are club sessions, and they arrive late.** Those
three days are never candidates for a drop recommendation, whatever the load
says. They are also usually uploaded by the coach only on the Sunday before, so
an empty Tue/Thu/Sat further out means "not published yet", not "free" —
`week-planner` reserves them rather than filling them, because a key bike or swim
dropped into a day that later gains a club session is the failure mode that costs
a week. Load goes onto the non-club days first (Mon/Wed/Fri/Sun) and only spills
onto a club day, easy sessions only, if the week is still short.

**Auth is a browser cookie, and it will expire.** TrainingPeaks has no public API
for personal use, so `TP_AUTH_COOKIE` is the `Production_tpAuth` session cookie,
pasted in by hand. When it dies the sync says so on Telegram by name rather than
failing quietly, because a mirror that stopped looks exactly like a coach who
stopped planning. Unset, the whole thing no-ops.

**Health and calendar use separate OAuth grants and must stay separate.** One
client, two refresh tokens (`GOOGLE_HEALTH_REFRESH_TOKEN`,
`GOOGLE_CALENDAR_REFRESH_TOKEN`), minted by `scripts/google_auth.py --scopes ...`.
The Google Health API allowlists its own scopes and 403s any token that also
carries the calendar scope, so merging the two grants silently breaks wellness
while calendar keeps working. `coach/google_oauth.py` is the shared exchange.

**Model split is intentional**: `COACH_MODEL` (Sonnet) for the ~730 scheduled runs a year,
`PLANNER_MODEL` (Opus) passed explicitly for `plan-architect`, which runs a
handful of times a season. `agent.run(prompt, model=...)` is the seam.

**Detailed weeks are generated one week at a time**, never the whole season up
front. The macro plan holds block structure; `week-planner` fills in the swim,
bike and gym sessions — running arrives from the coach through
`trainingpeaks_sync`, not from the plan.

## Conventions that matter

- **Never invent training data.** Numbers come from intervals.icu tool calls; a
  failed call is reported plainly, not papered over. This rule is in the system
  prompt and repeated in the skills — keep it there when editing either.
- **Never delete an intervals.icu calendar event.** Move it or rewrite its
  description, and record the change in the day's note. The single exception is
  `trainingpeaks_sync`, which deletes events carrying its own `tp:` external id
  when TrainingPeaks no longer has them — a run the coach withdrew has to
  disappear rather than linger as a session the agent keeps grading against.
  The agent itself has no such exception.
- **One writer per file.** `20 Daily/YYYY-MM-DD.md` is written by `daily-debrief`
  at 21:00 and by nothing else, one note per date, after the day rather than
  before it. `30 Sessions/` is written by `session-debrief` off the webhook and
  by nothing else. `daily-brief` must stay a Telegram-only job.
- **`session-debrief` must write `activity_id` into a note's frontmatter.** It is
  the only dedupe key; without it a re-fired webhook debriefs the same session
  twice. See `session_debrief.already_debriefed`.
- **The model count is now per-session, not per-day.** A busy day can be three
  agent turns rather than one, on top of the two scheduled jobs. That was the
  price of debriefing on upload, and `COACH_MODEL` staying Sonnet is what keeps
  it affordable.
- **Medical escalation is not optional.** Sharp/localised pain, fever, or three
  consecutive red readiness days ends prescription and routes to a physio/GP.
- **Auth is a single chat-ID check** (`telegram_bot._authorised`). It is the only
  thing between the bot and anyone who finds it; unauthorised updates are dropped
  silently, with no reply.
- Coaching guardrails (ramp rate ≤5–7/wk base, ≤3–5/wk build; 80/20 distribution;
  recovery every 3rd–4th week) live in `vault-template/00 Meta/coaching-principles.md`
  and override plan files when they conflict. Skills reference them by name.
- `vault-template/` is seed content copied into a fresh vault repo once at setup;
  it is not read at runtime.

## Gotcha

The Agent SDK moves fast. If `ClaudeAgentOptions` rejects a field, check
https://code.claude.com/docs/en/agent-sdk/python before debugging further.
