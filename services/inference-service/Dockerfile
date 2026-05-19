# Stage 1: Builder
FROM python:3.11-slim AS builder

WORKDIR /app

RUN apt-get update && apt-get install -y \
    gcc g++ curl build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY services/inference-service/requirements.txt .

RUN pip install --upgrade pip setuptools wheel
RUN pip install --no-cache-dir --user -r requirements.txt

# Stage 2: Runtime
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --shell /bin/bash app

COPY --from=builder /root/.local /home/app/.local
ENV PATH=/home/app/.local/bin:$PATH
ENV PYTHONPATH="/app:/home/app/.local/lib/python3.11/site-packages"
ENV PYTHONUNBUFFERED=1

# App code (repo-root build context path)
COPY services/inference-service .

RUN chown -R app:app /app /home/app/.local \
    && chmod +x /home/app/.local/bin/*

USER app

EXPOSE 8090

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
  CMD curl -f http://localhost:8090/health || exit 1

ENTRYPOINT ["python", "main.py"]
