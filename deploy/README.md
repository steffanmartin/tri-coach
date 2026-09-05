# Deploying tri-coach to the one.com VPS

Replaces the Azure Container Apps deployment that used to live in `infra/`.
Everything the managed platform supplied — ingress with TLS, secrets from Key
Vault, log ingestion — is now three explicit things on one box: Caddy, a
root-owned `.env`, and a rotated json-file log.

- **Host** `vps-6077.onecom-cloud.one` (`85.190.105.41`), Ubuntu 26.04 LTS,
  2 vCPU / 4 GB / 100 GB. Exactly the `cpu: 2.0 / memory: 4.0Gi` the container
  app had.
- **Image** `ghcr.io/steffanmartin/tri-coach`, built by
  `.github/workflows/deploy.yml`. The VPS pulls; it never builds.
- **Accounts** `administrator` (human) and `deploy` (owns `/opt/tri-coach`, and
  the account CI logs in as). Key-only auth, both in `AllowUsers`.

## 1. Bootstrap the box

`deploy/bootstrap.sh` is idempotent and does the whole thing: swap, timezone,
unattended-upgrades with a 04:00 reboot window, ufw + fail2ban, Docker CE, the
`deploy` user, `/opt/tri-coach`, and Caddy.

```bash
scp deploy/bootstrap.sh administrator@vps-6077.onecom-cloud.one:/tmp/
ssh administrator@vps-6077.onecom-cloud.one 'sudo bash /tmp/bootstrap.sh'
```

It deliberately leaves `sshd_config` alone. Once you have proven key login for
every account you intend to keep, apply `deploy/sshd-hardening.conf` to
`/etc/ssh/sshd_config.d/10-hardening.conf`, `sudo sshd -t`, restart, and *verify
in a second terminal before closing the first*. Turning password auth off is the
one step that can strand you.

The 04:00 reboot window is not arbitrary: APScheduler holds both cron jobs
in-process with a one-second misfire grace, so a reboot landing on 06:00 or 21:00
silently skips that day's run.

## 2. Secrets and config

```
/opt/tri-coach/                 deploy:deploy 0750
├── docker-compose.yml          0644   shipped by CI — never hand-edit it here
├── deploy.env                  0644   IMAGE_TAG=<sha>, and nothing else
├── .env                        0600   every runtime var, including the secrets
└── secrets/id_ed25519          0600   the triathlon-brain deploy key
```

Two env files on purpose. `--env-file deploy.env` points compose's `${...}`
*interpolation* at a file holding only the image tag, while `env_file: .env` is
what reaches the container. One file doing both jobs is how the tag ends up
injected as a container variable and how a secret ends up in `docker compose
config` output.

`.env` is `.env.example` filled in — it is the single config surface now, which
is a real gain over Key Vault plus `infra/app.bicep`'s `env:` block, two lists
that drifted silently. **A change to it needs a container restart.**

The deploy key is mounted as a read-only *directory* at `/mnt/secrets`, the
default of `VAULT_SSH_KEY_FILE`, so `entrypoint.sh` runs its copy-and-chmod-600
path exactly as it did under Container Apps — ssh refuses a group- or
world-readable key. Mounting the directory rather than the file also means
rotating the key needs no compose change.

## 3. TLS

`deploy/Caddyfile` → `/etc/caddy/Caddyfile`. Caddy runs on the *host*, not in a
container: it needs 80/443, and publishing those from Docker is the one case
where Docker's iptables chain jumps ahead of ufw.

```bash
sudo install -m 644 deploy/Caddyfile /etc/caddy/Caddyfile
sudo caddy validate --config /etc/caddy/Caddyfile
sudo systemctl reload caddy
```

Certificates live in `/var/lib/caddy/.local/share/caddy/`, renew automatically,
and need 80 or 443 reachable at renewal time. Nothing to back up — a lost store
just re-issues.

Verify from **off** the box, not from the VPS:

```bash
curl -fsS https://vps-6077.onecom-cloud.one/health   # ok  (502 if the container is down)
curl -o /dev/null -w '%{http_code}\n' https://vps-6077.onecom-cloud.one/   # 404, from Caddy
```

## 4. Deploys

Push to `main`. CI builds, pushes `ghcr.io/steffanmartin/tri-coach:<sha7>` and
`:latest`, then SSHes in, writes `deploy.env`, pulls, restarts, and waits for the
container to report healthy — rolling back to the previous tag if it never does.
The `DEPLOY_TO_VPS` repository variable gates the second half.

Manual deploy or rollback:

```bash
ssh deploy@vps-6077.onecom-cloud.one
cd /opt/tri-coach
echo IMAGE_TAG=<sha> > deploy.env
docker compose --env-file deploy.env pull && docker compose --env-file deploy.env up -d
docker compose --env-file deploy.env logs -f
```

Rollback is a local image and a one-line edit, which is the whole reason
`deploy.env` pins a sha rather than tracking `:latest`.

**Required in GitHub** — secrets `VPS_HOST`, `VPS_USER`, `VPS_SSH_KEY`,
`VPS_KNOWN_HOSTS`; variable `DEPLOY_TO_VPS`. The GHCR package must be **public**,
which has to be set once by hand after the first push (packages default to
private even for a public repo) or the VPS's credential-less pull fails with
`denied`. The image carries no secrets: the Dockerfile's only `COPY`s are
`pyproject.toml`/`uv.lock`, `coach/`, `.claude/` and `entrypoint.sh`, and the
repo is public anyway.

## 5. Register the webhook

At https://intervals.icu/settings/apps set **Webhook URL** to
`https://vps-6077.onecom-cloud.one/intervals/webhook`, tick **ACTIVITY_UPLOADED**
and nothing else, and delete any previous URL — a stale one means intervals.icu
retries a dead host forever. If you set **Webhook Authorization Header**, mirror
it byte for byte in `INTERVALS_WEBHOOK_AUTH_HEADER`.

## Verify

- `docker compose --env-file deploy.env ps` → `Up (healthy)`.
- Logs show `vault: cloning` once, then polling, no traceback.
- `docker compose exec coach ls /vault/.claude/skills` lists **daily-brief**.
  If it lists `daily-readiness`, the skills refresh is broken — see the note in
  CLAUDE.md about the vault repo tracking `.claude/`.
- `/status` in Telegram returns CTL/ATL/TSB — the SDK path and the intervals.icu
  MCP both work.
- `/today` returns a readiness call — the skills loaded from `/vault/.claude`.
- A commit authored by `tri-coach` appears in the vault repo — the deploy key and
  the push path.
- `curl -fsS https://vps-6077.onecom-cloud.one/health` returns `ok` from off-box.
  A 404 there means the container is up but the receiver never started, which
  almost always means `INTERVALS_WEBHOOK_SECRET` is empty; it fails closed and
  logs `INTERVALS_WEBHOOK_SECRET unset — not listening for webhooks`.
- After the next ride or run: a `30 Sessions/` commit and a Telegram message
  within minutes.

## Things that will bite

- **Never publish the container port on `0.0.0.0`.** Docker writes its own
  iptables chain ahead of ufw's, so `8080:8080` would put the webhook receiver on
  the public internet with no TLS and no firewall in front. It is
  `127.0.0.1:8080:8080` and Caddy is the only thing that fronts it.
- **Never run two instances.** Telegram permits one `getUpdates` poller per
  token; a second makes both fail with 409. Worse, two would race on one git
  working tree and write the same session note twice.
- **`/vault` persists now.** That is a change from Azure, where a cold start
  re-cloned and therefore healed anything wedged for free. `entrypoint.sh` aborts
  an interrupted rebase explicitly; for anything else,
  `docker volume rm tri-coach_vault` is the reset (it is safe — git is the source
  of truth, and unpushed work is the only thing lost).
- **Never commit `.claude/` to the vault repo.** The image is the only source of
  the skills and `entrypoint.sh` rewrites them on every start; a tracked copy in
  the vault would be restored by the next `git add -A` and then win forever.
- **A `.env` change needs a restart**, exactly as a Key Vault change needed a new
  revision.
- **The Let's Encrypt certificate is on a provider-owned hostname.**
  `onecom-cloud.one` is not on the Public Suffix List, so the per-registered-domain
  rate limit is shared with every other one.com VPS customer using their assigned
  name, and a rebuild could reassign the hostname and take the registered webhook
  URL with it. Both are fixed by pointing a domain you own at `85.190.105.41`,
  swapping the site address in the Caddyfile, and re-registering the URL.
- **Snapshots are not backups.** one.com keeps one snapshot for 24 h. The vault
  is git-backed offsite, which covers the data; `/opt/tri-coach/.env` and the
  deploy key are the only things on this box that exist nowhere else — keep them
  in a password manager.
