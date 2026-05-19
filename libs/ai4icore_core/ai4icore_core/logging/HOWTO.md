# Structured Logging — How to use in a service

All logs are written to stdout as structured JSON. Fluentbit reads stdout and forwards to OpenSearch. No Kafka handler, no file handler, no special log shipper setup required in the service.

---

## Quickstart

Two steps in `main.py`:

```python
import logging
from fastapi import FastAPI
from ai4icore_core.logging import configure_logging, RequestMiddleware

logger = logging.getLogger(__name__)

def create_app() -> FastAPI:
    app = FastAPI(title="my-service")

    configure_logging(service_name="my-service")  # 1. set up root logger
    app.add_middleware(RequestMiddleware)          # 2. seed trace ID per request

    # include routers, other middleware, etc.
    return app

app = create_app()
```

Then use standard Python logging everywhere else — no special imports, no per-file setup:

```python
import logging

logger = logging.getLogger(__name__)

logger.info("user created")
logger.warning("quota approaching limit")
logger.error("database unreachable")
```

---

## What `configure_logging()` does

- Attaches a `JSONFormatter` to the root logger (all logs come out as structured JSON)
- Attaches a `ContextFilter` that injects `trace_id` and `tenant_id` into every log record automatically
- Clears any existing root logger handlers so there are no duplicate log lines
- Quiets noisy third-party libraries (see [Controlling third-party log levels](#controlling-third-party-log-levels))
- Disables `uvicorn.access` log — `RequestMiddleware` already logs every request

Because every logger in the process propagates to the root logger, this single call covers your service code, SQLAlchemy, httpx, FastAPI internals — everything.

**Must be called before the first request arrives**, typically at the top of `create_app()`.

---

## What `RequestMiddleware` does

- Reads `X-Correlation-ID` from the incoming request header
- Normalises it to 32-hex (strips hyphens from a UUID, validates format)
- Generates a new trace ID if the header is absent or invalid
- Stores the trace ID in a contextvar so every log line for this request automatically includes it
- Echoes the trace ID back in the response `X-Correlation-ID` header
- Logs one structured line per request: `METHOD /path STATUS duration_ms`
- Skips logging `OPTIONS` preflight requests by default

**Must be added last** with `add_middleware()`. FastAPI middleware runs in LIFO order — last added runs first on the request — so `RequestMiddleware` must be outermost to seed the trace ID before any other code runs.

```python
app.add_middleware(OtherMiddleware)   # runs second
app.add_middleware(RequestMiddleware) # runs first — add last
```

---

## JSON output format

Every log line is a JSON object on a single line:

```json
{
  "timestamp": "2026-05-19T10:23:45.123456+00:00",
  "level": "INFO",
  "service": "my-service",
  "trace_id": "4a7f3c2e1b0d9e8f7a6b5c4d3e2f1a0b",
  "tenant_id": "acme-corp",
  "message": "user created",
  "service_version": "1.0.0",
  "environment": "production",
  "hostname": "pod-abc123",
  "logger": "app.services.user_service"
}
```

For `ERROR` and above, `file`, `line`, and `function` are also included. Exceptions are serialised under `exception`.

---

## Attaching structured data to a log line

Pass a `context` dict via `extra` to include structured fields alongside the message:

```python
logger.info("order placed", extra={"context": {
    "order_id": "ord-789",
    "amount": 49.99,
    "currency": "USD",
}})
```

Output:
```json
{
  "level": "INFO",
  "message": "order placed",
  "trace_id": "...",
  "context": {
    "order_id": "ord-789",
    "amount": 49.99,
    "currency": "USD"
  }
}
```

---

## Controlling the root log level

The root log level is the global floor — no logger in the process can emit below it.

Priority order (highest wins):

| Source | Example |
|---|---|
| Argument to `configure_logging()` | `configure_logging(log_level="DEBUG")` |
| `LOG_LEVEL` environment variable | `LOG_LEVEL=DEBUG` |
| `.env` file in the working directory | `LOG_LEVEL=DEBUG` |
| Default | `INFO` |

In production, set `LOG_LEVEL` as a container environment variable. Do not hardcode the level in the `configure_logging()` call.

Accepted values: `DEBUG`, `INFO`, `WARNING`, `ERROR` (case-insensitive).

---

## Controlling third-party log levels

By default, `configure_logging()` sets these libraries to `WARNING` to reduce noise:

```
httpx, httpcore, urllib3, sqlalchemy.engine
```

To change this, pass `third_party_log_levels` with the **full list** your service wants. This replaces the defaults entirely — the service owns the complete set of overrides.

**Keep the defaults, add more:**
```python
configure_logging(
    service_name="my-service",
    third_party_log_levels={
        "httpx": "WARNING",
        "httpcore": "WARNING",
        "urllib3": "WARNING",
        "sqlalchemy.engine": "WARNING",
        "boto3": "WARNING",       # add service-specific library
        "botocore": "WARNING",
    },
)
```

**Enable SQLAlchemy query logging for this service:**
```python
configure_logging(
    service_name="my-service",
    third_party_log_levels={
        "httpx": "WARNING",
        "httpcore": "WARNING",
        "urllib3": "WARNING",
        "sqlalchemy.engine": "INFO",  # override — want query logs
    },
)
```

**No third-party overrides — everything follows the root level:**
```python
configure_logging(
    service_name="my-service",
    third_party_log_levels={},
)
```

---

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `SERVICE_NAME` | `""` | Appears in every log line as `service`. Overridden by the `service_name` argument. |
| `SERVICE_VERSION` | `1.0.0` | Appears in every log line as `service_version`. |
| `ENVIRONMENT` or `ENV` | `development` | Appears in every log line as `environment`. |
| `LOG_LEVEL` | `INFO` | Root log level. Overridden by the `log_level` argument. |
| `EXCLUDE_HEALTH_LOGS` | `false` | Skip request logging for `/health` paths. |
| `EXCLUDE_METRICS_LOGS` | `false` | Skip request logging for `/metrics` paths. |
| `EXCLUDE_OPTIONS_LOGS` | `true` | Skip request logging for `OPTIONS` preflight requests. |

---

## Services that do not use FastAPI / have no HTTP requests

Call `configure_logging()` the same way — JSON formatting and context injection still work. Without `RequestMiddleware` there is no per-request trace ID, so `trace_id` will be a freshly generated ID for each log line that falls outside a request context.

---

## What NOT to do

```python
# Do not use get_logger() — it is just logging.getLogger() with an extra call.
# Use the stdlib directly.
from ai4icore_core.logging import get_logger   # unnecessary
logger = get_logger(__name__)                  # unnecessary

# Do this instead:
import logging
logger = logging.getLogger(__name__)
```

```python
# Do not add handlers or formatters to individual loggers.
# configure_logging() sets up the root logger — adding handlers elsewhere
# causes duplicate log lines.
logger.addHandler(logging.StreamHandler())  # do not do this
```

```python
# Do not call configure_logging() more than once.
# Each call clears and resets the root logger handlers.
```
