# -----------------------------
# STAGE 1 — BUILDER
# -----------------------------
FROM python:3.11-slim AS builder

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    curl \
    libpq-dev \
    libsndfile1-dev \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first (better Docker cache)
COPY services/tts-service/requirements.txt .

# Upgrade pip tooling
RUN pip install --upgrade pip setuptools wheel

# Install Python deps to user site-packages
RUN pip install --no-cache-dir --user -r requirements.txt

# Copy observability plugin source
COPY libs/ai4icore_observability /app/libs/ai4icore_observability

# IMPORTANT:
# Install plugin as editable (expects source to exist at runtime)
RUN pip install --no-cache-dir --user -e /app/libs/ai4icore_observability


# -----------------------------
# STAGE 2 — RUNTIME
# -----------------------------
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    libpq5 \
    libsndfile1 \
    ffmpeg \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN useradd --create-home --shell /bin/bash app

# Copy Python dependencies installed in builder
COPY --from=builder /root/.local /home/app/.local

# 🔑 COPY observability plugin SOURCE (FIXES ModuleNotFoundError)
COPY --from=builder /app/libs/ai4icore_observability /app/libs/ai4icore_observability

# Environment
ENV PATH="/home/app/.local/bin:$PATH"
ENV PYTHONPATH="/app:/app/libs"
ENV PYTHONUNBUFFERED=1

# Copy application code
COPY services/tts-service /app

RUN chown -R app:app /app
USER app

EXPOSE 8088

HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
  CMD curl -f http://localhost:8088/health || exit 1

ENTRYPOINT ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8088"]
