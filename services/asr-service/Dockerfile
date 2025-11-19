# Stage 1: builder
FROM python:3.10-slim AS builder
WORKDIR /app

# Install build-time deps (for librosa, soundfile, torch builds)
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        ffmpeg \
        libsndfile1 \
        build-essential \
        git \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .

# Install Python dependencies
RUN pip install --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -r requirements.txt

# Copy full source code
COPY . .

# (Optional) Download model if required
# RUN python download_model.py

# ---- Stage 2: Runtime Image ----
FROM python:3.10-slim AS runtime
WORKDIR /app

# OS deps required at runtime
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        ffmpeg \
        libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

# Copy installed libs
COPY --from=builder /usr/local /usr/local

# Copy application code
COPY --from=builder /app /app

ENV PYTHONUNBUFFERED=1

ENTRYPOINT ["python", "main.py"]
