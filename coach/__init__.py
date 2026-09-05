"""tri-coach.

Nothing is exported here. The only thing this module does is turn down httpx's
logger, and it lives here because there are six separate `logging.basicConfig`
calls across the entry points and the problem does not care which one ran.

httpx logs a line per request at INFO, including the full URL — and Telegram
puts the bot token in the *path*, not a header:

    api.telegram.org/bot<TOKEN>/getUpdates

So an INFO-level httpx logger writes the bot token to stdout every time the bot
long-polls, which is every ten seconds, forever. That goes straight into the
container's log, which on the VPS is a json-file on disk read with `docker
compose logs` and kept for five rotations — so the token outlives any session
that produced it. `daily_brief.send` leaks it the same way through
`/sendMessage`.

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

# Every entry point calls basicConfig with this. Container Apps stamped each log
# line on ingest, so nothing here ever needed to; a json-file on the VPS does
# not, and `docker compose logs -t` stamps at read time only if you remember the
# flag. On a box where the logs are all you have, an unstamped traceback is
# nearly useless.
LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"
