# AI4ICore Logging Library

Structured JSON logging library for AI4ICore microservices with trace correlation support.

## Features

- Structured JSON log format
- Automatic trace ID correlation
- Kafka integration for log streaming
- Service metadata injection
- Context-aware logging
- Correlation middleware for FastAPI
- **Plugin pattern** for one-line registration (recommended)

## Installation

```bash
pip install -e libs/ai4icore_logging
```

## Quick Start

### Recommended: Plugin Pattern (One-Line Registration)

```python
from fastapi import FastAPI
from ai4icore_logging import register_logging_plugin, get_logger

app = FastAPI()

# One-line registration: configures logging + adds middleware
register_logging_plugin(app)

# Get logger
logger = get_logger("my-service")

@app.get("/api/endpoint")
async def my_endpoint():
    # Logs automatically include trace_id, tenant_id, correlation_id
    logger.info("Processing request", extra={"user_id": "user_123"})
    return {"status": "ok"}
```

**With custom configuration:**

```python
from fastapi import FastAPI
from ai4icore_logging import LoggingConfig, register_logging_plugin

app = FastAPI()

# Create custom config
config = LoggingConfig(
    service_name="my-service",
    use_kafka=True,
    exclude_health_logs=True,
)

# Register plugin with config
register_logging_plugin(app, config=config)
```

### Alternative: Manual Middleware Setup (Legacy)

If you prefer manual control, you can still add middleware individually:

```python
from fastapi import FastAPI
from ai4icore_logging import (
    configure_logging,
    CorrelationMiddleware,
    ServiceRequestLoggingMiddleware,
    get_logger
)

app = FastAPI()

# Step 1: Configure logging
configure_logging(
    service_name="my-service",
    use_kafka=False,
)

# Step 2: Add middleware manually
app.add_middleware(CorrelationMiddleware)
app.add_middleware(ServiceRequestLoggingMiddleware)

# Get logger
logger = get_logger("my-service")

@app.get("/api/endpoint")
async def my_endpoint():
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

### Using LoggingConfig Class (Recommended)

```python
from ai4icore_logging import LoggingConfig, register_logging_plugin

# Create config from environment variables
config = LoggingConfig.from_env()

# Or create with custom values
config = LoggingConfig(
    service_name="my-service",
    service_version="2.0.0",
    environment="production",
    use_kafka=True,
    exclude_health_logs=True,
    exclude_metrics_logs=True,
)

register_logging_plugin(app, config=config)
```

### Environment Variables

All configuration can be set via environment variables:

**Core Settings:**
- `SERVICE_NAME`: Service name (defaults to "unknown")
- `SERVICE_VERSION`: Service version (defaults to "1.0.0")
- `ENVIRONMENT`: Environment name (defaults to "development")
- `LOG_LEVEL`: Log level (defaults to "INFO")
- `ROOT_LOG_LEVEL`: Root logger level (defaults to "WARNING")

**Kafka Settings:**
- `USE_KAFKA_LOGGING`: Enable Kafka handler (defaults to "false")
- `KAFKA_LOG_TOPIC`: Kafka topic name (defaults to "logs")

**Middleware Settings:**
- `LOGGING_PLUGIN_ENABLED`: Enable plugin (defaults to "true")
- `CORRELATION_MIDDLEWARE_ENABLED`: Enable correlation middleware (defaults to "true")
- `REQUEST_LOGGING_MIDDLEWARE_ENABLED`: Enable request logging middleware (defaults to "true")
- `CORRELATION_HEADER_NAME`: Header name for correlation ID (defaults to "X-Correlation-ID")

**Request Logging Filtering:**
- `EXCLUDE_HEALTH_LOGS`: Skip /health endpoint logs (defaults to "false")
- `EXCLUDE_METRICS_LOGS`: Skip /metrics endpoint logs (defaults to "false")
- `EXCLUDE_OPTIONS_LOGS`: Skip OPTIONS (CORS) logs (defaults to "true")
- `ALLOWED_LOG_LEVELS`: Comma-separated levels to log (defaults to "DEBUG,INFO,WARNING,ERROR")
- `MIN_LOG_LEVEL`: Minimum log level fallback (defaults to "INFO")
- `INCLUDE_4XX_LOGS`: Include 4xx errors in logs (defaults to "false", gateway logs them)

