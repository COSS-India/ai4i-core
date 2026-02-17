# Build with context from repo root: docker compose build alert-config-sync-service
FROM python:3.11-slim AS builder
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends gcc curl && rm -rf /var/lib/apt/lists/*

# Copy logging lib (required for JSON logs -> OpenSearch via Fluent Bit)
COPY libs/ai4icore_logging /app/libs/ai4icore_logging
COPY services/alert-config-sync-service/requirements.txt /app/requirements.txt

RUN pip install --no-cache-dir -r /app/requirements.txt
RUN pip install --no-cache-dir -e /app/libs/ai4icore_logging

# Runtime stage
FROM python:3.11-slim
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl wget && rm -rf /var/lib/apt/lists/*

COPY --from=builder /usr/local /usr/local
COPY --from=builder /app/libs/ai4icore_logging /app/libs/ai4icore_logging

COPY services/alert-config-sync-service/ /app/

RUN mkdir -p /etc/prometheus/rules /etc/alertmanager

ENV PYTHONPATH="/app:/app/libs"
ENV PYTHONUNBUFFERED=1

EXPOSE 8097
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
  CMD wget --spider -q http://localhost:8097/health || exit 1

CMD ["python", "main.py"]
