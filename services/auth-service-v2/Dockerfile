FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc libpq-dev && \
    rm -rf /var/lib/apt/lists/*

# Install shared platform libraries (cacheable layer)
# Order matters: exceptions first (no deps), then constants (depends on exceptions)
COPY libs/ai4icore_exceptions /tmp/ai4icore_exceptions
COPY libs/ai4icore_constants /tmp/ai4icore_constants
COPY libs/ai4icore_env /tmp/ai4icore_env
COPY libs/ai4icore_logging /tmp/ai4icore_logging
COPY libs/ai4icore_auth /tmp/ai4icore_auth
COPY libs/ai4icore_bootstrap /tmp/ai4icore_bootstrap
COPY libs/ai4icore_multi_tenant /tmp/ai4icore_multi_tenant
RUN pip install --no-cache-dir \
    /tmp/ai4icore_exceptions \
    /tmp/ai4icore_constants \
    /tmp/ai4icore_env \
    /tmp/ai4icore_logging \
    /tmp/ai4icore_auth \
    /tmp/ai4icore_bootstrap \
    /tmp/ai4icore_multi_tenant && \
    rm -rf /tmp/ai4icore_*

# Install service dependencies
COPY services/auth-service-v2/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY services/auth-service-v2/ .

# Create keys directory (mount production keys via volume)
RUN mkdir -p /app/keys

EXPOSE 8081

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8081", "--workers", "1"]
