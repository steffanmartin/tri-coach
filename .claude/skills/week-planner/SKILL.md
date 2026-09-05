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

## Running is the coach's, unless Steffan asks
Steffan has a human run coach who prescribes every run in TrainingPeaks. Those
sessions are mirrored onto the intervals.icu calendar automatically and their
descriptions open with `COACH (TrainingPeaks)`.

**Never plan a run on your own initiative** — not a long run, not an easy
shakeout, not the run leg of a brick, not "the block needs one more aerobic
hour". Running volume, intensity and placement are the coach's by default, and
your remit is swim, bike and gym plus the shape of the week around the runs.

**When Steffan explicitly asks for a run, write it.** A brick with a real run
leg, a shakeout before a race, an easy recovery jog he wants on the plan — those
are his to ask for, and "the coach owns running" is not a reason to refuse. Ask
only if the request is ambiguous. What is forbidden is deciding for yourself
that the week needs running; what is fine is planning the run he asked for.

- Runs you write are your own events and behave normally — the mirror only ever
  touches events it created, so yours are never overwritten or deleted by it.
  Keep them clearly distinguishable: never put the `COACH (TrainingPeaks)`
  marker on one.
- **Never move, rewrite or delete a run carrying the coach marker**, asked or
  not. The mirror is one-way: an event you delete is re-created on the next
  sync, and an edit is overwritten the next time the coach touches that session
  in TrainingPeaks. If Steffan wants one of *those* changed, that is the
  drop/reduce conversation below.
- A run you add sits *on top of* the coach's week. Say what it does to the
  week's running load, and if it pushes the total past the block's target, say
  that too rather than quietly absorbing it.
- Count every coach run's duration and TSS toward the week's totals. They are the
  single largest input to how much bike, swim and gym the week can carry.
- Default brick construction is to place *your ride* against one of the coach's
  runs: put the bike session immediately before a coach run on the same day and
  say so in the plan. Write a run leg of your own only when Steffan asks for a
  brick as a single session.
- If a week has no coach runs at all, say so rather than planning as though none
  were coming — see the note on club days below. Do not fill the gap with running
  unless Steffan asks you to.

## Club days: Tuesday, Thursday, Saturday
The coach's Tuesday, Thursday and Saturday sessions are club sessions. They are
fixed points in the week and are **never** candidates for the review below: prefer not to drop them,
but you can suggest a reduction if the total load is too high.

They also **arrive late**. The coach usually uploads the coming week's club
sessions on the Sunday before, so an empty Tuesday, Thursday or Saturday more
than a few days out means "not uploaded yet", not "free". Reserve those days:
plan no key bike or swim into them, note in the plan that the club session is
pending, and rebalance once it lands. Filling a club day with your own key
session because the mirror looked empty is the one mistake that costs a week.

## Reviewing the coach's runs against total load
The coach sees Steffan's running. They do not see his bike, swim and gym. That
gap is yours to close: read the week's mirrored runs alongside everything else
the week holds, and say plainly when the combined load is too much.

- Judge the *total* — coach runs plus your bike, swim, gym and brick — against
  the block's target hours and TSS, the ramp rate, and current CTL/ATL/TSB.
- Where it is too much, recommend which run sessions to drop or shorten, in
  priority order, each with the reason and the number that drove it. Recommend
  the smallest change that works: a run cut from 60 to 40 minutes before a run
  cut entirely.
- **Never recommend touching a Tuesday, Thursday or Saturday session.** If the
  week is still too heavy once every other run is on the table, cut your own
  bike, swim or gym instead, and say that is what you did.
- Recommend, then stop. Do not act on a drop until Steffan has agreed to it.

### Once he agrees
1. Record it in `10 Plan/week-YYYY-Www.md`: which session, dropped or reduced to
   what, and why. That file is the record of the agreed week.
2. Append a one-line `COACH:` note to the intervals.icu event saying it was
   dropped or reduced by agreement, with the date.
3. Tell him the event itself stays on the calendar and on his watch. The mirror
   only ever reflects TrainingPeaks, so a deletion here is undone on the next
   sync — if he wants it gone for real it has to come out in TrainingPeaks,
   by him or by his coach.
4. Re-plan the rest of the week against the capacity the drop frees up.

## Where the load goes
Swim, bike and gym are planned around the club days, not through them.

- **Fill the non-club days first** — Monday, Wednesday, Friday, Sunday — up to
  the week's target hours and TSS.
- Only if the week is still short after that, add a second session onto a club
  day, and keep it easy: an aerobic swim or a gym session, never a key effort
  stacked on top of a club session.
- When a coach run is dropped or reduced by agreement, the freed capacity goes
  into bike and swim — never into a replacement run.

## Rules
- **Ramp rate**: weekly CTL ramp stays ≤ 5–7/week in base, ≤ 3–5 in build.
  Nothing above that gets written, whatever the plan table says.
- **Key sessions per week**: the run key session is the coach's and is already
  in the week. On top of it you place at most two of your own — one bike, one
  swim — and at peak no more. A run Steffan asks you for counts toward the
  week's key sessions like any other. Everything else is aerobic. Never two consecutive
  quality days in the same discipline, and never a key bike or swim the day
  before a coach run marked as a hard session.
- **Polarised-ish distribution**: ~80% of time below LT1, ~20% at or above LT2.
- **Protected**: weekend long ride, 2 swims minimum. The long run is the coach's
  and is protected by them, not by you.
- **Strength**: 2×/week in base and build 1, 1×/week from build 2, placed after a
  hard session or on an easy day — never the day before a key run.
- **Brick**: at least one per week from build 1 onward, built by default from
  your ride placed immediately before one of the coach's runs.
- Recovery week every 4th (base) or 3rd (build/peak): 55–65% of the block's volume,
  intensity *frequency* preserved but volume within sessions cut.

## Output
Write `10 Plan/week-YYYY-Www.md` with a day-by-day table and the week's intent in
two sentences. Note against any day whose session was shaped by a commitment
which commitment it was, so the reasoning survives into next week's review.
Then create the intervals.icu calendar events, with structured workout steps so
they sync to the Coros. Use bulk creation, not one call per day.

You create bike, swim, gym and brick events; runs only when Steffan asked for
them. **A run you write will not reach the watch.** The intervals.icu -> Coros
upload filters runs out, because the coach's sessions arrive there straight from
TrainingPeaks and would otherwise land twice — so say in your report that he has
to read that session off the plan rather than expecting it on the Coros.
Everything else syncs normally.

Report back only what changed versus what was already on the calendar, and end
with your drop/reduce recommendations for the coach's runs as a short numbered
list Steffan can say yes or no to.
