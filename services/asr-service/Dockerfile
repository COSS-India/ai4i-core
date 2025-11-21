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
    && rm -rf /var/lib/apt/lists/*

# Copy everything
COPY . /app

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
    && rm -rf /var/lib/apt/lists/*

# Copy Python libraries
COPY --from=builder /usr/local /usr/local

# Copy application code
COPY --from=builder /app /app

# ❗ IMPORTANT FIX: REMOVE .env so ConfigMap overrides work
RUN rm -f /app/.env || true

ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH="/app"

EXPOSE 8087

ENTRYPOINT ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8087"]
