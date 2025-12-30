# -----------------------------
# STAGE 1 — BUILDER
# -----------------------------
    FROM python:3.11-slim AS builder
    WORKDIR /app
    
    RUN apt-get update && \
        apt-get install -y --no-install-recommends \
            gcc \
            g++ \
            curl \
            libpq-dev \
            ffmpeg \
            libsndfile1-dev \
            build-essential \
            git \
            libgomp1 \
        && rm -rf /var/lib/apt/lists/*
    
    # Copy AI4ICore Observability Plugin
    COPY libs/ai4icore_observability /app/libs/ai4icore_observability
    
    # Copy AI4ICore Model Management Plugin
    COPY libs/ai4icore_model_management /app/libs/ai4icore_model_management
    
    # Copy requirements and install dependencies
    COPY services/asr-service/requirements.txt .
    
    # Upgrade pip, setuptools, and wheel first
    RUN pip install --upgrade pip setuptools wheel
    
    # Install Python dependencies from requirements.txt first
    RUN pip install --no-cache-dir --user -r requirements.txt
    
    # Then install the observability plugin (after its dependencies are installed)
    RUN pip install --no-cache-dir --user -e /app/libs/ai4icore_observability
    
    # Install the model management plugin
    RUN pip install --no-cache-dir --user -e /app/libs/ai4icore_model_management
    
    
    # -----------------------------
    # STAGE 2 — RUNTIME
    # -----------------------------
    FROM python:3.11-slim AS runtime
    WORKDIR /app
    
    RUN apt-get update && \
        apt-get install -y --no-install-recommends \
            curl \
            libpq5 \
            libssl3 \
            libnss3 \
            libstdc++6 \
            ca-certificates \
            ffmpeg \
            libsndfile1 \
            libgomp1 \
        && rm -rf /var/lib/apt/lists/*
    
    # Copy Python libraries
    COPY --from=builder /root/.local /root/.local
    ENV PATH=/root/.local/bin:$PATH
    
    # Copy AI4ICore Observability Plugin
    COPY --from=builder /app/libs/ai4icore_observability /app/libs/ai4icore_observability
    
    # Copy AI4ICore Model Management Plugin
    COPY --from=builder /app/libs/ai4icore_model_management /app/libs/ai4icore_model_management
    
    # Copy application code
    COPY services/asr-service .
    
    # ❗ IMPORTANT FIX: REMOVE .env so ConfigMap overrides work
    RUN rm -f /app/.env || true
    
    ENV PYTHONUNBUFFERED=1
    ENV PYTHONPATH="/app"
    
    EXPOSE 8087
    
    ENTRYPOINT ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8087"]
    