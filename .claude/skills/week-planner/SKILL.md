---
name: week-planner
description: Build or rebalance a week of training and push it to the intervals.icu calendar. Use for /week, "plan my week", or after a red day forces a reshuffle.
---

# Week planner

## Inputs
**Read `00 Meta/calendar.md` first, before drafting anything.** It is a synced
snapshot of Steffan's Google Calendar for the next three weeks and it decides
which days are actually available — draft the week against real free time rather
than fitting sessions in afterwards.

Then: current phase from `10 Plan/ironman-macro-plan.md`, the target weekly hours
and TSS for this week's position in the block, the last 3 weeks actual load,
current CTL/ATL/TSB, and the standing constraints in `00 Meta/athlete-profile.md`.

## Reading the calendar
- The snapshot lists every day in the window; a day saying "nothing scheduled"
  is genuinely free. The window line at the top gives the date it was taken —
  if that is not today, say so rather than trusting it silently.
- Events marked `(marked free)` are on the calendar but do not block training.
  Everything else occupies its slot.
- **Some entries are training, not obstacles.** Squad sessions, club runs, races
  and lessons are sessions Steffan has already committed to. Build the week
  around them and count their load — never prescribe a second session of the
  same discipline that day to "cover" the plan. If a squad session collides with
  what the block needs, adapt the rest of the week to it; it is fixed and your
  plan is not. When you cannot tell whether an entry is training, ask rather
  than assume.
- Long or early commitments constrain the *neighbouring* day too: no key session
  the morning after an event ending late, and no long ride the day before travel.
- The profile's standing constraints (work pattern, fixed squad swims) still
  apply. Where the two disagree, the calendar wins for that specific date — it
  is the more recent statement of what is true.
- Never move a calendar commitment to make a session fit. Move the session.
- If the snapshot is missing or its window has clearly gone stale, plan from the
  profile alone and say plainly that you did so. Do not guess at his week.

## Rules
- **Ramp rate**: weekly CTL ramp stays ≤ 5–7/week in base, ≤ 3–5 in build.
  Nothing above that gets written, whatever the plan table says.
- **Key sessions per week**: normally 3 (one per discipline), 4 at peak. Everything
  else is aerobic. Never two consecutive quality days in the same discipline.
- **Polarised-ish distribution**: ~80% of time below LT1, ~20% at or above LT2.
- **Protected**: weekend long ride, weekend or midweek long run, 2 swims minimum.
- **Strength**: 2×/week in base and build 1, 1×/week from build 2, placed after a
  hard session or on an easy day — never the day before a key run.
- **Brick**: at least one per week from build 1 onward.
- Recovery week every 4th (base) or 3rd (build/peak): 55–65% of the block's volume,
  intensity *frequency* preserved but volume within sessions cut.

## Output
Write `10 Plan/week-YYYY-Www.md` with a day-by-day table and the week's intent in
two sentences. Note against any day whose session was shaped by a commitment
which commitment it was, so the reasoning survives into next week's review.
Then create the intervals.icu calendar events, with structured workout steps so
they sync to the Coros. Use bulk creation, not one call per day.
Report back only what changed versus what was already on the calendar.
