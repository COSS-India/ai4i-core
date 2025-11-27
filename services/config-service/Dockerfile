# Multi-stage Dockerfile for Config Service
FROM python:3.11-slim as builder
WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    curl \
    libpq-dev \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Final stage
FROM python:3.11-slim
WORKDIR /app

# 🔥 FIXED: Install complete runtime dependencies
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

# Copy Python packages from builder
COPY --from=builder /root/.local /home/app/.local
ENV PATH=/home/app/.local/bin:$PATH

# Copy application code
COPY . .

# 🔥 FIXED: Set ownership AND executable permissions
RUN chown -R app:app /app /home/app/.local \
    && chmod +x /home/app/.local/bin/*

USER app

EXPOSE 8082

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8082/health || exit 1

ENTRYPOINT ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8082"]
