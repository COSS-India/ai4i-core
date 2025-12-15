FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    curl \
    && rm -rf /var/lib/apt/lists/*

# ✅ FIX: copy requirements from correct monorepo path
COPY services/pipeline-service/requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

# ✅ FIX: copy application code from correct path
COPY services/pipeline-service/ .

EXPOSE 8090

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
  CMD curl -f http://localhost:8090/health || exit 1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8090"]
