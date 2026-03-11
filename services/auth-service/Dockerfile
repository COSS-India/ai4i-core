# Multi-stage Dockerfile for Auth Service
FROM python:3.11-slim AS builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    curl \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy AI4I Core libraries
COPY libs/ai4icore_telemetry /app/libs/ai4icore_telemetry
COPY libs/ai4icore_logging /app/libs/ai4icore_logging
# Multi-tenant library used by auth-service for tenant resolution
COPY libs/ai4icore_multi_tenant /app/libs/ai4icore_multi_tenant
# Shared constants
COPY libs/ai4icore_constants /app/libs/ai4icore_constants
COPY libs/ai4icore_env /app/libs/ai4icore_env

# Copy requirements from build context
COPY services/auth-service/requirements.txt .

# Install Python dependencies (NO --user)
RUN pip install --no-cache-dir -r requirements.txt

# Install AI4I Core libraries in editable mode
RUN pip install --no-cache-dir -e /app/libs/ai4icore_telemetry
RUN pip install --no-cache-dir -e /app/libs/ai4icore_logging
RUN pip install --no-cache-dir -e /app/libs/ai4icore_multi_tenant
RUN pip install --no-cache-dir -e /app/libs/ai4icore_constants
RUN pip install --no-cache-dir -e /app/libs/ai4icore_env

# ---------------- Final stage ----------------
FROM python:3.11-slim

WORKDIR /app

# Install runtime dependencies
RUN apt-get update && apt-get install -y \
    curl \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN useradd --create-home --shell /bin/bash app

# Copy installed Python packages
COPY --from=builder /usr/local /usr/local

# Copy AI4I Core libraries from builder
COPY --from=builder /app/libs/ai4icore_telemetry /app/libs/ai4icore_telemetry
COPY --from=builder /app/libs/ai4icore_logging /app/libs/ai4icore_logging
COPY --from=builder /app/libs/ai4icore_multi_tenant /app/libs/ai4icore_multi_tenant
COPY --from=builder /app/libs/ai4icore_env /app/libs/ai4icore_env

# Copy shared constants lib
COPY libs/ai4icore_constants /app/libs/ai4icore_constants

# Install ai4icore_constants in editable mode
RUN pip install --no-cache-dir -e /app/libs/ai4icore_constants

# Create __init__.py file to make services a Python package
RUN touch /app/services/__init__.py

# Copy application code from service context
COPY services/auth-service .

# Fix ownership ONLY for app files
RUN chown -R app:app /app
USER app

EXPOSE 8081

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
  CMD curl -f http://localhost:8081/health || exit 1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8081"]
