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

# Copy shared constants lib
COPY libs/ai4icore_constants /app/libs/ai4icore_constants
# Copy AI4ICore plugins from monorepo
COPY libs/ai4icore_observability /app/libs/ai4icore_observability
COPY libs/ai4icore_multi_tenant /app/libs/ai4icore_multi_tenant
COPY libs/ai4icore_logging /app/libs/ai4icore_logging
COPY libs/ai4icore_telemetry /app/libs/ai4icore_telemetry
COPY libs/ai4icore_model_management /app/libs/ai4icore_model_management
COPY libs/ai4icore_env /app/libs/ai4icore_env
COPY libs/ai4icore_auth /app/libs/ai4icore_auth

# Copy service requirements
COPY services/ocr-service/requirements.txt .

RUN pip install --upgrade pip setuptools wheel

# Install Python deps
RUN pip install --no-cache-dir --user -r requirements.txt
RUN pip install --no-cache-dir --user -e /app/libs/ai4icore_observability
RUN pip install --no-cache-dir --user -e /app/libs/ai4icore_multi_tenant
RUN pip install --no-cache-dir --user -e /app/libs/ai4icore_logging
RUN pip install --no-cache-dir --user -e /app/libs/ai4icore_telemetry
RUN pip install --no-cache-dir --user -e /app/libs/ai4icore_model_management
RUN pip install --no-cache-dir --user -e /app/libs/ai4icore_constants
RUN pip install --no-cache-dir --user -e /app/libs/ai4icore_env
RUN pip install --no-cache-dir --user -e /app/libs/ai4icore_auth

# Verify packaging is installed (for debugging)
RUN python -c "import packaging; print(f'packaging version: {packaging.__version__}')" || (echo "ERROR: packaging not found!" && exit 1)

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

ENV PATH="/home/app/.local/bin:$PATH"
ENV PYTHONPATH="/app"
ENV PYTHONUNBUFFERED=1

# Ensure packaging is available in runtime - install system-wide AND user-wide
# This ensures it's available regardless of Python path resolution
RUN pip install --no-cache-dir packaging>=21.0 && \
    pip install --no-cache-dir --target=/home/app/.local/lib/python3.11/site-packages packaging>=21.0 && \
    python -c "import sys; sys.path.insert(0, '/home/app/.local/lib/python3.11/site-packages'); import packaging; print(f'✓ packaging {packaging.__version__} verified')" || \
    (echo "ERROR: packaging not available!" && exit 1)

# Copy AI4ICore plugins
COPY --from=builder /app/libs/ai4icore_observability /app/libs/ai4icore_observability
COPY --from=builder /app/libs/ai4icore_multi_tenant /app/libs/ai4icore_multi_tenant
COPY --from=builder /app/libs/ai4icore_logging /app/libs/ai4icore_logging
COPY --from=builder /app/libs/ai4icore_telemetry /app/libs/ai4icore_telemetry
COPY --from=builder /app/libs/ai4icore_model_management /app/libs/ai4icore_model_management
COPY --from=builder /app/libs/ai4icore_env /app/libs/ai4icore_env
COPY --from=builder /app/libs/ai4icore_auth /app/libs/ai4icore_auth

# Copy application code and shared constants
COPY services/ocr-service .
COPY --from=builder /app/libs/ai4icore_constants /app/libs/ai4icore_constants

# Adjust ownership and permissions
RUN chown -R app:app /app /home/app/.local \
    && chmod +x /home/app/.local/bin/* || true

USER app

EXPOSE 8099

HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
  CMD curl -f http://localhost:8099/health || exit 1

# Run the application
# Disable uvicorn access logs since we use RequestLoggingMiddleware with trace_id
ENTRYPOINT ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8099", "--no-access-log"]
