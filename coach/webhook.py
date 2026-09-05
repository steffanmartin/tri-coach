"""Receive intervals.icu webhooks and turn ACTIVITY_UPLOADED into a debrief.

This is the one inbound surface the process has. Everything else the coach does
is outbound — Telegram long polling, REST reads, the MCP over stdio — so this
module is deliberately small and suspicious of what it is handed.

**It acknowledges before it works, and that is not laziness.** intervals.icu
re-fires a webhook with exponential backoff until it gets a 2xx, and an agent
turn takes tens of seconds; holding the connection open for one would earn a
retry, and the retry would debrief the same session twice. So the handler
verifies, hands the work to the bot's event loop, and returns 200 immediately.
Delivery is acknowledged, not completion — `session_debrief` owns the outcome,
including telling Telegram when it fails.

The stdlib server is a deliberate choice over aiohttp or starlette. The traffic
is a few POSTs a day from one source; `ThreadingHTTPServer` handles the parsing
and status lines correctly, and the alternative was a web framework in the
dependency list of a process whose whole point is that it serves nothing.

Two independent checks, and the process refuses to listen without the first:

- the `secret` in the POST body, which intervals.icu generates and shows at
  https://intervals.icu/settings/apps
- optionally an `Authorization` header, whose value is set on the same page

Both are compared with `hmac.compare_digest`. A request failing either is
dropped with 403 and logged without its body.
"""
import asyncio
import hmac
import json
import logging
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable, Coroutine

log = logging.getLogger(__name__)

WEBHOOK_PATH = "/intervals/webhook"
HEALTH_PATH = "/health"

# Only this one matters here. The app is registered for ACTIVITY_UPLOADED alone,
# but intervals.icu decides what it sends, not us — an event type we did not ask
# for is acknowledged and ignored rather than treated as an error, so a change on
# their side can never put us into a retry loop.
ACTIVITY_UPLOADED = "ACTIVITY_UPLOADED"

# Bodies above this are refused unread. A webhook batch is a few KB; anything
# this size is not one, and reading it into memory is the only cost of finding out.
MAX_BODY_BYTES = 1_000_000


def _activity_id(event: dict) -> str | None:
    """Pull the activity id out of an event, tolerating either shape.

    The documented payload nests the activity (`{"activity": {"id": ...}}`), but
    the id is the one field this module cannot do without, so a flat
    `activity_id` is accepted too rather than dropping the event.
    """
    activity = event.get("activity")
    if isinstance(activity, dict) and activity.get("id"):
        return str(activity["id"])
    if event.get("activity_id"):
        return str(event["activity_id"])
    return None


def relevant_events(payload: dict, athlete_id: str) -> list[dict]:
    """The ACTIVITY_UPLOADED events in this batch that belong to our athlete.

    The athlete filter is not paranoia about intervals.icu; it is what stops a
    misconfigured app — ours or someone else's pointed at this URL — from
    quietly debriefing another person's training into Steffan's vault.
    """
    events = payload.get("events")
    if not isinstance(events, list):
        return []
    keep = []
    for event in events:
        if not isinstance(event, dict) or event.get("type") != ACTIVITY_UPLOADED:
            continue
        if str(event.get("athlete_id") or "") != athlete_id:
            log.warning("dropping %s for another athlete", ACTIVITY_UPLOADED)
            continue
        if _activity_id(event):
            keep.append(event)
        else:
            log.warning("dropping %s with no activity id", ACTIVITY_UPLOADED)
    return keep


# Set by `serve`. The loop and the dispatcher live here at module scope rather
# than on the handler class, and that is not a style preference: a plain function
# assigned to a class attribute becomes a method on attribute access, so
# `self.dispatch(event)` would silently pass the handler instance as the first
# argument and every delivery would die with a TypeError *after* the 200 had
# already gone out — invisible from intervals.icu's side, which would see a
# perfectly successful webhook.
_loop: asyncio.AbstractEventLoop | None = None
_dispatch: Callable[[dict], Coroutine[Any, Any, Any]] | None = None


class _Handler(BaseHTTPRequestHandler):
    # Strings are safe as class attributes — only callables get bound. Set by
    # `serve`, rather than an __init__ override, because BaseHTTPRequestHandler
    # is instantiated per request by the server itself.
    secret: str = ""
    auth_header: str = ""
    athlete_id: str = ""

    server_version = "tri-coach"
    sys_version = ""

    def log_message(self, fmt: str, *args) -> None:  # noqa: A003
        """Route access logs through logging instead of stderr, so they land in
        `az containerapp logs` with everything else."""
        log.info("%s - %s", self.address_string(), fmt % args)

    def _reply(self, code: int, body: str = "ok") -> None:
        # A body on every response on purpose: intervals.icu historically treated
        # 204 No Content as a failure and re-fired, so this never sends one.
        raw = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self) -> None:  # noqa: N802
        """Health probe, and the only endpoint that says nothing about the athlete.

        `/` answers too because that is what Container Apps' ingress actually
        probes — it does not know about `/health`, and every probe was logging a
        404 against a container that was serving perfectly well. Both return the
        same bare `ok`; neither reveals whether the athlete exists, has trained,
        or is being coached at all.
        """
        if self.path.split("?", 1)[0] in (HEALTH_PATH, "/"):
            self._reply(200)
        else:
            self._reply(404, "not found")

    def do_POST(self) -> None:  # noqa: N802
        if self.path.split("?", 1)[0] != WEBHOOK_PATH:
            self._reply(404, "not found")
            return
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            self._reply(400, "bad length")
            return
        if length <= 0 or length > MAX_BODY_BYTES:
            self._reply(400, "bad length")
            return

        if self.auth_header and not hmac.compare_digest(
            self.headers.get("Authorization") or "", self.auth_header
        ):
            log.warning("rejected webhook: Authorization mismatch")
            self._reply(403, "forbidden")
            return

        try:
            payload = json.loads(self.rfile.read(length))
        except (ValueError, OSError) as exc:
            log.warning("rejected webhook: unreadable body: %s", type(exc).__name__)
            self._reply(400, "bad body")
            return
        if not isinstance(payload, dict):
            self._reply(400, "bad body")
            return

        if not hmac.compare_digest(str(payload.get("secret") or ""), self.secret):
            # Deliberately does not log the body or the offered secret.
            log.warning("rejected webhook: secret mismatch")
            self._reply(403, "forbidden")
            return

        events = relevant_events(payload, self.athlete_id)
        # 200 first, work second. See the module docstring: anything slower than
        # this earns a retry, and a retry is a duplicate debrief.
        self._reply(200, f"accepted {len(events)}")
        for event in events:
            self._schedule(event)

    def _schedule(self, event: dict) -> None:
        """Hand one event to the bot's event loop from this handler thread."""
        if _loop is None or _dispatch is None:  # pragma: no cover
            log.error("webhook received before the loop was attached")
            return
        future = asyncio.run_coroutine_threadsafe(_dispatch(event), _loop)

        def _log_failure(done) -> None:
            exc = done.exception()
            if exc is not None:
                log.exception("webhook dispatch failed", exc_info=exc)

        # Without a callback the exception would sit unread on the future and the
        # failure would be invisible; `session_debrief` reports its own errors to
        # Telegram, so this only catches what escapes it.
        future.add_done_callback(_log_failure)


async def _default_dispatch(event: dict) -> None:
    # Imported here rather than at module scope so `webhook` stays importable
    # (and testable) without pulling in the Agent SDK.
    from . import session_debrief

    activity = event.get("activity") if isinstance(event.get("activity"), dict) else {}
    await session_debrief.debrief_activity(
        _activity_id(event), activity.get("name"), activity.get("type")
    )


def serve(
    loop: asyncio.AbstractEventLoop,
    dispatch: Callable[[dict], Coroutine[Any, Any, Any]] | None = None,
) -> ThreadingHTTPServer | None:
    """Start the receiver on a daemon thread. Returns None when not configured.

    Fails closed: with no `INTERVALS_WEBHOOK_SECRET` there is no way to tell a
    real delivery from anyone who found the URL, so the port is never opened and
    the bot runs exactly as it did before. That is also what makes this safe to
    ship ahead of the webhook being registered at intervals.icu.
    """
    secret = os.environ.get("INTERVALS_WEBHOOK_SECRET", "")
    if not secret:
        log.info("INTERVALS_WEBHOOK_SECRET unset — not listening for webhooks")
        return None

    global _loop, _dispatch
    _Handler.secret = secret
    _Handler.auth_header = os.environ.get("INTERVALS_WEBHOOK_AUTH_HEADER", "")
    _Handler.athlete_id = os.environ["INTERVALS_ATHLETE_ID"]
    _loop = loop
    _dispatch = dispatch or _default_dispatch

    port = int(os.environ.get("WEBHOOK_PORT", 8080))
    server = ThreadingHTTPServer(("0.0.0.0", port), _Handler)
    threading.Thread(
        target=server.serve_forever, name="intervals-webhook", daemon=True
    ).start()
    log.info("webhook listening on :%d%s", port, WEBHOOK_PATH)
    return server
