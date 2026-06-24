# ai4i-core

Consolidated utility libraries for AI4ICore microservices. A single installable package that bundles what used to live across ten standalone libraries — constants, env, exceptions, logging, telemetry, observability, model management, service base, bootstrap, and email.

## Installation

```bash
pip install ai4i-core
```

## Subpackages

| Subpackage | Purpose |
| --- | --- |
| `ai4i_core.bootstrap` | FastAPI app bootstrap helpers (cache, database, redis, schemas, versioning) |
| `ai4i_core.constants` | Static error codes, messages, and back-compat re-exports |
| `ai4i_core.email` | Provider-agnostic transactional email client (SMTP, console, pluggable) |
| `ai4i_core.env` | Pydantic-based environment / settings |
| `ai4i_core.exceptions` | Shared exception hierarchy, response envelope, FastAPI handlers |
| `ai4i_core.logging` | Structured JSON logging with trace correlation |
| `ai4i_core.model_management` | Model management client, Triton inference, FastAPI middleware |
| `ai4i_core.observability` | Prometheus metrics, dashboards, middleware |
| `ai4i_core.service_base` | App factory, health, rate limit, service registry, inference headers |
| `ai4i_core.telemetry` | OpenTelemetry tracing, OpenSearch query clients |

## Usage

```python
from ai4i_core.env import app_env
from ai4i_core.logging import get_logger, register_logging_plugin
from ai4i_core.exceptions import register_exception_handlers
from ai4i_core.observability import ObservabilityPlugin, PluginConfig
from ai4i_core.telemetry import register_telemetry_plugin, TelemetryConfig
from ai4i_core.service_base import create_inference_app
```

See each subpackage's source for the full surface.

## Requirements

- Python `>= 3.11`

## License

MIT — see [LICENSE](LICENSE).

## Links

- Source: <https://github.com/COSS-India/ai4i-core>
- Issues: <https://github.com/COSS-India/ai4i-core/issues>
