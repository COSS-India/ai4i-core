FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc libpq-dev && \
    rm -rf /var/lib/apt/lists/*

# Service deps from PyPI (ai4i-core pulled from PyPI via requirements.txt)
COPY services/auth-service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY services/auth-service/ .

# Create keys directory (mount production keys via volume)
RUN mkdir -p /app/keys

# Run as non-root user for security
RUN useradd --no-create-home --shell /bin/false appuser \
    && chown -R appuser:appuser /app

USER appuser

EXPOSE 8081

ENTRYPOINT ["python", "main.py"]
