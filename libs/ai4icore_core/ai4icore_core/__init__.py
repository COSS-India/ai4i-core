"""
ai4icore_core — Consolidated AI4ICore utility libraries.

Subpackages:
    bootstrap          — FastAPI app bootstrap helpers (cache, db, redis, schemas, versioning)
    email              — Provider-agnostic transactional email client (SMTP, console, ...)
    exceptions         — Shared exception hierarchy, response envelope, FastAPI handlers
    logging            — Structured JSON logging with trace correlation
    observability      — Prometheus metrics, middleware
    telemetry          — OpenTelemetry tracing, Jaeger / OpenSearch query clients
"""

__version__ = "1.1.3"
