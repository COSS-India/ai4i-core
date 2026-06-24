# ai4i-core

Consolidated utility libraries for AI4I microservices — a single installable
package providing the cross-cutting concerns (FastAPI bootstrap helpers, logging,
observability, telemetry, exceptions, and email) shared across the AI4I backend
services.

## Installation

```bash
pip install ai4i-core
```

## Subpackages

| Subpackage | Purpose |
| --- | --- |
| `ai4i_core.bootstrap` | FastAPI app-factory helpers: cache, database, Redis, health router, rate limiting, schemas, API versioning |
| `ai4i_core.context` | Shared `contextvars` (trace id, tenant id, user id, endpoint path) read by the logging and telemetry layers |
| `ai4i_core.email` | Provider-agnostic transactional email client (SMTP, console; pluggable providers) |
| `ai4i_core.exceptions` | Shared exception hierarchy, response envelope, and FastAPI exception handlers |
| `ai4i_core.logging` | Structured JSON logging with trace/tenant correlation and request middleware |
| `ai4i_core.observability` | Prometheus metrics collection and ASGI middleware |
| `ai4i_core.telemetry` | OpenTelemetry tracing, W3C context propagation, OpenSearch query clients |

## Usage

```python
from ai4i_core.bootstrap import create_service_app, init_database, init_redis
from ai4i_core.logging import get_logger, RequestMiddleware
from ai4i_core.exceptions import AppError, InsufficientPermissionsError
from ai4i_core.observability import setup_observability, ObservabilityMiddleware
from ai4i_core.telemetry import TraceManager, trace_stage
from ai4i_core.email import EmailClient, EmailMessage
from ai4i_core.context import get_trace_id, get_tenant_id
```

Each subpackage's `__init__.py` (`__all__`) lists its full public surface.

## Requirements

- Python `>= 3.11`

## License

MIT — see [LICENSE](LICENSE).

## Links

- Source: <https://github.com/COSS-India/ai4i-core>
- Issues: <https://github.com/COSS-India/ai4i-core/issues>
