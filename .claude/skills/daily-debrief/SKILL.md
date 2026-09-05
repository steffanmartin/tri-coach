---
name: daily-debrief
description: Close out the day — what was actually trained, how it went against what was prescribed, and what the body did. Writes the day's daily note, reading the session notes already written on upload. Use for the 21:00 job, /day, or "how did today go".
---

# Daily debrief

This runs at the end of the day, not the start. `daily-brief` predicts;
this records. It is the **only** writer of `20 Daily/YYYY-MM-DD.md` — the
morning brief no longer writes one, so if you skip step 3 the day has no note.

**Do not write `30 Sessions/`.** Each session was already debriefed as it
uploaded, by `session-debrief` fired from the intervals.icu webhook. Those notes
are an input to this job, not an output of it. Writing one here would produce a
second note for a session that already has one.

## 1. Gather (never skip, never guess)

- `00 Meta/athlete-profile.md` and `00 Meta/coaching-principles.md`
- This week's plan, `10 Plan/week-YYYY-Www.md` — what today was *supposed* to be
- intervals.icu activities for today, with per-interval detail for each
- **Today's `30 Sessions/` notes** — one per activity, written when it uploaded.
  These are your account of how each session went; read them rather than
  re-deriving the analysis from the raw activity data.
- Today's planned calendar events, **including the description**. If the morning
  changed a session it left a `COACH:` note there, and that note is the only
  durable record of the morning's call — read it before judging execution
  against the original prescription.
- Today's wellness: `hrv`, `restingHR`, `sleepSecs`, `steps`, plus `ctl`, `atl`,
  `TSB` (= ctl − atl) and `rampRate`
- The last 7 files in `20 Daily/`

If an activity is missing, say so. A session whose upload has not arrived is not
the same as a session that did not happen — do not decide which it was.

## 2. Reconcile the day's sessions

Every activity recorded today should already have a `30 Sessions/` note. Line the
two up and account for both kinds of gap — the prompt tells you the counts:

- **A planned session with no activity.** The upload has not arrived, or the
  session did not happen. Say which is unknown; do not pick one.
- **An activity with no session note.** The webhook never reached the coach, or
  its debrief failed. Note it in the change log as un-debriefed and summarise it
  at surface level only — do not write the missing note here, and do not pass it
  off as analysed.

## 3. Write the daily note

Write `20 Daily/YYYY-MM-DD.md` from `20 Daily/_template.md`, filling the
frontmatter fully — it feeds the Dataview charts, and a blank field is not the
same as a missing measurement, so say which it is.

- `## Verdict` — the day in two or three sentences, in hindsight. Was the day's
  training what the week needed?
- `## Signals` — this morning's wellness numbers against their baselines, plus
  today's steps. Same 7-day vs 60-day framing `daily-brief` uses.
- `## Planned vs actual` — the plan's session, the prescription as it stood
  after any morning change (the `COACH:` note), and what was actually done.
  Name the gap plainly when there is one.
- `## Sessions` — one line per `30 Sessions/` note for today, linking each, plus
  any activity that has no note yet.
- `## Change log` — anything moved, any tool call that failed, any data anomaly.

One note per date. On a re-run, rewrite it rather than appending a second copy.

## 4. Flag forward

Say what tomorrow morning needs to know: a key session missed, a session that
ran far harder or longer than it was billed, a pain report, a wellness or
load number that does not look real. Put it in the `## Change log` so
`daily-brief` picks it up when it reads back the last 7 days.

Escalation is not optional and does not soften in the evening: sharp or
localised pain, fever, or three consecutive red readiness days means "see a
physio or GP", not a modified session tomorrow. Say it plainly and stop
offering training modifications.

## 5. Emit the `<telegram>` block

Eight lines maximum: what was done, how it went against what was prescribed,
one line of health, one line on what tomorrow holds.

**If nothing was logged today**, that is a normal outcome, not a failure. Two or
three lines — nothing recorded, today's steps, tomorrow's session — and still
write the daily note with `execution: not done`. Do not manufacture a session
and do not go silent.
