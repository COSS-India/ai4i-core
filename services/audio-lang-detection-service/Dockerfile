# -----------------------------
# STAGE 1 — BUILDER
# -----------------------------
FROM python:3.11-slim AS builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    curl \
    libpq-dev \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements from build context
COPY services/audio-lang-detection-service/requirements.txt .

ENV PIP_DEFAULT_TIMEOUT=300
RUN pip install --no-cache-dir --user -r requirements.txt

# Copy observability plugin (vendored inside service)
COPY libs/ai4icore_observability /app/libs/ai4icore_observability
RUN pip install --no-cache-dir --user -e /app/libs/ai4icore_observability


# -----------------------------
# STAGE 2 — RUNTIME
# -----------------------------
FROM python:3.11-slim

WORKDIR /app

# Runtime dependencies
RUN apt-get update && apt-get install -y \
    curl \
    libpq5 \
    libssl3 \
    libnss3 \
    libstdc++6 \
    ca-certificates \
    iputils-ping \
    netcat-openbsd \
    && rm -rf /var/lib/apt/lists/*

# Non-root user
RUN useradd --create-home --shell /bin/bash app

# Copy Python deps from builder
COPY --from=builder /root/.local /home/app/.local
ENV PATH=/home/app/.local/bin:$PATH

# Copy observability plugin
COPY --from=builder /app/libs/ai4icore_observability /app/libs/ai4icore_observability

# Copy application source
COPY services/audio-lang-detection-service .

RUN chown -R app:app /app /home/app/.local \
    && chmod +x /home/app/.local/bin/*

USER app

EXPOSE 8096

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
  CMD curl -f http://localhost:8096/health || exit 1

ENTRYPOINT ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8096"]
