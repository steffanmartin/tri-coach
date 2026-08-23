"""Always-on Telegram bot (long polling) + in-process cron for the daily brief."""
import logging
import os

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from . import agent, daily_brief, vault

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
    for i in range(0, len(reply) or 1, 4000):  # Telegram caps at 4096 chars
        await update.message.reply_text(reply[i : i + 4000] or "(no reply)")


async def on_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _ask(update, context, update.message.text)


async def cmd_today(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _ask(update, context, "Run the `daily-readiness` skill for today.")


async def cmd_week(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _ask(update, context, "Run the `week-planner` skill for the coming week.")


async def cmd_debrief(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _ask(update, context, "Run the `session-debrief` skill on my latest activity.")


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _ask(
        update, context,
        "Give me CTL, ATL, TSB, 7-day load and weeks-to-race in under 6 lines.",
    )


def main() -> None:
    vault.ensure_clone()
    app = Application.builder().token(os.environ["TELEGRAM_BOT_TOKEN"]).build()
    app.add_handler(CommandHandler("today", cmd_today))
    app.add_handler(CommandHandler("week", cmd_week))
    app.add_handler(CommandHandler("debrief", cmd_debrief))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_message))

    scheduler = AsyncIOScheduler(timezone=os.environ.get("TZ", "Europe/Copenhagen"))
    scheduler.add_job(
        daily_brief.main,
        "cron",
        hour=int(os.environ.get("DAILY_BRIEF_CRON_HOUR", 6)),
        minute=int(os.environ.get("DAILY_BRIEF_CRON_MINUTE", 30)),
    )
    scheduler.start()

    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
