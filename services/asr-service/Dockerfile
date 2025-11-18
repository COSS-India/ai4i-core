# Stage 1: builder
FROM python:3.8-slim AS builder
WORKDIR /app

# Install only build-time OS deps
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
      ffmpeg \
      libsndfile1 \
      build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy only dependency manifest(s)
COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY . .

# (Optional) Download model weights only if needed at build time
# Better: consider moving model download to runtime or initialisation script
RUN python download_model.py

# Stage 2: runtime
FROM python:3.8-slim AS runtime
WORKDIR /app

# Copy installed dependencies from builder
COPY --from=builder /usr/local/lib/python3.8/site-packages /usr/local/lib/python3.8/site-packages
# Copy source code (without dev/test files if you prune)
COPY --from=builder /app /app

# Remove test/dev artefacts if any
RUN rm -rf /app/tests /app/.git

ENV PYTHONUNBUFFERED=1
ENTRYPOINT ["python","main.py"]
