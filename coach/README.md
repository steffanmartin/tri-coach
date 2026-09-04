# `coach/` — the Python side

Everything here exists to get the agent to the two things it reasons over —
**intervals.icu** for numbers and the **vault** for memory — and to get its
answers back to Telegram. The coaching logic itself is not in this package; it
lives in the vault's `.claude/skills/`. See the root [CLAUDE.md](../CLAUDE.md)
for the architecture behind these splits.

| Module | Role |
|---|---|
| `telegram_bot.py` | process entry point: long-polling bot + the in-process scheduler |
| `agent.py` | the only place the Claude Agent SDK is touched |
| `vault.py` | git clone/pull/commit/push around the Obsidian vault |
| `daily_brief.py` | the 06:00 readiness job |
| `daily_debrief.py` | the 21:00 end-of-day job |
| `intervals.py` | read-only intervals.icu REST client, for the jobs only |
| `polling.py` | the wait-for-the-data loop both scheduled jobs share |
| `telegram_format.py` | markdown → Telegram entities, shared by both send paths |
| `wellness_sync.py` | push Fitbit wellness into intervals.icu; run by both jobs |
| `google_health.py` | Google Health API client (HRV, resting HR, sleep, steps) |
| `calendar_sync.py` | render Google Calendar into `00 Meta/calendar.md` |
| `google_calendar.py` | Google Calendar API client |
| `google_oauth.py` | refresh-token → access-token exchange, shared by both clients |

## Runtime core

**`telegram_bot.py`** — `main()` is what the container runs. It clones the vault
if needed, registers the `/today`, `/week`, `/debrief`, `/day` and `/status`
handlers plus a catch-all text handler, starts an `AsyncIOScheduler` holding the
two cron jobs (the morning brief and the evening debrief), and hands control to
`run_polling`. Auth is one chat-ID comparison in `_authorised`; unauthorised
updates are dropped with no reply. The command handlers are deliberately thin —
each is a one-line prompt naming a skill.

**`agent.py`** — `run(prompt, model=None)` is the single seam onto the SDK. It
pulls the vault, refreshes the calendar snapshot, runs one fresh `query()`, and
commits and pushes whatever the agent wrote. There is no conversation memory
between calls; continuity comes from the agent re-reading the vault. Also holds
`SYSTEM_PROMPT` (the hard rules, including folder ownership and medical
escalation), the intervals MCP server definition, and the tool allowlist — note
there is no Bash and no network tool, which is why the calendar has to be synced
in as a file.

**`vault.py`** — thin `subprocess` wrapper over git. `ensure_clone` at startup,
`pull` (fetch + rebase) before a turn, `commit_and_push` after. Nothing else in
the package shells out to git.

## Scheduled jobs

Both jobs have the same shape: start at a cron time, poll until the day's data
has actually landed, give up at a deadline rather than never running, then hand a
`<telegram>`-tagged prompt to `agent.run`. The loop itself lives once in
`polling.py`. Both build their prompt *per run* — a module-level f-string would
freeze `date.today()` at container start, and the scheduler holds these modules
in memory for months.

**`daily_brief.py`** — 06:00. Polls Google Health for the night's HRV, resting HR
and sleep, syncs them, and briefs; at 09:00 it briefs anyway, naming what never
arrived. Sends over the Bot API directly rather than through the bot's
`Application`. `send` and `extract_telegram` here are shared with the debrief.
Failures are sent to Telegram, never swallowed. Runnable by hand:
`python -m coach.daily_brief --no-wait`.

**`daily_debrief.py`** — 21:00. Polls intervals.icu until every planned session
for today has an activity recorded, then debriefs each one into `30 Sessions/`
and writes the day's `20 Daily/` note. It is the **only** writer of the daily
note — `daily-brief` no longer writes one, because a note written at 06:00
describes a day that has not happened. At 23:00 it stops waiting and says what
never uploaded rather than guessing whether the session happened. Runnable by
hand: `python -m coach.daily_debrief --no-wait`.

Polling intervals.icu here, and Google Health in the morning, is not an
inconsistency: wellness is in intervals.icu only because `wellness_sync` puts it
there, so polling for it would be watching our own writes, whereas activities
come from Coros and are genuinely upstream of us.

**`polling.py`** — `poll_until(check, on_error, deadline, interval_min, label)`.
Runs `check` off-thread (the event loop is busy long-polling Telegram), logs and
retries on failure instead of raising, and never sleeps past the deadline, so the
last poll lands exactly on it.

**`intervals.py`** — read-only REST client, `activities(day)` and
`planned_workouts(day)`. Exists purely so a scheduled job can decide whether it
is worth waking the agent; it is deliberately not a general client, since a
second numbers source is what the wellness sync exists to prevent. Planned events
are narrowed to Run/Ride/Swim, because gym and mobility never produce an upload
and would hold the poll at the deadline every night. It goes to REST rather than
through the intervals MCP because it runs before there is an agent turn to host
an MCP tool call.

**`wellness_sync.py`** — reads days from `google_health` and PUTs them to
intervals.icu's `wellness-bulk` endpoint. Both scheduled jobs call it. Writes are
upserts keyed by date, so re-running a window corrects it; the CLI takes
`--days`, `--dry-run` and `--today-steps` and warns when a field came back empty
for the whole window. This is what keeps "all numbers come from intervals.icu"
literally true — the agent never sees this path.

**`calendar_sync.py`** — renders the next three weeks into `00 Meta/calendar.md`,
grouped by day, with empty days written out explicitly so "nothing scheduled" is
distinguishable from "not synced". `refresh_quietly()` is the best-effort variant
`agent.run` calls on every turn: it never raises, so a Google outage leaves the
stale snapshot in place instead of taking the bot down. The file is rewritten
only when its content changes, so an unchanged calendar produces no commit.

## Google clients

Each client is an API reader with no opinion about the vault; the sync job above
it decides where the result lands.

**`google_health.py`** — `wellness_rows(days, include_today_steps)` returns rows for
intervals.icu. HRV and resting HR are daily records; sleep is a session
attributed to the wake date and filtered to `mainSleep` so naps don't inflate it;
steps are rolled up server-side and gated on `include_today_steps`: the morning
skips today's, since the count has barely started, and the evening debrief writes
it once the day is essentially over. Days with no measurement are dropped rather
than written as nulls.

**`google_calendar.py`** — `events(token, horizon_days)` flattens all-day and
timed events into one shape, expands recurring series, and skips cancelled events
and ones Steffan himself declined. `GOOGLE_CALENDAR_IDS` widens it beyond the
primary calendar.

**`google_oauth.py`** — `access_token(refresh_var)` exchanges a refresh token
named by env var. Health and calendar are **one OAuth client but two separate
grants**, and merging them breaks wellness silently: the Health API 403s any
token that also carries the calendar scope. Error messages here are written for
someone reading them as a Telegram alert at 06:00, so they name both the Azure
and the local place to set the variable. Tokens are minted by
[`scripts/google_auth.py`](../scripts/google_auth.py).

## Formatting

**`telegram_format.py`** — `text_chunks(markdown)` converts model markdown into
`(text, entities)` pairs, split under Telegram's 4096-character cap. Uses
entities rather than `parse_mode="MarkdownV2"` because the latter would require
the model to never miss one of ~18 escaped characters. Non-text items (code
files, diagrams) are dropped.
