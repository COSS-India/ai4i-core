# ai4icore_core

The consolidated core library for AI4I-Core microservices. Replaces the individual `ai4icore_exceptions`, `ai4icore_env`, `ai4icore_constants`, `ai4icore_logging`, `ai4icore_auth`, `ai4icore_bootstrap`, `ai4icore_observability`, `ai4icore_telemetry`, `ai4icore_platform_core`, `ai4icore_service_base`, and `ai4icore_email` packages.

## Subpackages

| Module | Purpose |
|---|---|
| `ai4icore_core.exceptions` | Shared exception hierarchy, response envelopes, FastAPI exception handlers |
| `ai4icore_core.env` | Pydantic-based environment configuration (`AppEnv`, `app_env`) |
| `ai4icore_core.constants` | Static error codes, error messages, service-name maps |
| `ai4icore_core.logging` | Structured JSON logging with trace correlation, Kafka log shipping |
| `ai4icore_core.auth` | JWT verification (RS256/JWKS), permission checking, auth middleware |
| `ai4icore_core.bootstrap` | App factory, DB/Redis init, rate limiting, health checks, base schemas |
| `ai4icore_core.observability` | Prometheus metrics collector, observability plugin and middleware |
| `ai4icore_core.telemetry` | OpenTelemetry tracing, Jaeger/OpenSearch query clients, span helpers |
| `ai4icore_core.platform_core` | Model management client, Triton inference client, resolution middleware |
| `ai4icore_core.service_base` | Inference service factory (`create_inference_app`), service registry, rate limiting |
| `ai4icore_core.email` | Provider-agnostic transactional email client (SMTP today, pluggable for SES/SendGrid/etc.) |

## Installation

```bash
# Local (editable)
pip install -e libs/ai4icore_core

# From PyPI (after publishing)
pip install ai4icore-core
```

## Usage

```python
from ai4icore_core.exceptions import AppError, register_exception_handlers
from ai4icore_core.env import app_env
from ai4icore_core.logging import get_logger, RequestLoggingMiddleware
from ai4icore_core.auth import JWTVerifier, AuthMiddleware, PermissionChecker
from ai4icore_core.bootstrap import init_database, get_db, BaseSchema
from ai4icore_core.observability import ObservabilityPlugin, MetricsCollector
from ai4icore_core.telemetry import setup_tracing, TelemetryPlugin
from ai4icore_core.platform_core import ModelManagementPlugin, TritonClient
from ai4icore_core.service_base import create_inference_app
from ai4icore_core.email import EmailClient, EmailMessage, get_email_client
```

## Publishing to PyPI

```bash
cd libs/ai4icore_core
python -m build
python -m twine upload dist/*
```
