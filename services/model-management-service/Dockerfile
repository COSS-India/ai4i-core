# ---------------- Stage 1: Builder ----------------
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

# ✅ FIX: copy requirements relative to build context
COPY requirements.txt .

# Install dependencies (NO --user)
RUN pip install --no-cache-dir -r requirements.txt

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

# Copy installed Python packages
COPY --from=builder /usr/local /usr/local

# Copy application code relative to build context
COPY . .

# Fix permissions
RUN chown -R app:app /app
USER app

EXPOSE 8091

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
  CMD curl -f http://localhost:8091/health || exit 1

ENTRYPOINT ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8091"]
