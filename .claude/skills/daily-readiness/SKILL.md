---
name: daily-readiness
description: Assess this morning's readiness from HRV, RHR, sleep and training load, then confirm or modify today's planned session. Use for the daily brief, /today, or any "how should I train today" question.
---

# Daily readiness

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

1. Write `20 Daily/YYYY-MM-DD.md` from `20 Daily/_template.md`. Fill the
   frontmatter fully — it feeds the Dataview charts.
2. If the session changed, update the intervals.icu calendar event description
   with a one-line `COACH:` note explaining the change. Never delete an event.
3. Emit the `<telegram>` block: verdict, the numbers that drove it, the session
   as it now stands, and one sentence of why. Eight lines maximum.
