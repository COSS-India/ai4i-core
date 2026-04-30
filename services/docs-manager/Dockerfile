# Docs Manager - serves merged OpenAPI spec and Swagger UI
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY services/docs-manager/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY services/docs-manager/ .

EXPOSE 8103

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
  CMD curl -f http://localhost:8103/health || exit 1

ENTRYPOINT ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8103"]
