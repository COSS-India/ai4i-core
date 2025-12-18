# Multi-stage Dockerfile for TTS Service
FROM python:3.11-slim as builder

# Set working directory
WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    curl \
    libpq-dev \
    libsndfile1-dev \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Copy AI4ICore Observability Plugin
COPY libs/ai4icore_observability /app/libs/ai4icore_observability

# Copy AI4ICore Model Management Plugin
COPY libs/ai4icore_model_management /app/libs/ai4icore_model_management

# Copy requirements and install Python dependencies
COPY services/tts-service/requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt
RUN pip install --no-cache-dir --user -e /app/libs/ai4icore_observability
RUN pip install --no-cache-dir --user -e /app/libs/ai4icore_model_management

# Final stage
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install runtime dependencies
RUN apt-get update && apt-get install -y \
    curl \
    libpq5 \
    libsndfile1 \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user first
RUN useradd --create-home --shell /bin/bash app

# Copy Python packages from builder stage to app user's home
COPY --from=builder /root/.local /home/app/.local

# Make sure scripts in .local are usable
ENV PATH=/home/app/.local/bin:$PATH

# Copy AI4ICore Observability Plugin
COPY --from=builder /app/libs/ai4icore_observability /app/libs/ai4icore_observability

# Copy AI4ICore Model Management Plugin
COPY --from=builder /app/libs/ai4icore_model_management /app/libs/ai4icore_model_management

# Copy application code
COPY services/tts-service .

# Change ownership to app user and make uvicorn executable
RUN chown -R app:app /app /home/app/.local && \
    chmod +x /home/app/.local/bin/*
USER app

# Expose port
EXPOSE 8088

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8088/health || exit 1

# Run the application
ENTRYPOINT ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8088"]