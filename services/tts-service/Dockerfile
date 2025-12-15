FROM python:3.11-slim AS builder

WORKDIR /app

RUN apt-get update && apt-get install -y \
    gcc g++ curl libpq-dev libsndfile1-dev ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY libs/ai4icore_observability /app/libs/ai4icore_observability
COPY services/tts-service/requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir -e /app/libs/ai4icore_observability

# ----------------------------
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    curl libpq5 libsndfile1 ffmpeg \
    && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --shell /bin/bash app

COPY --from=builder /usr/local /usr/local
# Copy service source code and observability library into the final image as well
COPY services/tts-service .
COPY libs/ai4icore_observability /app/libs/ai4icore_observability

RUN chown -R app:app /app
USER app

ENV PYTHONPATH="/app/libs:${PYTHONPATH}"

EXPOSE 8088

HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
  CMD curl -f http://localhost:8088/health || exit 1

ENTRYPOINT ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8088"]
