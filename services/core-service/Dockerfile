FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install system build dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc libpq-dev curl && \
    rm -rf /var/lib/apt/lists/*

# ── Install shared platform libraries (cacheable layer) ──
# Dependency order: exceptions → constants → env → logging → bootstrap
COPY libs/ai4icore_exceptions /tmp/ai4icore_exceptions
COPY libs/ai4icore_constants  /tmp/ai4icore_constants
COPY libs/ai4icore_env        /tmp/ai4icore_env
COPY libs/ai4icore_logging    /tmp/ai4icore_logging
COPY libs/ai4icore_bootstrap  /tmp/ai4icore_bootstrap
RUN pip install --no-cache-dir \
    /tmp/ai4icore_exceptions \
    /tmp/ai4icore_constants \
    /tmp/ai4icore_env \
    /tmp/ai4icore_logging \
    /tmp/ai4icore_bootstrap && \
    rm -rf /tmp/ai4icore_*

# ── Install service dependencies ──
COPY services/core-service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── Copy application code ──
COPY services/core-service/ .

EXPOSE 8095

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8095/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8095", "--workers", "4"]
