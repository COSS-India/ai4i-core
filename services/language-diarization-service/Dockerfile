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
COPY libs/ai4icore_exceptions /app/libs/ai4icore_exceptions
COPY libs/ai4icore_auth /app/libs/ai4icore_auth

# Copy service requirements
COPY services/language-diarization-service/requirements.txt .

RUN pip install --upgrade pip setuptools wheel

# Set pip timeout via environment variable (default is 15 seconds, increase to 300)
ENV PIP_DEFAULT_TIMEOUT=300

# Install Python deps
RUN pip install --no-cache-dir --user -r requirements.txt

# Force install packaging in user directory (needed by OpenTelemetry instrumentation)
RUN pip install --no-cache-dir --user --force-reinstall packaging>=23.0

# Install AI4ICore plugins
RUN pip install --no-cache-dir --user /app/libs/ai4icore_observability
RUN pip install --no-cache-dir --user -e /app/libs/ai4icore_multi_tenant
RUN pip install --no-cache-dir --user /app/libs/ai4icore_logging
RUN pip install --no-cache-dir --user /app/libs/ai4icore_telemetry
RUN pip install --no-cache-dir --user /app/libs/ai4icore_model_management
RUN pip install --no-cache-dir --user -e /app/libs/ai4icore_constants
RUN pip install --no-cache-dir --user -e /app/libs/ai4icore_env
RUN pip install --no-cache-dir --user -e /app/libs/ai4icore_exceptions
RUN pip install --no-cache-dir --user -e /app/libs/ai4icore_auth


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
# ENV PYTHONPATH="/app:/app/libs"
# Ensure Python can see:
# - service code at /app
# - multi-tenant plugin source at /app/libs/ai4icore_multi_tenant
# - user site-packages at /home/app/.local/lib/python3.11/site-packages
ENV PYTHONPATH="/app:/app/libs/ai4icore_multi_tenant:/home/app/.local/lib/python3.11/site-packages"
ENV PYTHONUNBUFFERED=1

# Copy AI4ICore plugins into runtime image
COPY --from=builder /app/libs/ai4icore_observability /app/libs/ai4icore_observability
COPY --from=builder /app/libs/ai4icore_multi_tenant /app/libs/ai4icore_multi_tenant
COPY --from=builder /app/libs/ai4icore_logging /app/libs/ai4icore_logging
COPY --from=builder /app/libs/ai4icore_telemetry /app/libs/ai4icore_telemetry
COPY --from=builder /app/libs/ai4icore_model_management /app/libs/ai4icore_model_management
COPY --from=builder /app/libs/ai4icore_env /app/libs/ai4icore_env
COPY --from=builder /app/libs/ai4icore_exceptions /app/libs/ai4icore_exceptions
COPY --from=builder /app/libs/ai4icore_auth /app/libs/ai4icore_auth

# Copy application code and shared constants
COPY services/language-diarization-service .
COPY --from=builder /app/libs/ai4icore_constants /app/libs/ai4icore_constants

# Adjust ownership and permissions
RUN chown -R app:app /app /home/app/.local \
    && chmod +x /home/app/.local/bin/*

RUN chown -R app:app /app
USER app

EXPOSE 8090

HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
  CMD curl -f http://localhost:8090/health || exit 1

ENTRYPOINT ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8090"]
