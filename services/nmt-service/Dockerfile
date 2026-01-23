# Stage 1: Builder
FROM python:3.11-slim AS builder

WORKDIR /app

RUN apt-get update && apt-get install -y \
    gcc g++ curl libpq-dev build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy AI4ICore plugins from monorepo
COPY libs/ai4icore_observability /app/libs/ai4icore_observability
# COPY libs/ai4icore_auth /app/libs/ai4icore_auth
COPY libs/ai4icore_logging /app/libs/ai4icore_logging
COPY libs/ai4icore_telemetry /app/libs/ai4icore_telemetry
COPY libs/ai4icore_model_management /app/libs/ai4icore_model_management
# Copy constants folder
COPY services/constants /app/services/constants

# Copy service requirements
COPY services/nmt-service/requirements.txt .

RUN pip install --upgrade pip setuptools wheel

# Install Python deps
# CRITICAL: Install packaging FIRST (system-wide) before any opentelemetry packages
# opentelemetry-instrumentation-fastapi imports packaging during installation
# Install both system-wide AND user-wide to ensure it's available
RUN pip install --no-cache-dir packaging>=21.0 && \
    pip install --no-cache-dir --user packaging>=21.0
 
# Install Python deps (packaging is already installed above)
RUN pip install --no-cache-dir --user -r requirements.txt
RUN pip install --no-cache-dir --user -e /app/libs/ai4icore_observability
# RUN pip install --no-cache-dir --user -e /app/libs/ai4icore_auth
RUN pip install --no-cache-dir --user -e /app/libs/ai4icore_logging
RUN pip install --no-cache-dir --user -e /app/libs/ai4icore_telemetry
RUN pip install --no-cache-dir --user -e /app/libs/ai4icore_model_management
# Verify packaging is installed (for debugging)
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

# Ensure packaging is available in runtime - install system-wide AND user-wide
# This ensures it's available regardless of Python path resolution
RUN pip install --no-cache-dir packaging>=21.0 && \
    pip install --no-cache-dir --target=/home/app/.local/lib/python3.11/site-packages packaging>=21.0 && \
    python -c "import sys; sys.path.insert(0, '/home/app/.local/lib/python3.11/site-packages'); import packaging; print(f'✓ packaging {packaging.__version__} verified')" || \
    (echo "ERROR: packaging not available!" && exit 1)


# Copy AI4ICore plugins
COPY --from=builder /app/libs/ai4icore_observability /app/libs/ai4icore_observability
# COPY --from=builder /app/libs/ai4icore_auth /app/libs/ai4icore_auth
COPY --from=builder /app/libs/ai4icore_logging /app/libs/ai4icore_logging
COPY --from=builder /app/libs/ai4icore_telemetry /app/libs/ai4icore_telemetry
COPY --from=builder /app/libs/ai4icore_model_management /app/libs/ai4icore_model_management
# Copy constants folder
COPY services/constants /app/services/constants

# App code (repo-root path)
COPY services/nmt-service .

RUN chown -R app:app /app /home/app/.local \
    && chmod +x /home/app/.local/bin/*

USER app

EXPOSE 8089

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
  CMD curl -f http://localhost:8089/health || exit 1

# Run the application
# Disable uvicorn access logs since we use RequestLoggingMiddleware with trace_id
ENTRYPOINT ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8089", "--no-access-log"]
