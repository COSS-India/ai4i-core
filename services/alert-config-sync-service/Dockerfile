FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY main.py .

# Create directories for YAML files (these should be mounted as volumes)
RUN mkdir -p /etc/prometheus/rules /etc/alertmanager

# Run the sync service
CMD ["python", "main.py"]

