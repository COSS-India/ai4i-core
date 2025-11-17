# ===========================================================
# Stage 1: Builder
# ===========================================================
FROM python:3.11-slim as builder

WORKDIR /app

# Install system build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc \
        g++ \
        make \
        libpq-dev \
        curl \
        xz-utils \
        libsndfile1-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .

# Install Python packages to user site (keeps final image clean)
RUN pip install --upgrade pip \
    && pip install --no-cache-dir --user -r requirements.txt


# ===========================================================
# Stage 2: Final Runtime Image
# ===========================================================
FROM python:3.11-slim

WORKDIR /app

# Install runtime OS dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq5 \
        libsndfile1 \
        curl \
        xz-utils \
    && rm -rf /var/lib/apt/lists/*

# -----------------------------------------------------------
# Install FFmpeg (static build = very small but powerful)
# -----------------------------------------------------------
RUN curl -L https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz \
        -o /tmp/ffmpeg.tar.xz \
    && tar -xf /tmp/ffmpeg.tar.xz -C /tmp \
    && mv /tmp/ffmpeg-*/ffmpeg /usr/local/bin/ \
    && mv /tmp/ffmpeg-*/ffprobe /usr/local/bin/ \
    && chmod +x /usr/local/bin/ffmpeg /usr/local/bin/ffprobe \
    && rm -rf /tmp/* \
    && apt-get purge -y curl xz-utils \
    && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*


# ===========================================================
# Python Runtime Environment
# ===========================================================
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH=/home/app/.local/bin:$PATH


# Create non-root user
RUN useradd --create-home --shell /bin/bash app

# Copy Python packages from builder stage
COPY --from=builder /root/.local /home/app/.local

# Copy application code (respects .dockerignore)
COPY . .

# Fix permissions
RUN chown -R app:app /app /home/app/.local \
    && chmod +x /home/app/.local/bin/*

USER app

# ===========================================================
# Networking & Healthcheck
# ===========================================================
EXPOSE 8087

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8087/health || exit 1

# ===========================================================
# Entrypoint
# ===========================================================
ENTRYPOINT ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8087"]
