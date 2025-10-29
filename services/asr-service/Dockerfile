# Multi-stage Dockerfile for ASR Service
# Stage 1: Builder
FROM python:3.11-slim as builder

WORKDIR /app

# System build deps
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    curl \
    libpq-dev \
    libsndfile1-dev \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps to user site
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Stage 2: Final
FROM python:3.11-slim

WORKDIR /app

# Runtime deps
RUN apt-get update && apt-get install -y \
    curl \
    libpq5 \
    libsndfile1 \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Python runtime safety
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH=/home/app/.local/bin:$PATH

# Non-root user
RUN useradd --create-home --shell /bin/bash app

# Python packages from builder
COPY --from=builder /root/.local /home/app/.local

# Copy application code (no .env will be copied with proper .dockerignore)
COPY . .

# Permissions
RUN chown -R app:app /app /home/app/.local && \
    chmod +x /home/app/.local/bin/*

USER app

EXPOSE 8087

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8087/health || exit 1

ENTRYPOINT ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8087"]
