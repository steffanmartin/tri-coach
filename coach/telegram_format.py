"""Markdown -> Telegram (text, entity) chunks, shared by the bot and daily_brief.

Telegram's MarkdownV2 parse_mode needs ~18 punctuation characters escaped and
uses single-asterisk bold, not the model's **bold** — getting an LLM to emit
that correctly on every turn is asking it to never slip on a single unescaped
period. telegramify_markdown parses real Markdown into (text, MessageEntity)
pairs instead, which Telegram renders directly with no parse_mode involved.
"""
from telegramify_markdown import telegramify
from telegramify_markdown.content import ContentType

MAX_MESSAGE_LENGTH = 4090  # Telegram's cap is 4096; leave a little headroom.


async def text_chunks(markdown: str) -> list[tuple[str, list[dict]]]:
    """(text, entity-dicts) pairs, ready for python-telegram-bot's `entities=`
    or a raw Bot API `sendMessage` body. Non-text items (extracted code files,
    diagrams) are dropped: coaching replies are prose, and daily_brief's
    prompt already asks for plain short lines with no code fences."""
    items = await telegramify(markdown or "(no reply)", max_message_length=MAX_MESSAGE_LENGTH)
    return [
        (item.text, [e.to_dict() for e in item.entities])
        for item in items
        if item.content_type == ContentType.TEXT
    ]
