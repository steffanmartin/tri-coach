FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
      git openssh-client curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Claude Code CLI (the Agent SDK drives it) + uv (runs the intervals.icu MCP)
RUN curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y nodejs && npm i -g @anthropic-ai/claude-code \
    && rm -rf /var/lib/apt/lists/*
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:${PATH}"

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY coach/ ./coach/
COPY .claude/ ./.claude/

CMD ["python", "-m", "coach.telegram_bot"]
