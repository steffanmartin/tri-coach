---
name: week-planner
description: Build or rebalance a week of training and push it to the intervals.icu calendar. Use for /week, "plan my week", or after a red day forces a reshuffle.
---

# Week planner

## Inputs
Current phase from `10 Plan/ironman-macro-plan.md`, the target weekly hours and
TSS for this week's position in the block, the last 3 weeks actual load, current
CTL/ATL/TSB, known calendar constraints from `00 Meta/athlete-profile.md`.

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
two sentences. Then create the intervals.icu calendar events, with structured
workout steps so they sync to the Coros. Use bulk creation, not one call per day.
Report back only what changed versus what was already on the calendar.
