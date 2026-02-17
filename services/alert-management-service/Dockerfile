# Build with context from repo root: docker compose build alert-management-service
FROM python:3.11-slim AS builder
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends gcc curl && rm -rf /var/lib/apt/lists/*

# Copy logging and telemetry libs (logging -> OpenSearch via Fluent Bit; telemetry -> Jaeger tracing)
COPY libs/ai4icore_logging /app/libs/ai4icore_logging
COPY libs/ai4icore_telemetry /app/libs/ai4icore_telemetry
COPY services/alert-management-service/requirements.txt /app/requirements.txt

RUN pip install --no-cache-dir -r /app/requirements.txt
RUN pip install --no-cache-dir -e /app/libs/ai4icore_logging
RUN pip install --no-cache-dir -e /app/libs/ai4icore_telemetry

# Runtime stage
FROM python:3.11-slim
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

COPY --from=builder /usr/local /usr/local
COPY --from=builder /app/libs/ai4icore_logging /app/libs/ai4icore_logging
COPY --from=builder /app/libs/ai4icore_telemetry /app/libs/ai4icore_telemetry

COPY services/alert-management-service/ /app/

# Parent of the ai4icore_* packages (package dir is libs/<name>/<name>/)
ENV PYTHONPATH="/app:/app/libs/ai4icore_logging:/app/libs/ai4icore_telemetry"
ENV PYTHONUNBUFFERED=1

EXPOSE 8098
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
  CMD curl -f http://localhost:8098/health || exit 1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8098"]
