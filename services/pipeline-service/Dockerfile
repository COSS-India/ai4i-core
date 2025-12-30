FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy AI4ICore plugins
COPY libs/ai4icore_observability /app/libs/ai4icore_observability
COPY libs/ai4icore_model_management /app/libs/ai4icore_model_management

# Copy requirements from build context
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir /app/libs/ai4icore_observability
RUN pip install --no-cache-dir /app/libs/ai4icore_model_management

# Copy application code
COPY . .

EXPOSE 8090

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
  CMD curl -f http://localhost:8090/health || exit 1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8090"]
