# vault-template

Seed content for a fresh coaching vault. It is copied into the vault repo **once**,
at setup, and is never read at runtime — the bot only ever looks at the real vault
at `VAULT_PATH`. Editing a file here changes what the *next* vault starts with; to
change the live vault, edit the live vault.

```bash
gh repo create triathlon-brain --private
git clone git@github.com:you/triathlon-brain.git
cp -r vault-template/* triathlon-brain/
cd triathlon-brain && git add -A && git commit -m "seed" && git push
```

Then open that folder as an Obsidian vault and install the **Obsidian Git**
plugin (auto-pull on start, auto-commit-and-push every 10 min).

## The folders it creates

| Folder | Written by | Purpose |
|---|---|---|
| `00 Meta/` | you (+ `calendar_sync`) | Standing inputs. Read-only to the agent. |
| `10 Plan/` | the agent | Macro plan, plus one file per detailed week. |
| `20 Daily/` | the agent | One note per day: readiness verdict and prescription. |
| `30 Sessions/` | the agent | Session debriefs, `YYYY-MM-DD-<slug>.md`. |
| `40 Journal/` | you | Free-form notes. The agent reads, never edits. |
| `50 Races/` | you | Race plans and race reports. Same rule. |

That ownership split is what keeps Obsidian's auto-commits and the agent's
commits from ever conflicting — they never write the same files. `30 Sessions/`,
`40 Journal/` and `50 Races/` ship empty (git won't track empty directories, so
create them by hand after copying, or drop a `.gitkeep` in each).

`00 Meta/calendar.md` is not seeded: `coach/calendar_sync.py` creates and owns it,
rewriting the next three weeks of Google Calendar on every turn.

## What's in each seeded file

### `00 Meta/athlete-profile.md`
Identity, thresholds (FTP, swim CSS, run threshold, LTHR, max HR), target race and
goal, training history, constraints, injury history, preferences. **Fill in the TBDs
before the first planning run.** Every zone and ramp calculation downstream is
derived from the thresholds table, so a stale value here is wrong everywhere — keep
the set-on dates honest, and retest anything older than ~8 weeks.

### `00 Meta/coaching-principles.md`
The guardrails the coach works within: ramp-rate ceilings (≤5–7 CTL/wk in base,
≤3–5 in build), 80/20 intensity distribution, a recovery week every 3rd–4th, and
the medical-escalation rule. **These override plan files when the two conflict**,
and the skills cite them by name — so this is the file to edit when you want to
change how the coach reasons, not just what it prescribes.

### `10 Plan/ironman-macro-plan.md`
The season skeleton: `race_date` in the frontmatter, block table, weekly hour/TSS
targets and CTL trajectory. Set the race date, then run `plan-architect` from
claude.ai (not Telegram — it's a long conversation) to fill in the block structure
and push the Annual Training Plan to intervals.icu. After that, `/week` each Sunday
generates the detailed week, one week at a time.

### `20 Daily/_template.md`
The skeleton every daily note is built from: frontmatter for the graded signals
(HRV, RHR, sleep, CTL/ATL/TSB, readiness colour, planned vs. prescribed) and the
Verdict / Signals / Today's session / Change log headings. `daily-readiness` reads
this file at write time, so keep it in the vault and keep the keys stable if you
edit it.
