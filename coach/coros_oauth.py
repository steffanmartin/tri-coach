"""Refresh-token exchange for the COROS MCP connector.

COROS has no developer console: the OAuth client is created at runtime by
dynamic registration (scripts/coros_auth.py), so the client id in .env is one
*we* minted rather than one COROS issued us. It is a public client — PKCE, no
secret — which is why nothing here sends one.

The regional endpoint matters. https://mcp.coros.com/mcp advertises itself as a
different resource than it redirects to, and strict MCP clients refuse the
mismatch, so both this module and .env pin the EU host directly.
"""
import os

import httpx

BASE = os.environ.get("COROS_MCP_BASE", "https://mcpeu.coros.com")
TOKEN_URL = f"{BASE}/oauth2/token"
MCP_URL = f"{BASE}/mcp"


def access_token() -> str:
    """Mint a short-lived access token from COROS_REFRESH_TOKEN.

    If COROS ever rotates the refresh token on exchange, this will start failing
    on the *second* run rather than the first, because the container cannot write
    a new token back to .env. That failure mode is what the explicit error below
    is for — the fix is to re-run scripts/coros_auth.py, not to debug the MCP.
    """
    resp = httpx.post(
        TOKEN_URL,
        data={
            "grant_type": "refresh_token",
            "refresh_token": os.environ["COROS_REFRESH_TOKEN"],
            "client_id": os.environ["COROS_CLIENT_ID"],
        },
        timeout=30,
    )
    if resp.status_code >= 400:
        raise RuntimeError(
            f"COROS refused the refresh token ({resp.status_code}): {resp.text}. "
            "Re-mint it with `uv run python scripts/coros_auth.py`."
        )
    return resp.json()["access_token"]
