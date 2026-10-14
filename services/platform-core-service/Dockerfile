FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install system build dependencies, plus WeasyPrint's runtime for the Usage
# Viewer report PDF: Pango + HarfBuzz, and a font with the ₹ glyph.
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc libpq-dev curl \
        libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz-subset0 fonts-dejavu-core && \
    rm -rf /var/lib/apt/lists/*

# ── Install service dependencies (ai4i-core pulled from PyPI via requirements.txt) ──
COPY services/platform-core-service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── Copy application code ──
COPY services/platform-core-service/ .

# Run as non-root user for security
RUN useradd --no-create-home --shell /bin/false appuser \
    && chown -R appuser:appuser /app

USER appuser

EXPOSE 8095

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8095/health || exit 1

ENTRYPOINT ["python", "main.py"]
