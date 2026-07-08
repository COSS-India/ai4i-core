FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install system build dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc libpq-dev curl && \
    rm -rf /var/lib/apt/lists/*

# ── Install service dependencies (ai4i-core pulled from PyPI via requirements.txt) ──
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Run as non-root user for security
RUN useradd --no-create-home --shell /bin/false appuser \
    && chown -R appuser:appuser /app

USER appuser

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD cat /proc/1/cmdline | tr '\0' ' ' | grep -q "main.py" || exit 1

ENTRYPOINT ["python", "main.py"]
