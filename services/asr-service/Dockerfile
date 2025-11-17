# ================================
# Stage 1 — Build dependencies
# ================================
FROM python:3.11-slim AS builder

WORKDIR /app

# Install build tools only here (not in final image)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libsndfile1-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies in a clean user space
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Clean unnecessary cache files
RUN rm -rf /root/.cache/pip
RUN rm -rf /root/.cache


# ================================
# Stage 2 — Final runtime image
# ================================
FROM python:3.11-slim

WORKDIR /app

# Runtime audio libraries only
RUN apt-get update && apt-get install -y --no-install-recommends \
    libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

# Install FFmpeg (static binary — MUCH smaller than Debian ffmpeg)
RUN apt-get update && apt-get install -y --no-install-recommends curl && \
    curl -L https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz \
        -o /tmp/ffmpeg.tar.xz && \
    tar -xf /tmp/ffmpeg.tar.xz -C /tmp && \
    mv /tmp/ffmpeg-*/ffmpeg /usr/local/bin/ && \
    mv /tmp/ffmpeg-*/ffprobe /usr/local/bin/ && \
    chmod +x /usr/local/bin/ffmpeg /usr/local/bin/ffprobe && \
    rm -rf /tmp/* && \
    apt-get purge -y curl

# Copy Python deps from builder
COPY --from=builder /root/.local /home/app/.local

# Add final app code
COPY . .

# Env setup
ENV PATH="/home/app/.local/bin:${PATH}"
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Create non-root user
RUN useradd --create-home --shell /bin/bash app && \
    chown -R app:app /app /home/app
USER app

# Expose ASR port
EXPOSE 8087

# Healthcheck
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8087/health || exit 1

# Start FastAPI app
ENTRYPOINT ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8087"]
