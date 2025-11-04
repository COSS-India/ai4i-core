# Multi-stage Dockerfile for NMT Service
# Stage 1: Builder
FROM python:3.11-slim as builder

# Set working directory
WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    curl \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements file
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir --user -r requirements.txt

# Stage 2: Final
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install runtime dependencies
RUN apt-get update && apt-get install -y \
    curl \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user first
RUN useradd --create-home --shell /bin/bash app

# Copy Python packages from builder stage to app user's home
COPY --from=builder /root/.local /home/app/.local

# Update PATH
ENV PATH=/home/app/.local/bin:$PATH

# Copy application code
COPY . .

# Change ownership to app user and make uvicorn executable
RUN chown -R app:app /app /home/app/.local && \
    chmod +x /home/app/.local/bin/*
USER app

# Expose port
EXPOSE 8089

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8089/api/v1/nmt/health || exit 1

# Entrypoint
ENTRYPOINT ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8089"]
