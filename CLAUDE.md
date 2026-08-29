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
docker compose exec coach python -m coach.daily_brief   # fire the 07:00 job now, without waiting
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
installs both; the SDK shells out to the CLI, and `uvx` launches the intervals MCP):

```bash
uv sync
uv run python -m coach.telegram_bot
```

There is no test suite, linter, or CI. Verification is manual: `/status` in
Telegram for the bot path, `python -m coach.daily_brief` for the scheduled path.

## Architecture

**One process, two entry points.** `coach/telegram_bot.py:main` starts both the
polling loop and an in-process `AsyncIOScheduler` that calls `daily_brief.main`
at 07:00. Deliberate: the container is already always-on, so separate scheduler
infra would be wasted. This also means **the host must not scale to zero** —
long polling dies with the process.

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
`/debrief` are one-line prompts that just name a skill.

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
intervals.icu's `wellness-bulk` endpoint ~15 min before the brief. Steps are
written a day behind: the other three are overnight measurements and final by
06:15, but today's step count has barely started. The agent is deliberately
unaware of this: it still reads every number through the intervals MCP, so
"numbers come from intervals.icu" stays literally true and `daily-readiness` gets
its 60-day baselines computed by intervals.icu rather than by the model. Writes
are upserts keyed by date, so re-running a window corrects it. **Do not give the
agent a second numbers source** — that is the whole point of the sync.

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

**Model split is intentional**: `COACH_MODEL` (Sonnet) for the ~365 daily runs,
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
