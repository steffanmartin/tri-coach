"""Always-on Telegram bot (long polling) + in-process cron for the daily jobs."""
import logging
import os

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from telegram import BotCommand, MessageEntity, Update
from telegram.constants import ChatAction
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from . import agent, daily_brief, daily_debrief, telegram_format, vault

logging.basicConfig(level=logging.INFO)
ALLOWED = str(os.environ["TELEGRAM_ALLOWED_CHAT_ID"])


def _authorised(update: Update) -> bool:
    return str(update.effective_chat.id) == ALLOWED


async def _ask(update: Update, context: ContextTypes.DEFAULT_TYPE, prompt: str) -> None:
    if not _authorised(update):
        return
    await context.bot.send_chat_action(update.effective_chat.id, ChatAction.TYPING)
    try:
        reply = await agent.run(prompt)
    except Exception as exc:
        reply = f"Something broke: {type(exc).__name__}: {exc}"
    for text, entities in await telegram_format.text_chunks(reply):
        await update.message.reply_text(text, entities=[MessageEntity(**e) for e in entities])


async def on_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _ask(update, context, update.message.text)


async def cmd_today(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _ask(update, context, "Run the `daily-brief` skill for today.")


async def cmd_week(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _ask(update, context, "Run the `week-planner` skill for the coming week.")


async def cmd_debrief(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _ask(update, context, "Run the `session-debrief` skill on my latest activity.")


async def cmd_day(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """The whole day, not one session — the same skill the 21:00 job runs."""
    await _ask(update, context, "Run the `daily-debrief` skill for today.")


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _ask(
        update, context,
        "Give me CTL, ATL, TSB, 7-day load and weeks-to-race in under 6 lines.",
    )


def main() -> None:
    vault.ensure_clone()

    scheduler = AsyncIOScheduler(timezone=os.environ.get("TZ", "Europe/Copenhagen"))

    # This is when the brief starts *looking*, not when it sends. The job polls
    # Google Health for the night's HRV, resting HR and sleep, syncs them into
    # intervals.icu and briefs as soon as they are all there — so the message
    # arrives on the morning the watch actually uploaded, rather than at a fixed
    # time that a late sync misses. See daily_brief for the deadline.
    scheduler.add_job(
        daily_brief.main,
        "cron",
        hour=int(os.environ.get("DAILY_BRIEF_CRON_HOUR", 6)),
        minute=int(os.environ.get("DAILY_BRIEF_CRON_MINUTE", 0)),
    )

    # Same shape at the other end of the day: this is when the debrief starts
    # looking for the day's activities to finish uploading from Coros, not when
    # it sends. It writes the day's `20 Daily/` note — the morning brief does
    # not — so if this job stops running, the vault stops gaining daily notes.
    scheduler.add_job(
        daily_debrief.main,
        "cron",
        hour=int(os.environ.get("DAILY_DEBRIEF_CRON_HOUR", 21)),
        minute=int(os.environ.get("DAILY_DEBRIEF_CRON_MINUTE", 0)),
    )

    # AsyncIOScheduler.start() needs a running loop, which doesn't exist yet in
    # this synchronous main() — post_init runs inside the loop run_polling creates.
    async def _start_scheduler(app: Application) -> None:
        scheduler.start()
        # Populates Telegram's "/" autocomplete menu with these commands and
        # descriptions; without it the handlers still work but are invisible
        # until typed from memory.
        await app.bot.set_my_commands([
            BotCommand("today", "Morning readiness check + today's session"),
            BotCommand("week", "Plan or rebalance this week"),
            BotCommand("debrief", "How did that session go"),
            BotCommand("day", "Close out today's training"),
            BotCommand("status", "CTL/ATL/TSB and weeks to race"),
        ])

    app = (
        Application.builder()
        .token(os.environ["TELEGRAM_BOT_TOKEN"])
        .post_init(_start_scheduler)
        .build()
    )
    app.add_handler(CommandHandler("today", cmd_today))
    app.add_handler(CommandHandler("week", cmd_week))
    app.add_handler(CommandHandler("debrief", cmd_debrief))
    app.add_handler(CommandHandler("day", cmd_day))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_message))

    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
