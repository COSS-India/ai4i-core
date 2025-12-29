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
    && rm -rf /var/lib/apt/lists/*

# Copy AI4ICore Observability Plugin
COPY libs/ai4icore_observability /app/libs/ai4icore_observability

# Copy AI4ICore Model Management Plugin
COPY libs/ai4icore_model_management /app/libs/ai4icore_model_management

# Copy requirements and install Python dependencies
COPY services/speaker-diarization-service/requirements.txt .

RUN pip install --upgrade pip setuptools wheel

# Install Python deps
RUN pip install --no-cache-dir --user -r requirements.txt
RUN pip install --no-cache-dir --user -e /app/libs/ai4icore_observability
RUN pip install --no-cache-dir --user -e /app/libs/ai4icore_model_management


# -----------------------------
# STAGE 2 — RUNTIME
# -----------------------------
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    libpq5 \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --shell /bin/bash app

# Copy Python site-packages
COPY --from=builder /root/.local /home/app/.local

# Copy AI4ICore Observability Plugin
COPY --from=builder /app/libs/ai4icore_observability /app/libs/ai4icore_observability

# Copy AI4ICore Model Management Plugin
COPY --from=builder /app/libs/ai4icore_model_management /app/libs/ai4icore_model_management

# Copy app code
COPY services/speaker-diarization-service /app

RUN chown -R app:app /app
USER app

EXPOSE 8095

HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
  CMD curl -f http://localhost:8095/health || exit 1

ENTRYPOINT ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8095"]
