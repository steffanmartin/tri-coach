# tri-coach

An always-on triathlon coach: Claude Agent SDK + intervals.icu + a git-backed
Obsidian vault, reachable over Telegram, with a 06:30 readiness job.

---

## What runs where

| Piece | Where | Why there |
|---|---|---|
| Telegram bot (long polling) | one small container | needs to be always-on; long polling means no public endpoint, no TLS, no webhook |
| 06:30 daily brief | same container, APScheduler | already always-on, so a separate scheduler is wasted infra |
| Coaching skills | `.claude/skills/`, mounted into the container | plain markdown, version-controlled, editable from Obsidian |
| Memory | the Obsidian vault, via git | the vault *is* the memory; no database |
| Training data | intervals.icu, via MCP | single source of truth for anything numeric |
| Deep planning sessions | Claude.ai in a browser | long back-and-forth is miserable on a phone keyboard |

Host: any small always-on box. A €4/mo Hetzner CX22 or an Azure Container App
with `minReplicas: 1` both work. Do not use scale-to-zero — long polling dies.

---

## Setup

### 1. intervals.icu
Settings → Developer Settings → generate an API key. Note your athlete ID
(`i123456`, visible in the URL). Confirm your watch is pushing **wellness**, not
just activities: the daily brief needs `hrv`, `restingHR`, `sleepSecs`. Check
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
ssh-keygen -t ed25519 -f ~/.ssh/vault_deploy   # add pubkey as a repo deploy key (write access)
docker compose up -d --build
docker compose logs -f
```

Verify: send `/status` in Telegram. Then `python -m coach.daily_brief` inside the
container to test the morning job without waiting for 06:30.

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
- `/status` — CTL / ATL / TSB / weeks to race
- anything else — free-form chat with the coach

---

## Notes
- **Model split**: `COACH_MODEL` (Sonnet) for daily jobs, `PLANNER_MODEL` (Opus)
  for `plan-architect`. Daily briefs run 365 times a year; planning runs six.
- **Detailed weeks are generated one week at a time**, never 52 weeks up front.
  A plan written in September for the following June is fiction.
- **The Agent SDK moves quickly.** If `ClaudeAgentOptions` rejects a field, check
  https://code.claude.com/docs/en/agent-sdk/python before debugging further.
- **WhatsApp** was skipped deliberately: the Business API needs Meta business
  verification, restricts what you can send outside a 24-hour window, and costs
  per conversation. Telegram is free and takes two minutes.
