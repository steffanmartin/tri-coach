FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
      git openssh-client curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Claude Code CLI (the Agent SDK drives it) + uv (runs the intervals.icu MCP)
RUN curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y nodejs && npm i -g @anthropic-ai/claude-code \
    && rm -rf /var/lib/apt/lists/*
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
# .venv/bin ahead of uv's own dir: `python` must resolve to the synced env, since
# the entrypoint execs the bot directly rather than going through `uv run`.
ENV PATH="/app/.venv/bin:/root/.local/bin:${PATH}"

# Seed GitHub's host keys: the vault clone/push runs non-interactively, so an
# unknown host key is a hard failure rather than a prompt.
RUN mkdir -p /root/.ssh && chmod 700 /root/.ssh \
    && ssh-keyscan github.com >> /root/.ssh/known_hosts

WORKDIR /app
# Dependencies before source: the lockfile changes far less often than coach/,
# so this layer survives most rebuilds. --frozen fails loudly if pyproject.toml
# and uv.lock have drifted apart, rather than silently re-resolving.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev
COPY coach/ ./coach/
COPY .claude/ ./.claude/
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
CMD ["python", "-m", "coach.telegram_bot"]
