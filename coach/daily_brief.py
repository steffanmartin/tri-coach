"""07:00 job: read wellness, decide today's session, write the note, ping Telegram."""
import asyncio
import os
from datetime import date

import httpx

from . import agent

PROMPT = f"""Run the `daily-readiness` skill for {date.today().isoformat()}.

Finish with a Telegram-ready summary between <telegram> and </telegram> tags:
max 8 short lines, no markdown headings, no emoji spam (one status emoji is fine).
"""


def _extract(reply: str) -> str:
    if "<telegram>" in reply and "</telegram>" in reply:
        return reply.split("<telegram>", 1)[1].split("</telegram>", 1)[0].strip()
    return reply[:1500]


async def send(text: str) -> None:
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    async with httpx.AsyncClient(timeout=30) as client:
        await client.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": os.environ["TELEGRAM_ALLOWED_CHAT_ID"], "text": text},
        )


async def main() -> None:
    try:
        reply = await agent.run(PROMPT)
        await send(_extract(reply))
    except Exception as exc:  # never fail silently at 07:00
        await send(f"Coach job failed: {type(exc).__name__}: {exc}")


if __name__ == "__main__":
    asyncio.run(main())
