# ================================
# Builder stage
# ================================
FROM python:3.11-slim AS builder
WORKDIR /app

RUN apt-get update && apt-get install -y gcc g++ curl && rm -rf /var/lib/apt/lists/*

# Copy libs from repo root (works only when context is repo root)
COPY libs/ai4icore_logging /app/libs/ai4icore_logging
COPY libs/ai4icore_telemetry /app/libs/ai4icore_telemetry

# Copy service requirements
COPY services/api-gateway-service/requirements.txt /app/requirements.txt

RUN pip install --upgrade pip setuptools wheel
RUN pip install --no-cache-dir --user -r /app/requirements.txt

RUN pip install --no-cache-dir --user -e /app/libs/ai4icore_logging
RUN pip install --no-cache-dir --user -e /app/libs/ai4icore_telemetry


# ================================
# Runtime stage
# ================================
FROM python:3.11-slim
WORKDIR /app

RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*
RUN useradd --create-home --shell /bin/bash app

COPY --from=builder /root/.local /home/app/.local
COPY --from=builder /app/libs /app/libs

# Copy ONLY service code into runtime
COPY services/api-gateway-service/ /app/

RUN chown -R app:app /app /home/app/.local && chmod +x /home/app/.local/bin/* || true

ENV PATH=/home/app/.local/bin:$PATH
ENV PYTHONPATH="/app:/app/libs"
ENV PYTHONUNBUFFERED=1

USER app
RUN pip install --no-cache-dir --user /app/libs/ai4icore_logging
RUN pip install --no-cache-dir --user /app/libs/ai4icore_telemetry

EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
  CMD curl -f http://localhost:8080/health || exit 1

ENTRYPOINT ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080", "--no-access-log"]
