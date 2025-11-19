# -----------------------------
# STAGE 1 — BUILDER
# -----------------------------
FROM python:3.10-slim AS builder
WORKDIR /app

# Install OS-level dependencies required for audio, numpy, torch
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        ffmpeg \
        libsndfile1 \
        build-essential \
        git \
        libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Copy only requirements first (for pip caching)
COPY requirements.txt .

# Install Python dependencies
RUN pip install --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY . .

# (Optional) Download model files if needed at build time
# RUN python download_model.py


# -----------------------------
# STAGE 2 — RUNTIME
# -----------------------------
FROM python:3.10-slim AS runtime
WORKDIR /app

# Install runtime-only OS deps
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        ffmpeg \
        libsndfile1 \
        libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Copy installed Python packages and application code
COPY --from=builder /usr/local /usr/local
COPY --from=builder /app /app

# Fix Python import paths (VERY IMPORTANT)
ENV PYTHONPATH="/app"
ENV PYTHONUNBUFFERED=1

# Expose service port (optional)
EXPOSE 8087

# Start the application
ENTRYPOINT ["python", "main.py"]
