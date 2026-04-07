FROM python:3.11-slim AS builder

WORKDIR /app

RUN apt-get update && apt-get install -y gcc g++ curl && rm -rf /var/lib/apt/lists/*

# Copy shared libs if present in monorepo (kept consistent with other services)
COPY libs/ai4icore_logging /app/libs/ai4icore_logging
COPY libs/ai4icore_env /app/libs/ai4icore_env

# Service requirements
COPY services/policy-service/requirements.txt /app/requirements.txt

RUN pip install --upgrade pip setuptools wheel
RUN pip install --no-cache-dir --user -r /app/requirements.txt
RUN pip install --no-cache-dir --user -e /app/libs/ai4icore_logging || true
RUN pip install --no-cache-dir --user -e /app/libs/ai4icore_env || true


FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*
RUN useradd --create-home --shell /bin/bash app

COPY --from=builder /root/.local /home/app/.local
COPY --from=builder /app/libs /app/libs

# Copy service code
COPY services/policy-service/ /app/

RUN chown -R app:app /app /home/app/.local && chmod +x /home/app/.local/bin/* || true

ENV PATH=/home/app/.local/bin:$PATH
ENV PYTHONPATH="/app:/app/libs"
ENV PYTHONUNBUFFERED=1

USER app
RUN pip install --no-cache-dir --user /app/libs/ai4icore_logging || true
RUN pip install --no-cache-dir --user /app/libs/ai4icore_env || true

EXPOSE 8099

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
  CMD curl -f http://localhost:8099/health || exit 1

ENTRYPOINT ["uvicorn", "app.main:get_app", "--host", "0.0.0.0", "--port", "8099", "--no-access-log"]

