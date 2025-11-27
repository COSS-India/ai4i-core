# -----------------------------
# STAGE 1 — BUILDER
# -----------------------------
FROM python:3.10-slim AS builder
WORKDIR /app

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        ffmpeg \
        libsndfile1 \
        build-essential \
        git \
        libgomp1 \
        curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements from service directory (build context is project root)
COPY services/asr-service/requirements.txt .

# Install Python dependencies
RUN pip install --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -r requirements.txt


# -----------------------------
# STAGE 2 — RUNTIME
# -----------------------------
FROM python:3.10-slim AS runtime
WORKDIR /app

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        ffmpeg \
        libsndfile1 \
        libgomp1 \
        curl \
        netcat-openbsd \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN useradd --create-home --shell /bin/bash app

# Copy Python libraries from builder
COPY --from=builder /usr/local /usr/local

# ⭐ Copy common observability module (SAME AS NMT SERVICE)
COPY --chown=app:app common/observability /app/observability

# Copy application code (relative to project root)
COPY --chown=app:app services/asr-service/. .

# ❗ IMPORTANT FIX: REMOVE .env so ConfigMap overrides work
RUN rm -f /app/.env || true

# Change ownership
RUN chown -R app:app /app

ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH="/app"

USER app

EXPOSE 8087

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8087/health || exit 1

ENTRYPOINT ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8087"]
