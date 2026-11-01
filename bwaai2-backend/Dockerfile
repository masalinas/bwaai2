# Stage 1: Build virtual environment with dependencies
FROM python:3.12.9-slim-bookworm AS builder

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /build

# Copy uv for fast dependency resolution
COPY --from=ghcr.io/astral-sh/uv:0.5.21 /uv /bin/uv

# Copy dependency manifests
COPY pyproject.toml README.md /build/

# Create virtualenv and install dependencies
RUN uv venv /opt/venv && \
    uv pip install --no-cache -r pyproject.toml

# Stage 2: Runtime image
FROM python:3.12.9-slim-bookworm AS runner

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:$PATH" \
    API_WORKERS=2

WORKDIR /app

# Create dedicated non-root user
RUN groupadd -g 1000 appgroup && \
    useradd -u 1000 -g appgroup -s /bin/sh -m appuser

# Copy virtualenv from builder stage
COPY --from=builder /opt/venv /opt/venv

# Copy application source code
COPY app/ /app/app/

# Set ownership
RUN chown -R appuser:appgroup /app

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=5s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers ${API_WORKERS:-2}"]
