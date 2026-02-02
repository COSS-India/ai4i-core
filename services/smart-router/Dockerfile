FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY smart-router.py .

# Expose port
EXPOSE 8096

# Run application
CMD ["python", "smart-router.py"]
