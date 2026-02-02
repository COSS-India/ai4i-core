# AI4ICore Logging Library

Structured JSON logging library for AI4ICore microservices with trace correlation support.

## Features

- Structured JSON log format
- Automatic trace ID correlation
- Kafka integration for log streaming
- Service metadata injection
- Context-aware logging
- Correlation middleware for FastAPI

## Installation

```bash
pip install -e libs/ai4icore_logging
```

## Quick Start

### 1. Add Correlation Middleware to FastAPI App

```python
from fastapi import FastAPI
from ai4icore_logging import CorrelationMiddleware, get_logger

app = FastAPI()

# Add correlation middleware (extracts X-Correlation-ID from headers)
app.add_middleware(CorrelationMiddleware)

# Get logger
logger = get_logger("my-service")

@app.get("/api/endpoint")
async def my_endpoint():
    # Logs automatically include trace_id from correlation middleware
    logger.info("Processing request", extra={"user_id": "user_123"})
    return {"status": "ok"}
```

### 2. Manual Trace ID Management

```python
from ai4icore_logging import get_logger, set_trace_id, TraceContext

# Option 1: Set trace ID manually
set_trace_id("abc-123-def")
logger = get_logger("my-service")
logger.info("This log will have trace_id=abc-123-def")

# Option 2: Use context manager
with TraceContext("abc-123-def"):
    logger.info("This log will have trace_id=abc-123-def")

# Option 3: Generate new trace ID automatically
with TraceContext():  # Generates new UUID
    logger.info("This log will have a new trace_id")
```

### 3. Get Correlation ID from Request

```python
from fastapi import Request
from ai4icore_logging import get_correlation_id

@app.get("/api/endpoint")
async def my_endpoint(request: Request):
    correlation_id = get_correlation_id(request)
    logger.info(f"Request correlation ID: {correlation_id}")
    return {"correlation_id": correlation_id}
```

## Log Format

All logs are formatted as JSON:

```json
{
  "timestamp": "2024-01-15T10:30:45.123Z",
  "level": "INFO",
  "service": "my-service",
  "message": "Processing request",
  "trace_id": "abc-123-def",
  "service_version": "1.0.0",
  "environment": "development",
  "hostname": "server-01",
  "user_id": "user_123"
}
```

## Configuration

Set environment variables:

- `SERVICE_NAME`: Service name (defaults to logger name)
- `SERVICE_VERSION`: Service version (defaults to "1.0.0")
- `ENVIRONMENT`: Environment name (defaults to "development")
- `LOG_LEVEL`: Log level (defaults to "INFO")
- `KAFKA_BOOTSTRAP_SERVERS`: Kafka servers (defaults to "localhost:9092")

