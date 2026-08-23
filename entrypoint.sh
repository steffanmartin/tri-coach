#!/bin/sh
# Prepares /vault, then hands off to the bot. Written to be a no-op wherever
# docker-compose already did the job with bind mounts, so both paths use one image.
set -e

VAULT="${VAULT_PATH:-/vault}"
SSH_KEY_FILE="${VAULT_SSH_KEY_FILE:-/mnt/secrets/id_ed25519}"

# Container Apps hands secrets over as a read-only volume, and ssh refuses to use
# a key that is group- or world-readable. Copy it somewhere we can lock down.
if [ -f "$SSH_KEY_FILE" ] && [ ! -f /root/.ssh/id_ed25519 ]; then
  mkdir -p /root/.ssh && chmod 700 /root/.ssh
  cp "$SSH_KEY_FILE" /root/.ssh/id_ed25519
  chmod 600 /root/.ssh/id_ed25519
fi

# git refuses to clone into a non-empty directory, and /vault is never reliably
# empty: compose mounts .claude into it, Azure may hand us a populated volume.
# So clone aside and copy in.
if [ ! -d "$VAULT/.git" ]; then
  echo "vault: cloning $VAULT_REPO"
  rm -rf /tmp/vault-clone
  git clone "$VAULT_REPO" /tmp/vault-clone
  mkdir -p "$VAULT"
  cp -a /tmp/vault-clone/. "$VAULT"/
  rm -rf /tmp/vault-clone
fi

# agent.options() sets cwd=VAULT_PATH with setting_sources=["project"], so the
# skills must sit at $VAULT_PATH/.claude or none of them load. Compose bind-mounts
# them; with no bind mount we put the image's copy in place.
if [ ! -e "$VAULT/.claude" ]; then
  cp -r /app/.claude "$VAULT/.claude"
fi

exec "$@"
