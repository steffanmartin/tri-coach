"""One-off: mint the Google refresh token. Run on your laptop, not in the container.

One grant per scope set, never one grant for all of them — see SCOPE_SETS for
why the health and calendar tokens have to stay apart.

Google Cloud console setup first (one time):

  1. Create (or pick) a project, enable the Google Health API **and the Google
     Calendar API**. A scope that is granted but whose API is not enabled still
     mints a token happily and then 403s on the first call.
  2. Google Auth Platform -> Audience -> **Publish app**, so publishing status is
     "In production". Do NOT leave it in "Testing" and add yourself as a test
     user: testing-status refresh tokens expire after 7 days, which would break
     the sync weekly and put a browser back in the loop. Publishing needs no
     verification under 100 users — you click through one "unverified app"
     warning at consent (Advanced -> Go to tri-coach) and the token then lasts.
  3. Google Auth Platform -> Data access -> Add or remove scopes, and add every
     scope in SCOPE_SETS below. Consent only offers what is listed there.
  4. Credentials -> Create OAuth client ID -> application type **Web application**
     -> Authorised redirect URI: https://www.google.com
  5. Export the client id and secret, then run this script once per scope set:

     export GOOGLE_HEALTH_CLIENT_ID=...
     export GOOGLE_HEALTH_CLIENT_SECRET=...
     uv run python scripts/google_auth.py --scopes health
     uv run python scripts/google_auth.py --scopes calendar

Google matches the redirect URI as an exact string — https://google.com and
https://www.google.com are different URIs, and a mismatch fails the request with
`redirect_uri_mismatch`. Point this at whatever the client actually has, either
with --redirect-uri or GOOGLE_HEALTH_REDIRECT_URI. It is only used to bounce the
code back; nothing is served there.

Personal use needs no security review: restricted-scope verification is only
required above 100 users, and you are authorising your own project against your
own account.

Run it once per scope set — `--scopes health`, then `--scopes calendar` — and put
each printed line in .env. The refresh tokens do not expire, so the container
never sees a browser again.
"""
import argparse
import os
import sys
import urllib.parse

import httpx

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from coach.google_health import SCOPES as HEALTH_SCOPES  # noqa: E402

# Read-only, and read-only is the ceiling: the coach reasons about what the day
# already contains, it does not write to a calendar the athlete shares with
# other people. `calendar.readonly` rather than `calendar.events.readonly`
# because listing the calendars is what lets you pick which one to read.
CALENDAR_SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]

# One refresh token per scope set, and they must NOT be merged into a single
# grant. health.googleapis.com allowlists its own scopes and rejects the whole
# request if the token carries anything else — a bundled token 403s every health
# call with DISALLOWED_OAUTH_SCOPES / "cl_readonly", while calendar keeps
# working, so the breakage looks like a health outage rather than a scope
# problem. Google cannot narrow scopes at refresh time either, so separate
# grants are the only way to hold both.
SCOPE_SETS = {
    "health": (HEALTH_SCOPES, "GOOGLE_HEALTH_REFRESH_TOKEN"),
    "calendar": (CALENDAR_SCOPES, "GOOGLE_CALENDAR_REFRESH_TOKEN"),
}

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
DEFAULT_REDIRECT = os.environ.get("GOOGLE_HEALTH_REDIRECT_URI", "https://www.google.com")


def main() -> None:
    parser = argparse.ArgumentParser(description="Mint a Google refresh token.")
    parser.add_argument(
        "--scopes", choices=sorted(SCOPE_SETS), required=True,
        help="which grant to mint; run once per set, they cannot share a token",
    )
    parser.add_argument(
        "--redirect-uri", default=DEFAULT_REDIRECT,
        help="must match the OAuth client exactly (default: %(default)s)",
    )
    parser.add_argument("--code", help="skip straight to the exchange with a code you already have")
    args = parser.parse_args()
    redirect = args.redirect_uri
    scopes, token_var = SCOPE_SETS[args.scopes]

    client_id = os.environ["GOOGLE_HEALTH_CLIENT_ID"]
    client_secret = os.environ["GOOGLE_HEALTH_CLIENT_SECRET"]

    params = {
        "client_id": client_id,
        "redirect_uri": redirect,
        "response_type": "code",
        "scope": " ".join(scopes),
        "access_type": "offline",   # without this there is no refresh token
        "prompt": "consent",        # force one, even if you have consented before
    }
    if args.code:
        code = urllib.parse.unquote(args.code.strip())
    else:
        print(f"Redirect URI: {redirect}  (must match the OAuth client exactly)\n")
        print("1. Open this URL and approve:\n")
        print(f"   {AUTH_URL}?{urllib.parse.urlencode(params)}\n")
        print(f"2. You land on {redirect}. Copy the `code` parameter out of the address bar.")
        print("   (It is URL-encoded; paste it exactly as shown.)\n")
        code = urllib.parse.unquote(input("Paste code: ").strip())

    resp = httpx.post(
        TOKEN_URL,
        data={
            "code": code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect,  # must match the authorise step exactly
            "grant_type": "authorization_code",
        },
        timeout=30,
    )
    if resp.status_code != 200:
        sys.exit(f"Token exchange failed ({resp.status_code}): {resp.text}")

    token = resp.json().get("refresh_token")
    if not token:
        sys.exit(
            "No refresh_token returned. This happens when the grant already exists — "
            "revoke the app at https://myaccount.google.com/permissions and retry."
        )

    print("\nAdd to .env:\n")
    print(f"{token_var}={token}")


if __name__ == "__main__":
    main()
