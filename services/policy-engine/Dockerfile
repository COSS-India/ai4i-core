FROM python:3.11-slim

WORKDIR /app

# Copy shared libs
COPY libs/ai4icore_env /app/libs/ai4icore_env

# Install dependencies
COPY services/policy-engine/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir -e /app/libs/ai4icore_env

ENV PYTHONPATH="/app:/app/libs"

# Copy code
COPY services/policy-engine/ .

# Run as non-root user for security
RUN useradd -m appuser && chown -R appuser /app
USER appuser

# Expose port
EXPOSE 8095

# Start with production settings
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8095", "--workers", "1"]
