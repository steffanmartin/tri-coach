# Privacy policy — tri-coach

**Last updated: 4 September 2026**

tri-coach is a personal, single-user training assistant, run by one athlete for
their own use. It is not a commercial product, it has no user accounts, and it
does not process data belonging to anyone other than its operator.

Source: https://github.com/steffanmartin/tri-coach

## Who runs it

Steffan Martin. Contact: steffankunoy@gmail.com

## What data it handles

| Data | Source | Why |
|---|---|---|
| Activities (rides, runs, swims) and their interval detail | intervals.icu | analysing completed sessions |
| Wellness (HRV, resting HR, sleep, steps) | Google Health, from a Fitbit device | assessing daily readiness |
| Planned workouts and calendar events | intervals.icu | knowing what was prescribed, and adjusting it |
| Calendar events (next three weeks) | Google Calendar | scheduling training around real commitments |
| Chat messages | Telegram | the interface to the assistant |

All of it belongs to the operator, about the operator. No other person's data is
collected, requested, or accepted — the Telegram interface rejects every chat ID
except the operator's own.

## Where it goes

- **A private git repository.** Training notes and plans are written to a private
  GitHub repository owned by the operator. This is the only durable store; there
  is no database and no hosted service holding this data.
- **Anthropic (Claude API).** Training data and messages are sent to Anthropic's
  API to generate coaching analysis, under Anthropic's own terms and privacy
  policy: https://www.anthropic.com/legal/privacy
- **The container host.** The application runs on a Linux virtual private
  server rented from one.com and administered solely by the operator.

Nothing is sold, shared with advertisers, used to train models, or disclosed to
any third party beyond those named above. There is no analytics or tracking of
any kind.

## intervals.icu access

tri-coach requests these OAuth scopes, and uses each of them:

- `ACTIVITY:READ` — read completed activities to analyse them
- `CALENDAR:WRITE` — read planned workouts, and adjust them when the day's
  readiness calls for it. Events are moved or their descriptions rewritten;
  the application never deletes a calendar event.
- `WELLNESS:WRITE` — write HRV, resting heart rate, sleep and step data
  collected from the operator's Fitbit, so intervals.icu remains the single
  source of numeric truth
- `SETTINGS:READ` — read sport settings (FTP, threshold pace, CSS) to compare
  efforts against current thresholds

Access can be revoked at any time by the operator at
https://intervals.icu/settings, which also stops webhook delivery.

## Retention and deletion

Data persists in the operator's private git repository for as long as the
operator keeps it, and is deleted by deleting that repository. Deleting the
intervals.icu account or revoking the application's access removes tri-coach's
ability to read anything further.

## Changes

Changes to this policy are committed to the repository above and visible in its
git history.
