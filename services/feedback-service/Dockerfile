# Stage 1: Builder
FROM python:3.11-slim AS builder

WORKDIR /app

RUN apt-get update && apt-get install -y \
    gcc g++ curl libpq-dev build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy AI4ICore shared libraries
COPY libs/ai4icore_observability /app/libs/ai4icore_observability
COPY libs/ai4icore_multi_tenant /app/libs/ai4icore_multi_tenant
COPY libs/ai4icore_env /app/libs/ai4icore_env
COPY libs/ai4icore_auth /app/libs/ai4icore_auth
COPY libs/ai4icore_service_base /app/libs/ai4icore_service_base
COPY libs/ai4icore_logging /app/libs/ai4icore_logging
COPY libs/ai4icore_telemetry /app/libs/ai4icore_telemetry
COPY libs/ai4icore_model_management /app/libs/ai4icore_model_management
COPY libs/ai4icore_constants /app/libs/ai4icore_constants
COPY libs/ai4icore_exceptions /app/libs/ai4icore_exceptions

COPY services/feedback-service/requirements.txt .

RUN pip install --upgrade pip setuptools wheel

# Install packaging first (required by opentelemetry during install)
RUN pip install --no-cache-dir packaging>=21.0 && \
    pip install --no-cache-dir --user packaging>=21.0

RUN pip install --no-cache-dir --user -r requirements.txt
RUN pip install --no-cache-dir --user -e /app/libs/ai4icore_observability
RUN pip install --no-cache-dir --user -e /app/libs/ai4icore_multi_tenant
RUN pip install --no-cache-dir --user -e /app/libs/ai4icore_env
RUN pip install --no-cache-dir --user -e /app/libs/ai4icore_exceptions
RUN pip install --no-cache-dir --user -e /app/libs/ai4icore_auth
RUN pip install --no-cache-dir --user /app/libs/ai4icore_service_base
RUN pip install --no-cache-dir --user -e /app/libs/ai4icore_logging
RUN pip install --no-cache-dir --user -e /app/libs/ai4icore_telemetry
RUN pip install --no-cache-dir --user -e /app/libs/ai4icore_model_management
RUN pip install --no-cache-dir --user -e /app/libs/ai4icore_constants

RUN python -c "import packaging; print(f'packaging version: {packaging.__version__}')" || (echo "ERROR: packaging not found!" && exit 1)

# Stage 2: Runtime
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    curl libpq5 libssl3 libnss3 libstdc++6 \
    ca-certificates iputils-ping netcat-openbsd \
    && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --shell /bin/bash app

COPY --from=builder /root/.local /home/app/.local
ENV PATH=/home/app/.local/bin:$PATH
ENV PYTHONPATH="/app:/app/libs/ai4icore_multi_tenant:/home/app/.local/lib/python3.11/site-packages"
ENV PYTHONUNBUFFERED=1

RUN pip install --no-cache-dir packaging>=21.0 && \
    pip install --no-cache-dir --target=/home/app/.local/lib/python3.11/site-packages packaging>=21.0 && \
    python -c "import sys; sys.path.insert(0, '/home/app/.local/lib/python3.11/site-packages'); import packaging; print(f'✓ packaging {packaging.__version__} verified')" || \
    (echo "ERROR: packaging not available!" && exit 1)

# Copy AI4ICore shared libraries
COPY --from=builder /app/libs/ai4icore_observability /app/libs/ai4icore_observability
COPY --from=builder /app/libs/ai4icore_multi_tenant /app/libs/ai4icore_multi_tenant
COPY --from=builder /app/libs/ai4icore_env /app/libs/ai4icore_env
COPY --from=builder /app/libs/ai4icore_auth /app/libs/ai4icore_auth
COPY --from=builder /app/libs/ai4icore_service_base /app/libs/ai4icore_service_base
COPY --from=builder /app/libs/ai4icore_logging /app/libs/ai4icore_logging
COPY --from=builder /app/libs/ai4icore_telemetry /app/libs/ai4icore_telemetry
COPY --from=builder /app/libs/ai4icore_model_management /app/libs/ai4icore_model_management
COPY --from=builder /app/libs/ai4icore_constants /app/libs/ai4icore_constants
COPY --from=builder /app/libs/ai4icore_exceptions /app/libs/ai4icore_exceptions

# App code
COPY services/feedback-service .

RUN chown -R app:app /app /home/app/.local \
    && chmod +x /home/app/.local/bin/*

USER app

EXPOSE 8100

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
  CMD curl -f http://localhost:8100/health || exit 1

ENTRYPOINT ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8100", "--no-access-log"]
