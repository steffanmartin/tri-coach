"""One-off: mint the COROS refresh token. Run on your laptop, not in the container.

COROS has no developer console and issues no long-lived API key. The MCP server
speaks OAuth with dynamic client registration, so this script does three things
in one pass:

  1. registers a fresh public OAuth client (PKCE, no secret) with COROS,
  2. opens the consent page and catches the code on a loopback port,
  3. exchanges it for a refresh token.

Both printed lines go in .env. Unlike the Google grant, we register the client
here rather than in a console, so COROS_CLIENT_ID is meaningless without the
COROS_REFRESH_TOKEN minted alongside it — re-run this to replace *both*.

    uv run python scripts/coros_auth.py
    uv run python scripts/coros_auth.py --list-tools   # what the grant can do

`--list-tools` needs the two vars already exported and just dumps the live tool
list. Use it after a COROS release rather than trusting this file: the connector
is young and its tool names are not a stable contract.

The loopback port must match the redirect URI registered in step 1, so change
both together or not at all.
"""
import argparse
import base64
import hashlib
import http.server
import os
import secrets
import sys
import threading
import urllib.parse
import webbrowser

import httpx

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from coach.coros_oauth import BASE, MCP_URL, TOKEN_URL, access_token  # noqa: E402

REGISTER_URL = f"{BASE}/connect/register"
AUTH_URL = f"{BASE}/oauth2/authorize"
SCOPES = "openid mcp.tools offline_access"  # offline_access is what buys the refresh token
PORT = 8765
REDIRECT = f"http://127.0.0.1:{PORT}/callback"


def _register() -> str:
    resp = httpx.post(
        REGISTER_URL,
        json={
            "client_name": "tri-coach",
            "redirect_uris": [REDIRECT],
            "grant_types": ["authorization_code", "refresh_token"],
            "response_types": ["code"],
            "token_endpoint_auth_method": "none",
            "scope": SCOPES,
        },
        timeout=30,
    )
    if resp.status_code >= 400:
        sys.exit(f"Client registration failed ({resp.status_code}): {resp.text}")
    return resp.json()["client_id"]


def _catch_code() -> str:
    """Serve exactly one request on the loopback port and return its `code`."""
    caught: dict[str, str] = {}

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            caught.update({k: v[0] for k, v in query.items()})
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"<h2>COROS connected. Close this tab.</h2>")

        def log_message(self, *_):  # keep the terminal readable
            pass

    server = http.server.HTTPServer(("127.0.0.1", PORT), Handler)
    threading.Thread(target=server.handle_request, daemon=True).start()
    print(f"Waiting for the COROS redirect on {REDIRECT} ...")
    while not caught:
        threading.Event().wait(0.3)
    server.server_close()
    if "code" not in caught:
        sys.exit(f"COROS returned no code: {caught}")
    return caught["code"]


def _list_tools() -> None:
    """Dump the live tool list, so the skills can be written against real names."""
    resp = httpx.post(
        MCP_URL,
        headers={
            "Authorization": f"Bearer {access_token()}",
            "Accept": "application/json, text/event-stream",
        },
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
        timeout=30,
    )
    print(resp.status_code)
    print(resp.text)


def main() -> None:
    parser = argparse.ArgumentParser(description="Mint a COROS refresh token.")
    parser.add_argument(
        "--list-tools", action="store_true",
        help="skip the grant; dump the tool list for the token already in the env",
    )
    args = parser.parse_args()
    if args.list_tools:
        return _list_tools()

    client_id = _register()

    # PKCE is not optional here: the client is public, so the verifier is the
    # only thing binding the code to us.
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()
    ).decode().rstrip("=")
    state = secrets.token_urlsafe(16)

    params = {
        "client_id": client_id,
        "redirect_uri": REDIRECT,
        "response_type": "code",
        "scope": SCOPES,
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    url = f"{AUTH_URL}?{urllib.parse.urlencode(params)}"
    print(f"\nOpening COROS consent. If nothing opens, paste this:\n\n   {url}\n")
    webbrowser.open(url)
    code = _catch_code()

    resp = httpx.post(
        TOKEN_URL,
        data={
            "grant_type": "authorization_code",
            "code": code,
            "client_id": client_id,
            "redirect_uri": REDIRECT,
            "code_verifier": verifier,
        },
        timeout=30,
    )
    if resp.status_code >= 400:
        sys.exit(f"Token exchange failed ({resp.status_code}): {resp.text}")

    token = resp.json().get("refresh_token")
    if not token:
        sys.exit(
            "No refresh_token returned — the grant came back without "
            f"offline_access. Scopes granted: {resp.json().get('scope')!r}"
        )

    print("\nAdd BOTH to .env (they are a pair; neither works alone):\n")
    print(f"COROS_CLIENT_ID={client_id}")
    print(f"COROS_REFRESH_TOKEN={token}")


if __name__ == "__main__":
    main()
