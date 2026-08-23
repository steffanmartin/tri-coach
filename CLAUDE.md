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
docker compose exec coach python -m coach.daily_brief   # fire the 06:30 job now, without waiting
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
at 06:30. Deliberate: the container is already always-on, so separate scheduler
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
without rethinking that.

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
