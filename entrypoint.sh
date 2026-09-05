#!/bin/sh
# Prepares /vault, then hands off to the bot. Written to be a no-op wherever
# docker-compose already did the job with bind mounts, so both paths use one image.
set -e

VAULT="${VAULT_PATH:-/vault}"
SSH_KEY_FILE="${VAULT_SSH_KEY_FILE:-/mnt/secrets/id_ed25519}"

# True when $1 is itself a mount point — i.e. compose bind-mounted something
# there and we must leave it alone, because those mounts are read-only and
# writing would fail the whole entrypoint under `set -e`. This replaces the two
# "only if it does not exist yet" guards this script used to carry, which could
# not tell a dev bind mount apart from stale state we are supposed to overwrite.
is_mount() {
  grep -qs " $1 " /proc/self/mountinfo
}

# A read-only secret mount is world-readable and ssh refuses a key that is group-
# or world-readable, so copy it somewhere we can lock down. Done on *every* start:
# the old "if not already there" guard meant a rotated key was silently ignored
# for as long as the container's writable layer survived.
if [ -f "$SSH_KEY_FILE" ] && ! is_mount /root/.ssh/id_ed25519; then
  mkdir -p /root/.ssh && chmod 700 /root/.ssh
  cp "$SSH_KEY_FILE" /root/.ssh/id_ed25519
  chmod 600 /root/.ssh/id_ed25519
fi

# git refuses to clone into a non-empty directory, and /vault is never reliably
# empty: compose mounts .claude into it, and a named volume may already be
# populated. So clone aside and copy in.
if [ ! -d "$VAULT/.git" ]; then
  echo "vault: cloning $VAULT_REPO"
  rm -rf /tmp/vault-clone
  git clone "$VAULT_REPO" /tmp/vault-clone
  mkdir -p "$VAULT"
  cp -a /tmp/vault-clone/. "$VAULT"/
  rm -rf /tmp/vault-clone
fi

# A container killed mid-turn (deploy, OOM, reboot) can leave a rebase half
# applied, and vault.pull() runs git with check=False and ignores the exit
# status — so every later turn would rebase onto a wedged tree and quietly lose
# its note. On Azure /vault was ephemeral and the next cold start re-cloned,
# healing this for free; with a persistent volume nothing does.
if [ -d "$VAULT/.git/rebase-merge" ] || [ -d "$VAULT/.git/rebase-apply" ]; then
  echo "vault: aborting an interrupted rebase"
  git -C "$VAULT" rebase --abort || true
fi

# agent.options() sets cwd=VAULT_PATH with setting_sources=["project"], so the
# skills must sit at $VAULT_PATH/.claude or none of them load. The image is their
# only source of truth, so refresh from it on EVERY start.
#
# The guard this replaces (`if [ ! -e "$VAULT/.claude" ]`) was a real bug. The
# first copy landed inside the vault working tree, where commit_and_push's
# `git add -A` committed and pushed it — so every clone since arrived carrying a
# frozen copy, the guard never fired again, and production went on running
# `daily-readiness` long after it was renamed to `daily-brief`. The vault repo
# now gitignores .claude/; this rewrites it from the image every time.
if is_mount "$VAULT/.claude"; then
  echo "skills: $VAULT/.claude is a bind mount, leaving it alone"
else
  rm -rf "$VAULT/.claude"
  cp -r /app/.claude "$VAULT/.claude"
fi

exec "$@"
