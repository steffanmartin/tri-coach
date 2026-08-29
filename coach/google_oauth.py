"""Refresh-token exchange, shared by the health and calendar clients.

There is one OAuth client but two grants, and they must not be merged: the
Google Health API allowlists its own scopes and 403s any token that also carries
the calendar scope. So each caller names the env var holding *its* refresh
token. See SCOPE_SETS in scripts/google_auth.py.
"""
import os

import httpx

TOKEN_URL = "https://oauth2.googleapis.com/token"


def access_token(refresh_var: str) -> str:
    """Mint a short-lived access token from the refresh token in `refresh_var`.

    Refresh tokens do not expire, so the container never needs a browser —
    see scripts/google_auth.py.
    """
    resp = httpx.post(
        TOKEN_URL,
        data={
            "grant_type": "refresh_token",
            "refresh_token": os.environ[refresh_var],
            "client_id": os.environ["GOOGLE_HEALTH_CLIENT_ID"],
            "client_secret": os.environ["GOOGLE_HEALTH_CLIENT_SECRET"],
        },
        timeout=30,
    )
    if resp.status_code == 400 and "invalid_grant" in resp.text:
        raise RuntimeError(
            f"Google refused {refresh_var} (invalid_grant). Usual cause: the "
            "OAuth app is back in 'Testing' publishing status, which expires "
            "refresh tokens after 7 days. Publish it, then re-run "
            "scripts/google_auth.py for this scope set."
        )
    resp.raise_for_status()
    return resp.json()["access_token"]
