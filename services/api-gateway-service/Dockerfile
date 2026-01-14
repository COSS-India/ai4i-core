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

# Copy AI4ICore libraries (from repo root)
COPY libs/ai4icore_logging /app/libs/ai4icore_logging
COPY libs/ai4icore_telemetry /app/libs/ai4icore_telemetry

# Copy requirements from service context
COPY services/api-gateway-service/requirements.txt .

RUN pip install --upgrade pip setuptools wheel

# Install Python dependencies
RUN pip install --no-cache-dir --user -r requirements.txt

# Install AI4ICore libraries (editable)
RUN pip install --no-cache-dir --user -e /app/libs/ai4icore_logging
RUN pip install --no-cache-dir --user -e /app/libs/ai4icore_telemetry


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

# Copy AI4ICore libraries into runtime image FIRST (before app code)
COPY --from=builder /app/libs /app/libs

# Copy application code from service context
COPY services/api-gateway-service /app

# Fix permissions (before switching user)
RUN chown -R app:app /app /home/app/.local \
    && chmod +x /home/app/.local/bin/* || true

ENV PATH=/home/app/.local/bin:$PATH
ENV PYTHONPATH="/app:/app/libs"
ENV PYTHONUNBUFFERED=1

# Switch to app user and install packages normally (non-editable) to avoid .pth file issues
USER app
RUN pip install --no-cache-dir --user /app/libs/ai4icore_logging
RUN pip install --no-cache-dir --user /app/libs/ai4icore_telemetry

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
  CMD curl -f http://localhost:8080/health || exit 1

ENTRYPOINT ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080", "--no-access-log"]
