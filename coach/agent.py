"""Thin wrapper around the Claude Agent SDK, pointed at the vault + intervals.icu."""
import os

from claude_agent_sdk import AssistantMessage, ClaudeAgentOptions, ResultMessage, TextBlock, query

from . import calendar_sync, coros_oauth, vault

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
            "command": "uvx",
            "args": [
                "--from",
                "git+https://github.com/eddmann/intervals-icu-mcp",
                # Pinned below its own stated floor (fastmcp>=2.12.4): fastmcp 3.x
                # made Context.get_state async, but this package's middleware and
                # every tool still call it unawaited, so every tool call dies with
                # "'coroutine' object has no attribute ...". 2.x is what its code
                # actually matches.
                "--with",
                "fastmcp<3",
                "intervals-icu-mcp",
            ],
            # eddmann/intervals-icu-mcp reads its own env var names (see its
            # ICUConfig in auth.py) — not the plain INTERVALS_* this app uses
            # elsewhere (.env.example, app.bicep) — hence the remap here.
            "env": {
                "INTERVALS_ICU_API_KEY": os.environ["INTERVALS_API_KEY"],
                "INTERVALS_ICU_ATHLETE_ID": os.environ["INTERVALS_ATHLETE_ID"],
            },
        }
    }


# COROS is a WRITE path only. intervals.icu stays the single source of numbers
# (see CLAUDE.md), and the COROS connector also serves sleep/HRV/load reads —
# so the agent is handed only the tools that push a workout out, never the ones
# that read a metric back. Widening this list re-opens the second-numbers-source
# problem the wellness sync exists to avoid.
COROS_WRITE_TOOLS: list[str] = []


def _coros_mcp() -> dict:
    """COROS MCP over HTTP, or nothing if the grant is not configured.

    Best-effort like the calendar snapshot: a COROS outage or an expired grant
    costs us the watch push, it does not take the bot down. The failure surfaces
    when the agent tries to call a tool that is not there and says so.
    """
    if not os.environ.get("COROS_REFRESH_TOKEN"):
        return {}
    try:
        token = coros_oauth.access_token()
    except Exception as exc:  # noqa: BLE001 - never fatal
        print(f"coros: no connector this turn ({exc})")
        return {}
    return {
        "coros": {
            "type": "http",
            "url": coros_oauth.MCP_URL,
            "headers": {"Authorization": f"Bearer {token}"},
        }
    }


def options(model: str | None = None) -> ClaudeAgentOptions:
    return ClaudeAgentOptions(
        model=model or os.environ.get("COACH_MODEL", "claude-sonnet-5"),
        system_prompt=SYSTEM_PROMPT,
        cwd=str(vault.VAULT_PATH),
        mcp_servers={**_intervals_mcp(), **_coros_mcp()},
        setting_sources=["project"],  # loads .claude/skills/
        allowed_tools=[
            "Read", "Write", "Edit", "Glob", "Grep", "Skill", "mcp__intervals",
            *COROS_WRITE_TOOLS,
        ],
        permission_mode="acceptEdits",
    )


def _text(message) -> str:
    """Pull text out of an AssistantMessage. TextBlock has no `.type` field —
    only `.text` — so this must isinstance-check the block, not duck-type it."""
    if not isinstance(message, AssistantMessage):
        return ""
    return "".join(b.text for b in message.content if isinstance(b, TextBlock))


async def run(prompt: str, model: str | None = None) -> str:
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
