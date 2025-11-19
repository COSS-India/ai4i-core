# STAGE 1 – Builder
FROM python:3.10-slim AS builder
WORKDIR /app

# Install OS deps
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        ffmpeg \
        libsndfile1 \
        build-essential \
        git \
        libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Copy ONLY this service code
COPY services/asr-service /app

# Install deps
RUN pip install --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -r requirements.txt

# STAGE 2 – Runtime
FROM python:3.10-slim AS runtime
WORKDIR /app

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        ffmpeg \
        libsndfile1 \
        libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /usr/local /usr/local
COPY --from=builder /app /app

ENV PYTHONPATH="/app"
ENV PYTHONUNBUFFERED=1

EXPOSE 8087
ENTRYPOINT ["python", "main.py"]
