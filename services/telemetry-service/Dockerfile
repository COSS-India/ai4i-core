# Multi-stage Dockerfile for Telemetry Service
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

# Copy AI4ICore libraries from monorepo
COPY libs/ai4icore_telemetry /app/libs/ai4icore_telemetry

# Copy requirements and install Python dependencies
COPY services/telemetry-service/requirements.txt .
RUN pip install --upgrade pip setuptools wheel
RUN pip install --no-cache-dir --user -r requirements.txt

# Install AI4ICore telemetry library (editable)
RUN pip install --no-cache-dir --user -e /app/libs/ai4icore_telemetry

# Verify packaging is installed (for debugging)
RUN python -c "import packaging; print(f'packaging version: {packaging.__version__}')" || (echo "ERROR: packaging not found!" && exit 1)

# Final stage
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install runtime dependencies
RUN apt-get update && apt-get install -y \
    curl \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user FIRST
RUN useradd --create-home --shell /bin/bash app

# Copy Python packages from builder stage
COPY --from=builder /root/.local /home/app/.local

# Copy application code FIRST
COPY services/telemetry-service /app

# Create libs directory and copy library AFTER app code (to ensure it's not overwritten)
RUN mkdir -p /app/libs
COPY --from=builder /app/libs/ai4icore_telemetry /app/libs/ai4icore_telemetry

# Verify library was copied
RUN test -d /app/libs/ai4icore_telemetry && test -f /app/libs/ai4icore_telemetry/ai4icore_telemetry/__init__.py || (echo "ERROR: Library directory or __init__.py not found!" && ls -la /app/libs/ 2>&1 && exit 1)

# Change ownership to app user
RUN chown -R app:app /app /home/app/.local

# Switch to app user
USER app

# Set environment variables
ENV PATH=/home/app/.local/bin:$PATH
ENV PYTHONPATH=/app:/app/libs
ENV PYTHONUNBUFFERED=1

# Install the library as app user (non-editable, copies files to site-packages)
# This ensures the library files are actually in site-packages, not just linked
RUN pip install --no-cache-dir --user /app/libs/ai4icore_telemetry || \
    (echo "ERROR: Failed to install ai4icore_telemetry!" && exit 1)

# Verify installation and that files exist
RUN python -c "import ai4icore_telemetry; print('✓ ai4icore_telemetry imported successfully')" && \
    python -c "import ai4icore_telemetry.opensearch_client; print('✓ opensearch_client found')" && \
    python -c "import ai4icore_telemetry.jaeger_client; print('✓ jaeger_client found')" || \
    (echo "ERROR: ai4icore_telemetry not importable!" && exit 1)

# Expose port
EXPOSE 8084

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8084/health || exit 1

# Run the application
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8084"]
