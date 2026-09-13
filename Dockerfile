# ---- Builder stage: compile deps that need build-essential ----
FROM python:3.11-slim AS builder

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN pip install --no-cache-dir -r requirements.txt

# ---- Runtime stage: no build tools, non-root user ----
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 1000 appuser

COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY . .
RUN mkdir -p data cache && chown -R appuser:appuser /app

USER appuser

# Railway proxy - documents the conventional port; actual bind port
# comes from $PORT at runtime (see CMD below).
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -f "http://localhost:${PORT:-8000}/api/v1/health" || exit 1

# Railway (and most PaaS) inject $PORT at runtime and route to whatever
# port the process actually binds - hardcoding --port here breaks on
# any host that doesn't happen to assign 8000. Default 8000 covers
# `docker run` without -e PORT=...
CMD ["sh", "-c", "uvicorn app.api.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
