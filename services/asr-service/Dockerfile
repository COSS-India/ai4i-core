# -----------------------------
# STAGE 1 — BUILDER
# -----------------------------
FROM python:3.11-slim AS builder
WORKDIR /app

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        gcc g++ curl libpq-dev ffmpeg libsndfile1-dev \
        build-essential git libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# ---- shared plugins (repo-root paths) ----
COPY libs/ai4icore_observability /app/libs/ai4icore_observability
COPY libs/ai4icore_logging /app/libs/ai4icore_logging
COPY libs/ai4icore_telemetry /app/libs/ai4icore_telemetry
COPY libs/ai4icore_model_management /app/libs/ai4icore_model_management

# ---- requirements ----
COPY services/asr-service/requirements.txt .

RUN pip install --upgrade pip setuptools wheel
RUN pip install --no-cache-dir --user -r requirements.txt

# Install AI4ICore plugins (editable) so logging, telemetry and observability are available
RUN pip install --no-cache-dir --user -e /app/libs/ai4icore_observability
RUN pip install --no-cache-dir --user -e /app/libs/ai4icore_logging
RUN pip install --no-cache-dir --user -e /app/libs/ai4icore_telemetry
RUN pip install --no-cache-dir --user -e /app/libs/ai4icore_model_management

# -----------------------------
# STAGE 2 — RUNTIME
# -----------------------------
FROM python:3.11-slim
WORKDIR /app

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        curl libpq5 libssl3 libnss3 libstdc++6 \
        ca-certificates ffmpeg libsndfile1 libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /root/.local /root/.local
ENV PATH=/root/.local/bin:$PATH

# Copy AI4ICore plugins into runtime image
COPY --from=builder /app/libs/ai4icore_observability /app/libs/ai4icore_observability
COPY --from=builder /app/libs/ai4icore_logging /app/libs/ai4icore_logging
COPY --from=builder /app/libs/ai4icore_telemetry /app/libs/ai4icore_telemetry
COPY --from=builder /app/libs/ai4icore_model_management /app/libs/ai4icore_model_management

# ---- application code ----
COPY services/asr-service /app

RUN rm -f /app/.env || true

ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH="/app"

EXPOSE 8087
ENTRYPOINT ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8087", "--no-access-log"]
