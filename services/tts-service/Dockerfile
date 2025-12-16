# -----------------------------
# STAGE 1 — BUILDER
# -----------------------------
FROM python:3.11-slim AS builder

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ curl \
    libpq-dev \
    libsndfile1-dev \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Copy only what is needed for dependency install
COPY services/tts-service/requirements.txt .

# Upgrade pip tools
RUN pip install --upgrade pip setuptools wheel

# Install deps to user site-packages (smaller & cleaner)
RUN pip install --no-cache-dir --user -r requirements.txt

# Copy observability plugin
COPY libs/ai4icore_observability /app/libs/ai4icore_observability
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

# Copy ONLY python dependencies (not entire /usr/local)
COPY --from=builder /root/.local /home/app/.local

ENV PATH="/home/app/.local/bin:$PATH"
ENV PYTHONPATH="/app"

# Copy application code
COPY services/tts-service /app

RUN chown -R app:app /app
USER app

EXPOSE 8088

HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
  CMD curl -f http://localhost:8088/health || exit 1

ENTRYPOINT ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8088"]
