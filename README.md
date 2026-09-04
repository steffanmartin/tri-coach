# tri-coach

An always-on triathlon coach: Claude Agent SDK + intervals.icu + a git-backed
Obsidian vault, reachable over Telegram. A morning readiness job fires as soon
as the night's wellness data lands; an evening debrief closes the day out once
the day's sessions have uploaded.

---

## What runs where

| Piece | Where | Why there |
|---|---|---|
| Telegram bot (long polling) | one small container | needs to be always-on; long polling means no public endpoint, no TLS, no webhook |
| Morning brief + evening debrief | same container, APScheduler | already always-on, so a separate scheduler is wasted infra |
| Coaching skills | `.claude/skills/`, mounted into the container | plain markdown, version-controlled, editable from Obsidian |
| Memory | the Obsidian vault, via git | the vault *is* the memory; no database |
| Training data | intervals.icu, via MCP | single source of truth for anything numeric |
| Deep planning sessions | Claude.ai in a browser | long back-and-forth is miserable on a phone keyboard |

Host: any always-on box or container with **4 GB RAM** (the Claude Code CLI is the
memory hog). Deployed on **Azure Container Apps**, Consumption, 2 vCPU / 4 GiB with
`minReplicas: 1` — see [`infra/`](infra/README.md). Do not use scale-to-zero, and do
not run more than one replica: long polling dies with the process, and two pollers on
one Telegram token both fail.

---

## Setup

### 1. intervals.icu
Settings → Developer Settings → generate an API key. Note your athlete ID
(`i123456`, visible in the URL). Confirm your watch is pushing **wellness**, not
just activities: the morning brief needs `hrv`, `restingHR`, `sleepSecs`. Check
Settings → Wellness that HRV and sleep rows are populating. If they are not,
fix that before anything else — the daily job has nothing to grade without them.

### 2. Vault repo
```bash
gh repo create triathlon-brain --private
git clone git@github.com:you/triathlon-brain.git
cp -r vault-template/* triathlon-brain/
cd triathlon-brain && git add -A && git commit -m "seed" && git push
```
Open the folder as an Obsidian vault. Install the **Obsidian Git** plugin:
auto-pull on start, auto-commit-and-push every 10 min.

Folder ownership — this is what keeps merge conflicts from ever happening:

| Folder | Written by |
|---|---|
| `00 Meta/` | you (the agent reads only) |
| `10 Plan/`, `20 Daily/`, `30 Sessions/` | the agent |
| `40 Journal/`, `50 Races/` | you |

### 3. Telegram
Message `@BotFather` → `/newbot` → save the token. Message `@userinfobot` to get
your numeric chat ID. The bot hard-rejects every other chat ID — without that
check, anyone who finds the bot gets your training data.

### 4. Deploy
```bash
cp .env.example .env      # fill it in
ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519   # add pubkey as a repo deploy key (write access)
docker compose up -d --build
docker compose logs -f
```

Verify: send `/status` in Telegram. Then, inside the container, test both
scheduled jobs without waiting for the clock:

```bash
docker compose exec coach python -m coach.daily_brief --no-wait
docker compose exec coach python -m coach.daily_debrief --no-wait
```

The debrief is the one that writes `20 Daily/` and `30 Sessions/`, so a
successful run should show a new commit on the vault repo.

### 5. Seed the plan
Set `race_date` in `10 Plan/ironman-macro-plan.md`, fill in the TBDs in
`00 Meta/athlete-profile.md`, then from Claude.ai (not Telegram — this is a long
conversation) run the `plan-architect` skill. It writes the block table and the
intervals.icu Annual Training Plan.

Then `/week` each Sunday for the detailed week.

---

## Commands
- `/today` — readiness check and today's session
- `/week` — plan or rebalance the coming week
- `/debrief` — analyse the most recent activity
- `/day` — close out today: what was trained, how it went, and the daily note
- `/status` — CTL / ATL / TSB / weeks to race
- anything else — free-form chat with the coach

---

## Notes
- **The brief waits for your watch, not the clock.** From 06:00 it polls Google
  Health every 10 minutes for the night's HRV, resting HR and sleep, pushes them
  into intervals.icu and briefs the moment all three are there. If they never
  publish it briefs at 09:00 anyway and says which numbers are missing, rather
  than grading a night it cannot see. All four times are env vars — see
  `.env.example`.
- **The debrief waits for your uploads.** From 21:00 it polls intervals.icu every
  10 minutes until every planned session for the day has an activity against it,
  then writes a note per session into `30 Sessions/` and the day's note into
  `20 Daily/`. At 23:00 it stops waiting and says what never uploaded — a session
  whose file has not arrived is not the same as one that did not happen.
- **The daily note is written in the evening, not the morning.** There is exactly
  one `20 Daily/YYYY-MM-DD.md` per day and the debrief owns it, so it describes
  the day that happened rather than the day that was predicted. The morning brief
  sends its verdict to Telegram and records any session change on the
  intervals.icu event description, which is what the evening reads back.
- **Model split**: `COACH_MODEL` (Sonnet) for daily jobs, `PLANNER_MODEL` (Opus)
  for `plan-architect`. Daily briefs run 365 times a year; planning runs six.
- **Detailed weeks are generated one week at a time**, never 52 weeks up front.
  A plan written in September for the following June is fiction.
- **The Agent SDK moves quickly.** If `ClaudeAgentOptions` rejects a field, check
  https://code.claude.com/docs/en/agent-sdk/python before debugging further.
- **WhatsApp** was skipped deliberately: the Business API needs Meta business
  verification, restricts what you can send outside a 24-hour window, and costs
  per conversation. Telegram is free and takes two minutes.
