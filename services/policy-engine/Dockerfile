FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy code
COPY . .

# Run as non-root user for security
RUN useradd -m appuser && chown -R appuser /app
USER appuser

# Expose port
EXPOSE 8095

# Start with production settings
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8095", "--workers", "1"]
