"""Read overnight wellness (HRV, resting HR, sleep) from the Google Health API.

Source is the Fitbit Air, which is the only device writing these three metrics —
Coros sends steps and nothing else. See `wellness_sync` for where they land.

Two shapes matter here. Daily records (`daily-heart-rate-variability`,
`daily-resting-heart-rate`) carry a `date` object; sleep is a session with an
`interval`, so it is attributed to the date you *woke up*, matching how
intervals.icu files a night.

`list` returns points newest-first, so every read walks backwards and stops once
it passes the window. That is deliberate: the API's `filter` grammar is fiddly
and a malformed filter fails open (returns everything), while walking a sorted
list cannot silently over-read.
"""
from datetime import date, datetime, timedelta

import httpx

from . import google_oauth

BASE = "https://health.googleapis.com/v4/users/me/dataTypes"

# One scope per category: HRV/resting HR are health metrics, sleep and steps
# each have their own. Adding a scope here invalidates the stored refresh token —
# re-run scripts/google_auth.py.
SCOPES = [
    "https://www.googleapis.com/auth/googlehealth.health_metrics_and_measurements.readonly",
    "https://www.googleapis.com/auth/googlehealth.sleep.readonly",
    "https://www.googleapis.com/auth/googlehealth.activity_and_fitness.readonly",
]

# The API caps a single read at 90 days for these types.
MAX_WINDOW_DAYS = 90


def access_token() -> str:
    """Health-scoped token. Must not be the calendar grant — this API rejects a
    token carrying any scope outside its own allowlist."""
    return google_oauth.access_token("GOOGLE_HEALTH_REFRESH_TOKEN")


def _walk(data_type: str, token: str, page_size: int):
    """Yield data points newest-first, following pagination."""
    page_token = None
    while True:
        params = {"pageSize": page_size}
        if page_token:
            params["pageToken"] = page_token
        resp = httpx.get(
            f"{BASE}/{data_type}/dataPoints",
            params=params,
            headers={"Authorization": f"Bearer {token}"},
            timeout=60,
        )
        resp.raise_for_status()
        body = resp.json()
        yield from body.get("dataPoints", [])
        page_token = body.get("nextPageToken")
        if not page_token:
            return


def _payload(point: dict, key: str) -> dict:
    """Data points wrap their value in a type-keyed object; tolerate it being flat."""
    return point.get(key) or point


def _as_date(obj: dict) -> str | None:
    """A Date object is {year, month, day}, any of which may be absent."""
    try:
        return date(int(obj["year"]), int(obj["month"]), int(obj["day"])).isoformat()
    except (KeyError, TypeError, ValueError):
        return None


def daily_hrv(token: str, since: date) -> dict[str, float]:
    """RMSSD in ms, which is what intervals.icu's `hrv` field expects.

    Fitbit surfaces RMSSD measured during deep sleep; the `average` field is a
    different statistic and is only a fallback so a night is not silently lost.
    """
    out: dict[str, float] = {}
    for point in _walk("daily-heart-rate-variability", token, 1000):
        body = _payload(point, "dailyHeartRateVariability")
        day = _as_date(body.get("date", {}))
        if not day:
            continue
        if date.fromisoformat(day) < since:
            break
        value = body.get(
            "deepSleepRootMeanSquareOfSuccessiveDifferencesMilliseconds"
        ) or body.get("averageHeartRateVariabilityMilliseconds")
        if value is not None:
            out[day] = round(float(value), 1)
    return out


def daily_resting_hr(token: str, since: date) -> dict[str, int]:
    out: dict[str, int] = {}
    for point in _walk("daily-resting-heart-rate", token, 1000):
        body = _payload(point, "dailyRestingHeartRate")
        day = _as_date(body.get("date", {}))
        if not day:
            continue
        if date.fromisoformat(day) < since:
            break
        value = body.get("beatsPerMinute")
        if value is not None:
            out[day] = int(value)
    return out


def _local_date(timestamp: str, offset: str | None) -> date:
    """Wall-clock date at the time of recording.

    The record carries its own UTC offset, so this stays correct on trips rather
    than reprojecting everything into the container's timezone.
    """
    moment = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    return (moment + timedelta(seconds=int((offset or "0s").rstrip("s")))).date()


def sleep(token: str, since: date) -> dict[str, int]:
    """Seconds actually asleep, keyed by wake date.

    Naps are excluded: Fitbit flags the overnight session as `mainSleep`, and
    folding daytime sleep into the same figure would inflate the number
    `daily-readiness` grades against its 7-hour threshold.
    """
    out: dict[str, int] = {}
    for point in _walk("sleep", token, 25):  # sleep pages cap at 25; 1 returns nothing
        body = _payload(point, "sleep")
        interval = body.get("interval") or {}
        if not interval.get("endTime"):
            continue
        woke = _local_date(interval["endTime"], interval.get("endUtcOffset"))
        if woke < since:
            break
        if not (body.get("metadata") or {}).get("mainSleep"):
            continue
        minutes = (body.get("summary") or {}).get("minutesAsleep")
        if minutes is None:
            continue
        # A main sleep can still arrive as more than one session across a night.
        out[woke.isoformat()] = out.get(woke.isoformat(), 0) + int(minutes) * 60
    return out


def _civil(day: date) -> dict:
    """CivilDateTime — a zoneless wall-clock stamp, split into date and time."""
    return {
        "date": {"year": day.year, "month": day.month, "day": day.day},
        "time": {"hours": 0, "minutes": 0, "seconds": 0},
    }


def daily_steps(token: str, since: date, until: date) -> dict[str, int]:
    """Daily step totals over a closed-open range.

    Steps is an interval type, so unlike the daily metrics it has to be rolled up
    server-side. `range` is a structured field rather than the string `filter`
    grammar, so an explicit range is safe to use here.

    The server rejects the query unless `windowSizeDays * pageSize` is within the
    type's 90-day cap — that product, not the requested range, is what it checks.
    """
    out: dict[str, int] = {}
    page_token = None
    while True:
        body = {
            "range": {"start": _civil(since), "end": _civil(until)},
            "windowSizeDays": 1,
            "pageSize": MAX_WINDOW_DAYS,
        }
        if page_token:
            body["pageToken"] = page_token
        resp = httpx.post(
            f"{BASE}/steps/dataPoints:dailyRollUp",
            json=body,
            headers={"Authorization": f"Bearer {token}"},
            timeout=60,
        )
        resp.raise_for_status()
        payload = resp.json()
        for point in payload.get("rollupDataPoints", []):
            day = _as_date((point.get("civilStartTime") or {}).get("date", {}))
            count = (point.get("steps") or {}).get("countSum")
            if day and count is not None:
                out[day] = int(count)
        page_token = payload.get("nextPageToken")
        if not page_token:
            return out


def wellness_rows(days: int, include_today_steps: bool = False) -> list[dict]:
    """Rows shaped for intervals.icu's wellness-bulk PUT, newest last.

    Days with no measurement are dropped rather than written as nulls: an empty
    row would overwrite whatever is already on that date.

    `include_today_steps` exists because the two scheduled jobs sit on opposite
    sides of the day. HRV, resting HR and sleep are overnight measurements and
    are final whenever either job runs, but steps accumulate as the day goes:
    at 06:00 the count has barely started and writing it would replace a real
    total with a near-zero, while by the evening debrief it is essentially
    final. So the morning leaves today's steps alone and the evening writes them.
    """
    days = min(days, MAX_WINDOW_DAYS)
    today = date.today()
    since = today - timedelta(days=days)
    token = access_token()

    hrv = daily_hrv(token, since)
    rhr = daily_resting_hr(token, since)
    slept = sleep(token, since)
    # `daily_steps` takes a closed-open range, so today is only covered when the
    # caller has asked for it.
    until = today + timedelta(days=1) if include_today_steps else today
    stepped = daily_steps(token, since, until)

    rows = []
    for day in sorted(set(hrv) | set(rhr) | set(slept) | set(stepped)):
        row = {"id": day}
        if day in hrv:
            row["hrv"] = hrv[day]
        if day in rhr:
            row["restingHR"] = rhr[day]
        if day in slept:
            row["sleepSecs"] = slept[day]
        if day in stepped and (include_today_steps or day != today.isoformat()):
            row["steps"] = stepped[day]
        if len(row) > 1:
            rows.append(row)
    return rows
