FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY services/pay-per-use-service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

ENV PYTHONPATH="/app"

COPY services/pay-per-use-service/main.py /app/
COPY services/pay-per-use-service/app /app/app

RUN useradd -m appuser && chown -R appuser /app
USER appuser

EXPOSE 8006

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8006", "--workers", "1"]
