# STAGE 1 – Builder
FROM python:3.10-slim AS builder
WORKDIR /app

# Install OS-dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        ffmpeg \
        libsndfile1 \
        build-essential \
        git \
        libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Copy only requirements first
COPY requirements.txt .

# Install Python deps
RUN pip install --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -r requirements.txt

# Copy all code (service root)
COPY . .

# (Optional) if you still need model download at build time
# RUN python download_model.py

# STAGE 2 – Runtime
FROM python:3.10-slim AS runtime
WORKDIR /app

# Install runtime-only libs
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        ffmpeg \
        libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

# Copy installed dependencies and code from builder
COPY --from=builder /usr/local /usr/local
COPY --from=builder /app /app

# Set environment
ENV PYTHONUNBUFFERED=1
# **Important**: Make sure Python can see 'models' and 'services' modules
ENV PYTHONPATH="/app"

# Expose port if needed
EXPOSE 8087

ENTRYPOINT ["python", "main.py"]
