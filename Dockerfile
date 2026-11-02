# Multi-stage production Dockerfile for MediCode API and Worker
# Stage 1: Build dependencies
FROM python:3.11-slim AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv for fast, reliable package compilation
COPY --from=ghcr.io/astral-sh/uv:0.5.21 /uv /uvx /bin/

COPY pyproject.toml .
# Install only non-dev dependencies into a standalone virtualenv
RUN uv venv /opt/venv && \
    . /opt/venv/bin/activate && \
    uv pip install --no-cache .

# Stage 2: Minimal runtime image
FROM python:3.11-slim AS runner

WORKDIR /app

# Install minimal runtime dependencies (libpq for postgresql)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create dedicated non-root system user
RUN groupadd -g 10001 medicode && \
    useradd -u 10001 -g medicode -s /bin/bash -m medicode

# Copy virtualenv from builder
COPY --from=builder --chown=medicode:medicode /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH="/app/src"

# Copy application source code and migrations
COPY --chown=medicode:medicode src /app/src
COPY --chown=medicode:medicode alembic /app/alembic
COPY --chown=medicode:medicode alembic.ini /app/alembic.ini

USER medicode

EXPOSE 8000

# Container healthcheck using FastAPI /health liveness probe
HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Default command: launch uvicorn API server
CMD ["uvicorn", "medicode.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
