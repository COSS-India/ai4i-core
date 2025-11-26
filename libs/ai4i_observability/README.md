# AI4I Observability Package

Shared observability library for AI4I microservices. Provides standardized metrics, middleware, and tenant resolution across all services (ASR, TTS, NMT, LLM).

## Features

- ✅ **Automatic Request Metrics**: Middleware records request counts and durations
- ✅ **Business Metrics**: Helpers for service-specific metrics (characters, seconds, translations)
- ✅ **Multi-tenant Support**: Extracts organization/user context from JWT or headers
- ✅ **Prometheus Integration**: Exposes `/metrics` and `/enterprise/metrics` endpoints
- ✅ **Zero Configuration**: Sensible defaults, configurable via environment variables

## Installation

### Option 1: Editable Install (Development)

```bash
cd libs/ai4i_observability
pip install -e .
```

### Option 2: From Service Dockerfile

```dockerfile
COPY ../../libs/ai4i_observability /app/libs/ai4i_observability
RUN pip install --no-cache-dir -e /app/libs/ai4i_observability
```

### Option 3: From requirements.txt

```txt
-e ../../libs/ai4i_observability
```

## Quick Start

### Basic Integration

```python
from fastapi import FastAPI
from ai4i_observability import init_observability

app = FastAPI()

# Initialize observability (one line!)
init_observability(app, service_name="nmt")

@app.post("/api/v1/translate")
async def translate(request: Request):
    # Your handler code
    return {"text": "translated"}
```

### With Business Metrics

```python
from ai4i_observability import init_observability
from ai4i_observability.metrics import record_translation

app = FastAPI()
init_observability(app, service_name="nmt")

@app.post("/api/v1/translate")
async def translate(request: Request, payload: dict):
    # Extract tenant context (set by middleware)
    tenant = request.state.ai4i_tenant
    
    # Your translation logic...
    result = await translate_text(payload)
    
    # Record business metric
    record_translation(
        organization=tenant.organization,
        api_key_name=tenant.api_key_name,
        user_id=tenant.user_id,
        source_language=payload["source_language"],
        target_language=payload["target_language"],
    )
    
    return result
```

## API Reference

### `init_observability()`

Initialize observability for a FastAPI application.

```python
init_observability(
    app: FastAPI,
    service_name: str,
    tenant_resolver: Optional[Callable] = None,
    enable_enterprise: bool = True,
    config: Optional[ObservabilityConfig] = None,
) -> CollectorRegistry
```

**Parameters:**
- `app`: FastAPI application instance
- `service_name`: Service identifier (e.g., "nmt", "tts", "asr")
- `tenant_resolver`: Optional function to extract tenant info. Defaults to `default_tenant_resolver`
- `enable_enterprise`: If True, mounts `/enterprise/metrics` endpoint
- `config`: Optional configuration. If None, loads from environment variables

**Returns:** Prometheus CollectorRegistry instance

### Business Metrics Helpers

#### `record_translation()`

Record a translation request (NMT service).

```python
record_translation(
    organization: str,
    api_key_name: str,
    user_id: str,
    source_language: str,
    target_language: str,
    service: str = "nmt",
)
```

#### `record_tts_characters()`

Record TTS characters synthesized.

```python
record_tts_characters(
    organization: str,
    api_key_name: str,
    user_id: str,
    language: str,
    characters: int,
    service: str = "tts",
)
```

#### `record_asr_seconds()`

Record ASR audio seconds processed.

```python
record_asr_seconds(
    organization: str,
    api_key_name: str,
    user_id: str,
    language: str,
    seconds: float,
    service: str = "asr",
)
```

## Configuration

Configuration is loaded from environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `AI4I_METRICS_BUCKETS` | `0.05,0.1,0.3,0.5,1,2,5` | Histogram buckets for request duration |
| `AI4I_PATH_TEMPLATING` | `true` | Enable path templating to reduce cardinality |
| `AI4I_ENABLE_ENTERPRISE` | `true` | Enable `/enterprise/metrics` endpoint |
| `AI4I_METRICS_NAMESPACE` | `ai4i` | Prefix for metric names |
| `AI4I_SCRAPE_INTERVAL` | `5` | Prometheus scrape interval hint (seconds) |

## Metrics Exposed

### Request Metrics (Automatic)

- `ai4i_requests_total`: Total HTTP requests
  - Labels: `method`, `endpoint`, `status_code`, `service`, `organization`
- `ai4i_request_duration_seconds`: Request duration histogram
  - Labels: `method`, `endpoint`, `service`, `organization`

### Business Metrics (Manual)

- `ai4i_inference_request_total`: Inference requests
  - Labels: `organization`, `service`, `task_type`, `source_language`, `target_language`, `api_key_name`, `user_id`
- `ai4i_tts_characters_synthesized`: TTS characters
  - Labels: `organization`, `service`, `language`, `api_key_name`, `user_id`
- `ai4i_asr_audio_seconds_processed`: ASR audio seconds
  - Labels: `organization`, `service`, `language`, `api_key_name`, `user_id`

## Tenant Resolution

The package automatically extracts tenant context from requests:

1. **JWT Claims** (if available in `request.state`):
   - `request.state.organization` or `request.state.org_id`
   - `request.state.user_id`
   - `request.state.api_key_name` or `request.state.api_key_id`

2. **HTTP Headers** (fallback):
   - `X-Organization-ID`
   - `X-User-ID`
   - `X-API-Key-Name`

3. **Defaults** (if not found):
   - `organization`: "unknown"
   - `user_id`: "anonymous"
   - `api_key_name`: "unknown"

### Custom Tenant Resolver

```python
from ai4i_observability import init_observability
from ai4i_observability.tenant import TenantContext

def custom_tenant_resolver(request: Request) -> TenantContext:
    # Your custom logic
    org = get_org_from_database(request)
    return TenantContext(
        organization=org,
        user_id=request.state.user_id,
        api_key_name=request.state.api_key_name,
    )

init_observability(app, "nmt", tenant_resolver=custom_tenant_resolver)
```

## Endpoints

After initialization, the following endpoints are available:

- `GET /metrics`: Prometheus metrics (standard)
- `GET /enterprise/metrics`: Enterprise metrics (if enabled)

## Integration Guide

See [INTEGRATION_GUIDE.md](../docs/OBSERVABILITY_INTEGRATION.md) for detailed integration steps for each service.

## Development

### Running Tests

```bash
cd libs/ai4i_observability
pytest tests/
```

### Building Package

```bash
python -m build
```

## Version History

- **0.1.0** (2024): Initial release
  - Request metrics middleware
  - Business metrics helpers
  - Tenant resolution
  - Prometheus integration

## License

MIT

