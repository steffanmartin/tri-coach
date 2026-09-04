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

# The intervals.icu MCP, installed at build time rather than fetched by `uvx` on
# the first tool call: that kept a network round-trip (and its failure modes) on
# the critical path of the first agent turn in a fresh container.
#
# Pinned to a rev, not a branch, so a rebuild cannot silently pick up upstream
# commits. fastmcp is held below its own stated floor (fastmcp>=2.12.4): 3.x made
# Context.get_state async, but this package's middleware and every tool still
# call it unawaited, so every tool call dies with "'coroutine' object has no
# attribute ...". 2.x is what its code actually matches.
#
# The sed fixes two upstream date bugs. intervals.icu returns start_date_local as
# a full ISO timestamp ("2026-09-04T00:00:00"), but get_calendar_events and
# get_upcoming_workouts both parse it with strptime(..., "%Y-%m-%d"), so both die
# with "unconverted data remains: T00:00:00" the moment the calendar is non-empty.
# fromisoformat accepts either shape. The server reports this as a normal result
# with is_error unset, so it fails silently — hence the grep, which fails the
# build if upstream ever moves these lines and the sed stops matching. Delete
# this whole patch once eddmann/intervals-icu-mcp fixes it upstream.
RUN uv tool install --with "fastmcp<3" \
      "intervals-icu-mcp @ git+https://github.com/eddmann/intervals-icu-mcp@cb91d4a" \
    && f=/root/.local/share/uv/tools/intervals-icu-mcp/lib/python*/site-packages/intervals_icu_mcp/tools/events.py \
    && sed -i -E 's/datetime\.strptime\((date|workout\.start_date_local), "%Y-%m-%d"\)/datetime.fromisoformat(\1)/' $f \
    && ! grep -q 'strptime(date\|strptime(workout' $f

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
