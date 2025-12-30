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

# Copy requirements from build context
COPY requirements.txt .

# Install Python dependencies (NO --user)
RUN pip install --no-cache-dir -r requirements.txt

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

# Copy application code
COPY . .

# Fix ownership ONLY for app files
RUN chown -R app:app /app
USER app

EXPOSE 8081

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
  CMD curl -f http://localhost:8081/health || exit 1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8081"]
