# -----------------------------
# STAGE 1 — BUILDER
# -----------------------------
FROM python:3.11-slim AS builder

WORKDIR /app

RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    curl \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements from build context
COPY requirements.txt .
# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Verify packaging is installed (for debugging)
RUN python -c "import packaging; print(f'packaging version: {packaging.__version__}')" || (echo "ERROR: packaging not found!" && exit 1)

# -----------------------------
# STAGE 2 — RUNTIME
# -----------------------------
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \    
    curl \
    libpq5 \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --shell /bin/bash app

# Copy Python site-packages
COPY --from=builder /usr/local /usr/local

# Ensure packaging is available in runtime - install system-wide AND user-wide
# This ensures it's available regardless of Python path resolution
RUN pip install --no-cache-dir packaging>=21.0 && \
    pip install --no-cache-dir --target=/usr/local/lib/python3.11/site-packages packaging>=21.0 && \
    python -c "import sys; sys.path.insert(0, '/usr/local/lib/python3.11/site-packages'); import packaging; print(f'✓ packaging {packaging.__version__} verified')" || \
    (echo "ERROR: packaging not available!" && exit 1)

COPY . .

RUN chown -R app:app /app
USER app

EXPOSE 8090

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
  CMD curl -f http://localhost:8090/api/v1/llm/health || exit 1

ENTRYPOINT ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8090"]
