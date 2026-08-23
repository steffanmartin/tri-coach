#!/usr/bin/env bash
# Installs the pieces the base image and features do not cover.
set -euo pipefail

# uv manages the Python environment, and `uvx` also launches the intervals.icu MCP.
curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.local/bin:$PATH"

# Claude Code CLI — the Agent SDK shells out to it, so it must be on PATH.
npm i -g @anthropic-ai/claude-code

# Same lockfile the image builds from, so the devcontainer and the deployed
# container resolve to identical versions.
uv sync --frozen

# The vault clone/push runs non-interactively; an unknown host key would be a
# hard failure rather than a prompt.
mkdir -p ~/.ssh && chmod 700 ~/.ssh
ssh-keyscan github.com >> ~/.ssh/known_hosts 2>/dev/null
sort -u -o ~/.ssh/known_hosts ~/.ssh/known_hosts

# Local runs need every var in .env.example exported.
[ -f .env ] || cp .env.example .env

echo "Ready. Next: fill in .env, then 'uv run python -m coach.telegram_bot'."
