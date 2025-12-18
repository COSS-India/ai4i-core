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

# Copy shared libraries
COPY libs/ai4icore_observability /app/libs/ai4icore_observability
COPY libs/ai4icore_auth /app/libs/ai4icore_auth
COPY libs/ai4icore_logging /app/libs/ai4icore_logging
COPY libs/ai4icore_telemetry /app/libs/ai4icore_telemetry

# Copy service requirements
COPY services/ner-service/requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir --user -r requirements.txt
RUN pip install --no-cache-dir --user -e /app/libs/ai4icore_observability
RUN pip install --no-cache-dir --user -e /app/libs/ai4icore_auth
RUN pip install --no-cache-dir --user -e /app/libs/ai4icore_logging
RUN pip install --no-cache-dir --user -e /app/libs/ai4icore_telemetry


FROM python:3.11-slim

WORKDIR /app

# Runtime dependencies (similar to NMT/OCR)
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

# Create libs directory and copy shared libraries
RUN mkdir -p /app/libs
COPY --from=builder /app/libs/ai4icore_observability /app/libs/ai4icore_observability
COPY --from=builder /app/libs/ai4icore_auth /app/libs/ai4icore_auth
COPY --from=builder /app/libs/ai4icore_logging /app/libs/ai4icore_logging
COPY --from=builder /app/libs/ai4icore_telemetry /app/libs/ai4icore_telemetry

# Copy service code
COPY services/ner-service .

# Adjust ownership and permissions
RUN chown -R app:app /app /home/app/.local \
    && chmod +x /home/app/.local/bin/* || true

USER app

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

EXPOSE 9001

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:9001/health || exit 1

ENTRYPOINT ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "9001"]

