"""tri-coach.

Nothing is exported here. The only thing this module does is turn down httpx's
logger, and it lives here because there are six separate `logging.basicConfig`
calls across the entry points and the problem does not care which one ran.

httpx logs a line per request at INFO, including the full URL — and Telegram
puts the bot token in the *path*, not a header:

    api.telegram.org/bot<TOKEN>/getUpdates

So an INFO-level httpx logger writes the bot token to stdout every time the bot
long-polls, which is every ten seconds, forever. On Azure that goes straight to
Log Analytics, where it is readable by anyone with reader access on the
workspace and is retained long after the token would otherwise have been
rotated. `daily_brief.send` leaks it the same way through `/sendMessage`.

Setting the level on the logger itself, rather than through `basicConfig`, is
deliberate: a later `basicConfig(level=INFO)` in any entry point sets the *root*
level and cannot raise this one back up.

The cost is the per-request line for every httpx call in the package, including
the intervals.icu and Google ones. That is an acceptable trade for not printing
a credential three thousand times a day — those calls report their own failures
where it matters, and httpx raises rather than logs when a request actually
fails, so nothing that mattered was being learned from those lines anyway.
"""
import logging

logging.getLogger("httpx").setLevel(logging.WARNING)
