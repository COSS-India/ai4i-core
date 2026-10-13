FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1

WORKDIR /app

# ── Install service dependencies (ai4i-core pulled from PyPI via requirements.txt) ──
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Run as non-root user for security
RUN useradd --no-create-home --shell /bin/false appuser \
    && chown -R appuser:appuser /app

USER appuser

# One job per container run; the k8s CronJob passes `--job <name>`.
ENTRYPOINT ["python", "main.py"]
CMD ["--list"]
