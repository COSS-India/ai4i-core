# ================================
# Builder stage
# ================================
FROM python:3.11-slim AS builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements from service context
COPY services/api-gateway-service/requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir --user -r requirements.txt


# ================================
# Runtime stage
# ================================
FROM python:3.11-slim

WORKDIR /app

# Install runtime dependencies
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN useradd --create-home --shell /bin/bash app

# Copy installed Python packages
COPY --from=builder /root/.local /home/app/.local

# Copy constants folder (COPY automatically creates parent directories)
COPY services/constants /app/services/constants

# Create __init__.py files to make services and constants Python packages
# (needed for: from services.constants.error_messages import ...)
RUN touch /app/services/__init__.py /app/services/constants/__init__.py

# Copy application code from service context
COPY services/api-gateway-service .

# Fix permissions
RUN chown -R app:app /app /home/app/.local \
    && chmod +x /home/app/.local/bin/*

ENV PATH=/home/app/.local/bin:$PATH

USER app

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
  CMD curl -f http://localhost:8080/health || exit 1

ENTRYPOINT ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
