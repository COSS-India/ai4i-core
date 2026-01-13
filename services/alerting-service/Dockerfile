# Multi-stage Dockerfile for Alerting Service
FROM python:3.11-slim AS builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    curl \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements from service directory
COPY services/alerting-service/requirements.txt .

RUN pip install --no-cache-dir --user -r requirements.txt

# ---------------- Final stage ----------------
FROM python:3.11-slim

WORKDIR /app

# Install runtime dependencies
RUN apt-get update && apt-get install -y \
    curl \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user early (best practice)
RUN useradd --create-home --shell /bin/bash app

# Copy Python packages from builder
COPY --from=builder /root/.local /home/app/.local

ENV PATH=/home/app/.local/bin:$PATH

# Copy application source
COPY services/alerting-service .

# Permissions
RUN chown -R app:app /app /home/app/.local
USER app

EXPOSE 8085

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
  CMD curl -f http://localhost:8085/health || exit 1

ENTRYPOINT ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8085"]
