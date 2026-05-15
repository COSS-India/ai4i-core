FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc libpq-dev && \
    rm -rf /var/lib/apt/lists/*

# Install service dependencies. The consolidated `ai4icore-core` package
# (pulled from PyPI via requirements.txt) bundles the shared subpackages
# previously installed individually (exceptions, constants, env, logging,
# bootstrap, email, ...).
COPY services/auth-service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY services/auth-service/ .

# Create keys directory (mount production keys via volume)
RUN mkdir -p /app/keys

EXPOSE 8081

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8081", "--workers", "4"]
