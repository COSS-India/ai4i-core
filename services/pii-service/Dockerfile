FROM python:3.11-slim AS builder
WORKDIR /app
RUN apt-get update && apt-get install -y gcc g++ curl libpq-dev && rm -rf /var/lib/apt/lists/*
COPY libs/ai4icore_exceptions /app/libs/ai4icore_exceptions
COPY libs/ai4icore_constants /app/libs/ai4icore_constants
COPY libs/ai4icore_env /app/libs/ai4icore_env
COPY libs/ai4icore_logging /app/libs/ai4icore_logging
COPY libs/ai4icore_auth /app/libs/ai4icore_auth
COPY services/pii-service/requirements.txt .
RUN pip install --upgrade pip setuptools wheel
RUN pip install --no-cache-dir --user -r requirements.txt
RUN pip install --no-cache-dir --user -e /app/libs/ai4icore_exceptions
RUN pip install --no-cache-dir --user -e /app/libs/ai4icore_constants
RUN pip install --no-cache-dir --user -e /app/libs/ai4icore_env
RUN pip install --no-cache-dir --user -e /app/libs/ai4icore_logging
RUN pip install --no-cache-dir --user -e /app/libs/ai4icore_auth
RUN pip install --no-cache-dir --user --force-reinstall packaging

FROM python:3.11-slim
WORKDIR /app
RUN apt-get update && apt-get install -y curl libpq5 ca-certificates && rm -rf /var/lib/apt/lists/*
RUN useradd --create-home --shell /bin/bash app
COPY --from=builder /root/.local /home/app/.local
ENV PATH="/home/app/.local/bin:$PATH"
ENV PYTHONPATH="/app"
ENV PYTHONUNBUFFERED=1
COPY --from=builder /app/libs/ai4icore_exceptions /app/libs/ai4icore_exceptions
COPY --from=builder /app/libs/ai4icore_constants /app/libs/ai4icore_constants
COPY --from=builder /app/libs/ai4icore_env /app/libs/ai4icore_env
COPY --from=builder /app/libs/ai4icore_logging /app/libs/ai4icore_logging
COPY --from=builder /app/libs/ai4icore_auth /app/libs/ai4icore_auth
COPY services/pii-service .
RUN chown -R app:app /app /home/app/.local && chmod +x /home/app/.local/bin/* || true
USER app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 CMD curl -f http://localhost:8000/health || exit 1
ENTRYPOINT ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
