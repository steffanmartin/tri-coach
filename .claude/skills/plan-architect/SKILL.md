---
name: plan-architect
description: Build or revise the full multi-month Ironman macro plan. Use when setting up a new season, changing race date, or after a block-boundary review. Run this with the planner model.
---

# Plan architect

Long-horizon work. Slow down, look at the data, then write.

## 1. Anchor
Race date, course profile (flat vs climbing, wetsuit likely, expected temps),
realistic goal time and its splits, hard calendar constraints (travel, work,
holidays), and any tune-up races.

## 2. Diagnose the limiter
Compare current thresholds against what the goal splits demand:
- **Swim** — CSS vs required pace over 3.8 km, allowing for wetsuit and draft.
- **Bike** — required NP at IM intensity (IF 0.65–0.72 for a first IM), as a
  fraction of current FTP. If required NP > 0.72 × FTP, the bike is the limiter.
- **Run** — an IM marathon is run at roughly 75–80% of open-marathon pace. If
  standalone run fitness already clears the goal split, the run is **not** the
  limiter, and adding run volume mostly buys injury risk.

State the limiter explicitly in the plan. Every block allocation follows from it.

## 3. Periodise
Prep → Base → Build 1 → Build 2 → Peak → Taper. For each block record: weeks,
weekly hours range, weekly TSS target, target CTL at block end, the 2–3 sessions
that define the block, and the exit test.

Non-negotiables:
- CTL ramp ≤ 5–7/wk in base, ≤ 3–5/wk in build. Model it week by week; if the
  arithmetic doesn't reach the target CTL by race week, extend the block or lower
  the target — do not raise the ramp.
- Fuelling is a trained progression: schedule the g CHO/hr build across long rides.
- Taper: 3 weeks, volume to roughly 60/45/30% of peak, intensity frequency held.
- One long-course tune-up race 8–12 weeks out, as a full fuelling and pacing rehearsal.
- A full race-simulation day 5–7 weeks out.

## 4. Write
`10 Plan/ironman-macro-plan.md`: the block table, the limiter rationale, the CTL
curve, the fuelling progression, the equipment/logistics deadlines. Then create
intervals.icu Annual Training Plan entries with weekly load targets — the ATP, not
52 weeks of individual workouts. Detailed weeks come from `week-planner`, one week
at a time, so the plan can respond to what actually happens.
