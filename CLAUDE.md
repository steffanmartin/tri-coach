# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

An always-on triathlon coach for one athlete (Steffan). A Telegram bot long-polls
for messages, hands each one to the Claude Agent SDK, and the agent reasons over
two data sources: **intervals.icu** (all numbers, via MCP) and a **git-backed
Obsidian vault** (all memory, via plain file tools). There is no database and no
web service — the vault repo *is* the state store.

## Commands

```bash
docker compose up -d --build          # build + run the bot (the only real "run" path)
docker compose logs -f
docker compose exec coach python -m coach.daily_brief --no-wait  # brief now, don't wait for wellness
docker compose exec coach python -m coach.daily_debrief --no-wait # debrief now, don't wait for uploads
docker compose exec coach python -m coach.wellness_sync --days 7   # pull HRV/RHR/sleep now
docker compose exec coach python -m coach.calendar_sync --dry-run  # see the calendar snapshot
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
`python -m coach.daily_debrief --no-wait` for the scheduled paths (drop the flag
to exercise the polling wait itself). The debrief is the one that writes to the
vault, so a successful run leaves a commit behind.

## Architecture

**One process, three entry points.** `coach/telegram_bot.py:main` starts the
polling loop and an in-process `AsyncIOScheduler` holding two cron jobs:
`daily_brief.main` at 06:00 and `daily_debrief.main` at 21:00. Deliberate: the
container is already always-on, so separate scheduler infra would be wasted. This
also means **the host must not scale to zero** — long polling dies with the
process, and with it both jobs.

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

**The debrief closes the day, and owns the daily note.** `daily_debrief.main` is
the same shape at the other end of the day: it starts at
`DAILY_DEBRIEF_CRON_HOUR/MINUTE` (21:00), polls every
`ACTIVITY_POLL_INTERVAL_MIN` (10) until every planned session for today has an
activity recorded against it, and at `DAILY_DEBRIEF_DEADLINE_HOUR/MINUTE` (23:00)
runs anyway with the count of what never uploaded passed into the prompt. It then
debriefs each activity into `30 Sessions/` and writes `20 Daily/YYYY-MM-DD.md`.
The wait loop itself is shared with the brief — `coach/polling.py:poll_until` —
so the retry, deadline and never-sleep-past-it behaviour cannot drift between
them. Here it polls **intervals.icu**, which is not a contradiction of the
morning polling Google Health: wellness is in intervals.icu only because our sync
put it there, whereas activities come from Coros and are genuinely upstream of
us. `coach/intervals.py` is that read path, and it exists only to let a scheduled
job decide whether waking the agent is worth it — it is not a second numbers
source for the agent, which still reads everything through the MCP. Planned
events are narrowed to Run/Ride/Swim (`intervals.TRACKED_SPORTS`) because gym and
mobility never produce an upload and would otherwise hold every night at the
deadline. `coach/intervals.py` uses REST rather than the MCP because it runs
inside the polling loop, before there is an agent turn to host a tool call.

**The daily note is written once, in the evening.** `20 Daily/YYYY-MM-DD.md` used
to be written at 06:00 by `daily-brief`, which meant the vault's record of a
day was a prediction that nothing ever reconciled — and `30 Sessions/` never got
written to at all. Now `daily-debrief` is the sole writer of both, and
`daily-brief` writes nothing to the vault: **do not restore its `20 Daily/`
write**, or the two jobs will fight over one file. The cost of this is that the
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
front. The macro plan holds block structure; `week-planner` fills in sessions.

## Conventions that matter

- **Never invent training data.** Numbers come from intervals.icu tool calls; a
  failed call is reported plainly, not papered over. This rule is in the system
  prompt and repeated in the skills — keep it there when editing either.
- **Never delete an intervals.icu calendar event.** Move it or rewrite its
  description, and record the change in the day's note.
- **`20 Daily/` and `30 Sessions/` are written by `daily-debrief` at 21:00, and by
  nothing else.** One note per date, written after the day, not before it.
  `daily-brief` must stay a Telegram-only job.
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
