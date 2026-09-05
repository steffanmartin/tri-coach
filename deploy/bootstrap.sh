#!/usr/bin/env bash
# One-time bootstrap for the One.com VPS that replaced Azure Container Apps.
# Idempotent: safe to re-run after a provider rebuild, which is the only way to
# change the OS and wipes the disk when you do.
#
# Run it as a sudoer:  scp deploy/bootstrap.sh <host>: && ssh <host> 'sudo bash bootstrap.sh'
#
# It deliberately does NOT touch sshd_config. Locking password auth off is the
# one step that can strand you, so it is a separate, deliberate act once you
# have proven key login works for every account you intend to keep.
set -euo pipefail

DEPLOY_USER=deploy
APP_DIR=/opt/tri-coach

echo "== swap =="
# 4 GB of RAM is exactly what the container app had, and the Claude Code CLI
# (node) plus the MCP server can spike on a long agent turn. Insurance, not
# capacity: the image is built in CI and only ever pulled here.
if ! swapon --show | grep -q /swapfile; then
  fallocate -l 4G /swapfile
  chmod 600 /swapfile
  mkswap /swapfile
  swapon /swapfile
  grep -q '^/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi
echo 'vm.swappiness=10' > /etc/sysctl.d/99-tricoach-swap.conf
sysctl -q --system

echo "== timezone =="
# Matches TZ in the app's env. APScheduler is given TZ explicitly, so this is
# for the operator reading logs, not for correctness.
timedatectl set-timezone Europe/Copenhagen

echo "== unattended upgrades =="
apt-get update -qq
DEBIAN_FRONTEND=noninteractive apt-get install -y -qq unattended-upgrades ufw fail2ban curl ca-certificates
# 04:00 sits between the 21:00 debrief and the 06:00 brief. APScheduler holds
# both jobs in-process with a 1s misfire grace, so a reboot landing on either
# would silently skip that day's run.
cat > /etc/apt/apt.conf.d/52-tricoach <<'EOF'
Unattended-Upgrade::Automatic-Reboot "true";
Unattended-Upgrade::Automatic-Reboot-Time "04:00";
EOF

echo "== firewall =="
# Note this governs the host only. Docker writes its own iptables chain ahead of
# ufw's, so a container published on 0.0.0.0 is reachable even when ufw denies.
# The compose file publishes 127.0.0.1:8080 for exactly that reason — Caddy is
# the only thing that ever fronts the receiver. Never change that binding.
ufw --force default deny incoming
ufw --force default allow outgoing
ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable
systemctl enable --now fail2ban

echo "== docker =="
if ! command -v docker >/dev/null; then
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
  chmod a+r /etc/apt/keyrings/docker.asc
  . /etc/os-release
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu ${VERSION_CODENAME} stable" \
    > /etc/apt/sources.list.d/docker.list
  apt-get update -qq
  DEBIAN_FRONTEND=noninteractive apt-get install -y -qq \
    docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
fi
systemctl enable --now docker

echo "== deploy user =="
# Separate from the human admin account so the CI key is not a general-purpose
# login. It owns $APP_DIR and is in the docker group (which is root-equivalent —
# acceptable, since it is a sudoer anyway and the box runs one thing).
id -u "$DEPLOY_USER" >/dev/null 2>&1 || adduser --disabled-password --gecos "" "$DEPLOY_USER"
usermod -aG docker,sudo "$DEPLOY_USER"
install -d -m 700 -o "$DEPLOY_USER" -g "$DEPLOY_USER" "/home/$DEPLOY_USER/.ssh"

echo "== app dir =="
install -d -m 750 -o "$DEPLOY_USER" -g "$DEPLOY_USER" "$APP_DIR"
install -d -m 700 -o "$DEPLOY_USER" -g "$DEPLOY_USER" "$APP_DIR/secrets"

echo "== caddy =="
# On the host, not in a container: it needs 80/443, and publishing those from
# Docker is the one case where the DOCKER chain jumps ufw. As a host service it
# binds via CAP_NET_BIND_SERVICE and reaches the bot over loopback.
if ! command -v caddy >/dev/null; then
  DEBIAN_FRONTEND=noninteractive apt-get install -y -qq debian-keyring debian-archive-keyring apt-transport-https
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' \
    | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
    > /etc/apt/sources.list.d/caddy-stable.list
  apt-get update -qq
  DEBIAN_FRONTEND=noninteractive apt-get install -y -qq caddy
fi
# Caddy's unit runs as the `caddy` user, which cannot create this itself; the
# Caddyfile's `log` directive fails the whole config load without it.
install -d -m 755 -o caddy -g caddy /var/log/caddy
systemctl enable caddy

echo
echo "bootstrap complete."
docker --version; docker compose version; caddy version
