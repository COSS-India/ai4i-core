FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install system build dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc libpq-dev curl && \
    rm -rf /var/lib/apt/lists/*

# ── Install local shared library (not on PyPI) ──
COPY libs/ai4icore_core /libs/ai4icore_core
RUN pip install --no-cache-dir -e /libs/ai4icore_core

# ── Install service dependencies ──
COPY services/platform-core-service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── Copy application code ──
COPY services/platform-core-service/ .

EXPOSE 8095

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8095/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8095", "--workers", "4"]
