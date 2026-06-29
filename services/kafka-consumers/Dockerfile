FROM python:3.11-slim

ARG file_name
ENV PYTHONUNBUFFERED=1
ENV FILE_NAME=${file_name}

WORKDIR /app

# Install system build dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc libpq-dev curl && \
    rm -rf /var/lib/apt/lists/*

# ── Install service dependencies (ai4i-core pulled from PyPI via requirements.txt) ──
COPY consumers/consumers/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── Copy shared module files ──
COPY consumers/consumers/services/__init__.py .
COPY consumers/consumers/services/config.py .

# ── Copy the specific consumer file ──
COPY consumers/consumers/services/${file_name}.py .

# Run as non-root user for security
RUN useradd --no-create-home --shell /bin/false appuser \
    && chown -R appuser:appuser /app

USER appuser

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD cat /proc/1/cmdline | tr '\0' ' ' | grep -q "${FILE_NAME}.py" || exit 1

ENTRYPOINT exec python ${FILE_NAME}.py
