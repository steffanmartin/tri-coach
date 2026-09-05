---
name: session-debrief
description: Analyse a completed activity against what was prescribed and write a session note. Use for /debrief, "how was that session", or after any key workout.
---

# Session debrief

This now runs **once per activity, as soon as it uploads** — the intervals.icu
ACTIVITY_UPLOADED webhook triggers it, minutes after the session ends, rather
than the evening job batching every session at 21:00. It is the **only** writer
of `30 Sessions/`; `daily-debrief` reads these notes and no longer produces them.

Pull the activity summary, its per-interval breakdown, and the planned event it
maps to. Then:

1. **Execution** — actual vs target for each interval (power, pace, HR). Flag
   drift >5% and fade across sets.
2. **Aerobic decoupling** — Pw:HR or Pa:HR over the steady portion. Above 5% on a
   long aerobic session means durability is the limiter; note it and watch the trend.
3. **Fuelling** — for anything over 90 min, was g CHO/hr on target for the block?
   This is a tracked progression, not an afterthought.
4. **Verdict** — one of: nailed it / close enough / missed, and the single most
   likely reason (fatigue, pacing, fuelling, heat, terrain, wrong target).
5. **Threshold check** — if this was a max effort, compare against current FTP /
   threshold pace / CSS in sport settings. Suggest an update only when two
   independent efforts agree; never bump thresholds off one good day.

## Write the note

`30 Sessions/YYYY-MM-DD-<slug>.md`, with this frontmatter:

```yaml
---
type: session
date: YYYY-MM-DD
sport: Run | Ride | Swim | ...
activity_id: i123456789    # the intervals.icu activity id, exactly as given
verdict: nailed it | close enough | missed
---
```

**`activity_id` is not optional and must be the real id.** A webhook is re-fired
with exponential backoff until it is acknowledged, so the same activity can
arrive more than once; that field is the only thing that tells the second
delivery the work is already done. A note without it means the session gets
debriefed twice, and the day's note then counts it twice.

Link to the daily note and the plan week. Keep it under 200 words. If nothing
notable happened, say so in two lines.

Do not write `20 Daily/` from here — the evening `daily-debrief` owns that file
and will read this note when it closes the day out.
