# Multi-stage Dockerfile for Config Service
FROM python:3.11-slim AS builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    curl \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy shared libs
COPY libs/ai4icore_constants /app/libs/ai4icore_constants
COPY libs/ai4icore_env /app/libs/ai4icore_env
COPY libs/ai4icore_exceptions /app/libs/ai4icore_exceptions
COPY libs/ai4icore_auth /app/libs/ai4icore_auth

# ✅ FIX: copy requirements using full path from repo root
COPY services/config-service/requirements.txt .

# Install Python dependencies (NO --user)
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir -e /app/libs/ai4icore_constants
RUN pip install --no-cache-dir -e /app/libs/ai4icore_env
RUN pip install --no-cache-dir -e /app/libs/ai4icore_exceptions
RUN pip install --no-cache-dir -e /app/libs/ai4icore_auth

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
# Copy Python packages from builder
# COPY --from=builder /root/.local /home/app/.local

# ENV PATH=/home/app/.local/bin:$PATH

# Copy shared libs from builder
COPY --from=builder /app/libs/ai4icore_constants /app/libs/ai4icore_constants
COPY --from=builder /app/libs/ai4icore_env /app/libs/ai4icore_env
COPY --from=builder /app/libs/ai4icore_exceptions /app/libs/ai4icore_exceptions
COPY --from=builder /app/libs/ai4icore_auth /app/libs/ai4icore_auth

# Copy application code
COPY services/config-service/ .

# Fix ownership ONLY for app files
RUN chown -R app:app /app
USER app

EXPOSE 8082

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
  CMD curl -f http://localhost:8082/health || exit 1

ENTRYPOINT ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8082"]
