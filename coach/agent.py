"""Thin wrapper around the Claude Agent SDK, pointed at the vault + intervals.icu."""
import os

from claude_agent_sdk import ClaudeAgentOptions, query

from . import vault

SYSTEM_PROMPT = """You are Steffan's triathlon coach.

You have three sources of truth, in this order:
1. `00 Meta/athlete-profile.md` and `00 Meta/coaching-principles.md` in the vault
   - read these at the start of EVERY session before anything else.
2. intervals.icu - the actual training data. Never guess a number you could look up.
3. `10 Plan/` - the current macro plan and this week's plan.

Hard rules:
- Never invent training data. If a tool call fails, say so plainly.
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
                "intervals-icu-mcp",
            ],
            "env": {
                "INTERVALS_API_KEY": os.environ["INTERVALS_API_KEY"],
                "INTERVALS_ATHLETE_ID": os.environ["INTERVALS_ATHLETE_ID"],
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
    """Pull text out of whatever message shape the SDK hands back."""
    content = getattr(message, "content", None)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(b.text for b in content if getattr(b, "type", None) == "text")
    return ""


async def run(prompt: str, model: str | None = None) -> str:
    vault.pull()
    chunks = []
    async for message in query(prompt=prompt, options=options(model)):
        chunks.append(_text(message))
    reply = "".join(c for c in chunks if c).strip()
    vault.commit_and_push(f"coach: {prompt[:60]}")
    return reply
