FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc libpq-dev && \
    rm -rf /var/lib/apt/lists/*

# Service deps from PyPI; monorepo ai4icore_core overrides until a release includes RequestMiddleware.
COPY libs/ai4icore_core /libs/ai4icore_core
COPY services/auth-service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir -e /libs/ai4icore_core

# Copy application code
COPY services/auth-service/ .

# Create keys directory (mount production keys via volume)
RUN mkdir -p /app/keys

EXPOSE 8081

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8081", "--workers", "4"]
