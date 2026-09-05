---
name: daily-brief
description: Assess this morning's readiness from HRV, RHR, sleep and training load, then confirm or modify today's planned session. Use for the daily brief, /today, or any "how should I train today" question.
---

# Daily brief

## 1. Gather (never skip, never guess)

- `00 Meta/athlete-profile.md` and `00 Meta/coaching-principles.md`
- intervals.icu wellness, **last 60 days**: `hrv`, `hrvSDNN`, `restingHR`,
  `sleepSecs`, `sleepScore`, `weight`, plus `soreness`/`fatigue`/`mood` if logged
- intervals.icu fitness: `ctl`, `atl`, `TSB` (= ctl − atl), `rampRate`
- Yesterday's activity: planned vs actual load, RPE, aerobic decoupling
- Today's planned event(s) from the calendar
- The last 7 files in `20 Daily/`

If wellness for today is missing, say so and grade on what exists — do not
silently substitute yesterday's numbers.

## 2. Score

Baselines: 7-day rolling mean vs 60-day mean and SD. Compute, don't eyeball.

| Signal | Green | Amber | Red |
|---|---|---|---|
| HRV (7d mean vs 60d) | within 0.5 SD | 0.5–1.0 SD below | >1.0 SD below, or 2 straight days >1 SD below |
| Resting HR vs 30d | ≤ +3 bpm | +4 to +7 | ≥ +8 |
| Sleep | ≥7h | 6–7h | <6h, or two nights <6h |
| Subjective | fine | one flag | pain, fever, sore throat |

**Overall = worst individual signal**, with one exception: a single amber against
otherwise green signals stays green. Any red is red.

TSB is context, not a grade. Deep negative TSB during a build block is expected
and is *not* a reason to back off on its own — only when it coincides with amber
or red physiology.

## 3. Decide

- **Green** — run the session as written.
- **Amber** — keep the session and its duration, cut the *last* interval set, or
  drop the target to the bottom of the prescribed band. Never both.
- **Red** — replace with Z1 aerobic or full rest. Move the key session, don't bin
  it: reschedule it into the week and rebalance so the weekly key sessions still
  land. Weekend long ride and long run are protected — displace midweek quality first.

Guardrails:
- Do not downgrade two consecutive key sessions without also re-planning the week
  (invoke `week-planner`).
- Never add volume or intensity beyond the plan on a green day. Green means "as
  written", not "feel free".
- Three consecutive red days, any fever, or sharp/localised pain: recommend a
  physio or GP. Say it plainly and stop offering training modifications.

## 4. Write and act

1. **Do not write `20 Daily/`.** The daily note is written once, at the end of
   the day, by the `daily-debrief` skill — a note written at 06:00 describes a
   day that has not happened yet, and two writers on one file would fight.
2. If the session changed, update the intervals.icu calendar event description
   with a one-line `COACH:` note explaining the change. Never delete an event.
   This matters more than it used to: that description is now the **only**
   durable record of this morning's decision, and it is what the evening debrief
   reads to judge execution against what was actually prescribed. If you changed
   a session and did not manage to write the note, say so in the `<telegram>`
   block so the change is not silently lost.

   **If the session is a run whose description opens with `COACH (TrainingPeaks)`,
   it belongs to Steffan's human run coach and is mirrored from their calendar.**
   Add the `COACH:` note as normal, but do not otherwise move, rewrite or delete
   it, and do not add a run of your own alongside it unless Steffan asks for one.
   On a red day, say in the `<telegram>` block what you would change about it
   and that it is the run
   coach's call — advising Steffan is yours to do, rewriting their prescription
   is not. Note also that the mirror is one-way: if the coach edits that session
   in TrainingPeaks later today, your `COACH:` note on it is overwritten, so for
   a coach run put the reasoning in the `<telegram>` block too rather than
   leaving it only on the event.
3. Emit the `<telegram>` block: verdict, the numbers that drove it, the session
   as it now stands, and one sentence of why. Eight lines maximum.
