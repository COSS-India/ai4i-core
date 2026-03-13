FROM python:3.11-slim AS builder

WORKDIR /app

# Build dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    curl \
    libpq-dev \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy shared libraries and service requirements
COPY libs/ai4icore_constants /app/libs/ai4icore_constants
COPY libs/ai4icore_env /app/libs/ai4icore_env
COPY libs/ai4icore_auth /app/libs/ai4icore_auth
COPY services/tenant-audit-service/requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Install shared libraries in editable mode
RUN pip install --no-cache-dir -e /app/libs/ai4icore_constants
RUN pip install --no-cache-dir -e /app/libs/ai4icore_env
RUN pip install --no-cache-dir -e /app/libs/ai4icore_auth

# ---------------- Stage 2: Runtime ----------------
FROM python:3.11-slim

WORKDIR /app

# Runtime libraries
RUN apt-get update && apt-get install -y \
    curl \
    libpq5 \
    libssl3 \
    libnss3 \
    libstdc++6 \
    ca-certificates \
    iputils-ping \
    netcat-openbsd \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN useradd --create-home --shell /bin/bash app

# Copy installed Python packages and shared libraries from builder
COPY --from=builder /usr/local /usr/local
COPY --from=builder /app/libs/ai4icore_constants /app/libs/ai4icore_constants
COPY --from=builder /app/libs/ai4icore_env /app/libs/ai4icore_env
COPY --from=builder /app/libs/ai4icore_auth /app/libs/ai4icore_auth

# Copy application code
COPY services/tenant-audit-service .

# Permissions
RUN chown -R app:app /app
USER app

EXPOSE 9003

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
  CMD curl -f http://localhost:9003/health || exit 1

ENTRYPOINT ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "9003"]

