"""Thin wrapper around the Claude Agent SDK, pointed at the vault + intervals.icu."""
import asyncio
import os

from claude_agent_sdk import AssistantMessage, ClaudeAgentOptions, ResultMessage, TextBlock, query

from . import calendar_sync, vault

SYSTEM_PROMPT = """You are Steffan's triathlon coach.

You have three sources of truth, in this order:
1. `00 Meta/athlete-profile.md` and `00 Meta/coaching-principles.md` in the vault
   - read these at the start of EVERY session before anything else.
2. intervals.icu - the actual training data. Never guess a number you could look up.
3. `10 Plan/` - the current macro plan and this week's plan.

Hard rules:
- Never invent training data. If a tool call fails, say so plainly.
- For CTL/ATL/TSB, use `get_wellness_for_date` or `get_wellness_data`, not
  `get_fitness_summary` — that tool reads the athlete-profile endpoint, which
  intervals.icu never populates with those fields, so it always reports "no
  fitness data" even when history exists.
- Never delete an intervals.icu calendar event. Move it or rewrite its
  description, and always record the change in today's daily note.
- Only write inside `10 Plan/`, `20 Daily/`, `30 Sessions/`. `40 Journal/` and
  `50 Races/` are Steffan's - read them, never edit them.
- You are not a doctor. Sharp or localised pain, fever, or three consecutive red
  readiness days means "see a physio or GP", not "here is a modified session".
- Be blunt and short. He is an experienced athlete; skip the pep talk.
"""


def _intervals_mcp() -> dict:
    """intervals.icu MCP over stdio. Swap for {"type":"http","url":...} if hosted."""
    return {
        "intervals": {
            # Installed by the Dockerfile (`uv tool install`, pinned rev, plus a
            # patch for an upstream date-parsing bug) rather than fetched here by
            # `uvx`, so the version the agent talks to is fixed at build time.
            # Local runs need that same install once — see CLAUDE.md.
            "command": "intervals-icu-mcp",
            "args": [],
            # eddmann/intervals-icu-mcp reads its own env var names (see its
            # ICUConfig in auth.py) — not the plain INTERVALS_* this app uses
            # elsewhere (.env.example, app.bicep) — hence the remap here.
            "env": {
                "INTERVALS_ICU_API_KEY": os.environ["INTERVALS_API_KEY"],
                "INTERVALS_ICU_ATHLETE_ID": os.environ["INTERVALS_ATHLETE_ID"],
            },
        }
    }


def options(model: str | None = None) -> ClaudeAgentOptions:
    return ClaudeAgentOptions(
        model=model or os.environ.get("COACH_MODEL", "claude-sonnet-5"),
        system_prompt=SYSTEM_PROMPT,
        cwd=str(vault.VAULT_PATH),
        mcp_servers=_intervals_mcp(),
        setting_sources=["project"],  # loads .claude/skills/
        allowed_tools=[
            "Read", "Write", "Edit", "Glob", "Grep", "Skill", "mcp__intervals",
        ],
        permission_mode="acceptEdits",
    )


def _text(message) -> str:
    """Pull text out of an AssistantMessage. TextBlock has no `.type` field —
    only `.text` — so this must isinstance-check the block, not duck-type it."""
    if not isinstance(message, AssistantMessage):
        return ""
    return "".join(b.text for b in message.content if isinstance(b, TextBlock))


# Serialises agent turns across every caller. Each run mutates one git working
# tree — pull, let the agent write, commit, push — so two overlapping turns would
# rebase onto each other's half-written state and one of them would lose its
# note. This was academic while the only callers were Telegram (one message at a
# time) and two cron jobs hours apart; ACTIVITY_UPLOADED changed that, since an
# upload can land in the middle of the evening debrief. Held for the whole turn,
# so a long `plan-architect` run does delay a session debrief behind it — which
# is the right trade against a corrupted vault.
_RUN_LOCK = asyncio.Lock()


async def run(prompt: str, model: str | None = None) -> str:
    async with _RUN_LOCK:
        return await _run(prompt, model)


async def _run(prompt: str, model: str | None = None) -> str:
    vault.pull()
    # Refreshed here rather than in the /week handler because `week-planner` is
    # also reachable by plain text ("plan my week"), which never touches a
    # command handler. After the pull, so the write lands on top of the rebase.
    calendar_sync.refresh_quietly()
    chunks = []
    result: ResultMessage | None = None
    async for message in query(prompt=prompt, options=options(model)):
        if isinstance(message, ResultMessage):
            result = message
            continue
        chunks.append(_text(message))
    reply = "".join(c for c in chunks if c).strip()
    # A turn can end with no assistant text without raising a Python exception
    # (e.g. an API error, a permission denial, hitting max_turns) — surface
    # that instead of silently returning "", per the "never paper over a
    # failed call" rule this system prompt states for tool calls.
    if not reply and result is not None:
        detail = result.result or "; ".join(result.errors or []) or result.subtype
        reply = f"Agent returned no reply (is_error={result.is_error}): {detail}"
    vault.commit_and_push(f"coach: {prompt[:60]}")
    return reply
