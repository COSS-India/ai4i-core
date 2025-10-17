# Multi-stage Dockerfile for API Gateway Service
FROM python:3.11-slim as builder

# Set working directory
WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Final stage
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install runtime dependencies
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user first
RUN useradd --create-home --shell /bin/bash app

# Copy Python packages from builder stage to app user's home
COPY --from=builder /root/.local /home/app/.local

# Copy application code
COPY . .

# Change ownership to app user
RUN chown -R app:app /app /home/app/.local

# Make sure scripts in .local are usable and executable
RUN chmod +x /home/app/.local/bin/*
ENV PATH=/home/app/.local/bin:$PATH

USER app

# Expose port
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

# Run the application
ENTRYPOINT ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
