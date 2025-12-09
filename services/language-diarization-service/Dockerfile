# Multi-stage Dockerfile for Language Diarization Service

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

# Copy AI4ICore Observability Plugin
COPY libs/ai4icore_observability /app/libs/ai4icore_observability

# Copy requirements and install Python dependencies
COPY services/language-diarization-service/requirements.txt .
# Set pip timeout via environment variable (default is 15 seconds, increase to 300)
ENV PIP_DEFAULT_TIMEOUT=300
RUN pip install --no-cache-dir --user -r requirements.txt
RUN pip install --no-cache-dir --user -e /app/libs/ai4icore_observability


# Final runtime image
FROM python:3.11-slim

WORKDIR /app

# Install runtime dependencies
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

# Copy AI4ICore Observability Plugin
COPY --from=builder /app/libs/ai4icore_observability /app/libs/ai4icore_observability

# Copy application code
COPY services/language-diarization-service .

# Adjust ownership and permissions
RUN chown -R app:app /app /home/app/.local \
    && chmod +x /home/app/.local/bin/*

USER app

# Expose port
EXPOSE 8094

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8094/health || exit 1

# Run the application
ENTRYPOINT ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8094"]

