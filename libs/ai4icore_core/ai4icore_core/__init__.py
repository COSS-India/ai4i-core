"""
ai4icore_core — Consolidated AI4ICore utility libraries.

Subpackages:
    bootstrap          — FastAPI app bootstrap helpers (cache, db, redis, schemas, versioning)
    constants          — Static error codes, messages, and back-compat re-exports
    email              — Provider-agnostic transactional email client (SMTP, console, ...)
    env                — Pydantic-based environment / settings
    exceptions         — Shared exception hierarchy, response envelope, FastAPI handlers
    logging            — Structured JSON logging with trace correlation
    model_management   — Model management client, Triton inference, FastAPI middleware
    observability      — Prometheus metrics, dashboards, middleware
    service_base       — App factory, health, rate limit, service registry, inference headers
    telemetry          — OpenTelemetry tracing, Jaeger / OpenSearch query clients
"""

__version__ = "1.1.0"
