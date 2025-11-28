# Dhruva Observability Plugin

Enterprise-grade observability features for the Dhruva Platform, including comprehensive metrics, monitoring, and business analytics.

## Features

- ✅ **Automatic Request Metrics**: Middleware automatically tracks all HTTP requests
- ✅ **Automatic Business Metrics**: Extracts TTS characters, NMT characters, ASR audio length from request bodies
- ✅ **Multi-tenant Support**: Extracts organization/app from JWT tokens or headers
- ✅ **Enterprise Metrics**: SLA tracking, quotas, system metrics
- ✅ **Prometheus Integration**: Exposes `/enterprise/metrics` endpoint
- ✅ **Zero Manual Code**: Fully automatic - no manual metric recording needed

## Installation

### Option 1: Editable Install (Development)

```bash
cd libs/dhruva_observability
pip install -e .
```

### Option 2: From Service Dockerfile

```dockerfile
COPY libs/dhruva_observability /app/libs/dhruva_observability
RUN pip install --no-cache-dir -e /app/libs/dhruva_observability
```

## Quick Start

### Basic Integration

```python
from fastapi import FastAPI
from dhruva_observability import ObservabilityPlugin, PluginConfig

app = FastAPI()

# Create and configure plugin
config = PluginConfig()
config.enabled = True
config.customers = ["irctc", "beml", "kisanmitra"]  # Optional: list of customers
config.apps = ["nmt", "tts", "asr"]  # Optional: list of apps

# Register plugin (one line!)
plugin = ObservabilityPlugin(config)
plugin.register_plugin(app)
```

### With Environment Variables

```python
from fastapi import FastAPI
from dhruva_observability import ObservabilityPlugin, PluginConfig

app = FastAPI()

# Load config from environment variables
config = PluginConfig.from_env()
plugin = ObservabilityPlugin(config)
plugin.register_plugin(app)
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `OBSERVE_UTIL_ENABLED` | `false` | Enable/disable plugin |
| `OBSERVE_UTIL_DEBUG` | `false` | Enable debug logging |
| `OBSERVE_UTIL_METRICS_PATH` | `/enterprise/metrics` | Metrics endpoint path |
| `OBSERVE_UTIL_HEALTH_PATH` | `/enterprise/health` | Health endpoint path |
| `OBSERVE_UTIL_CUSTOMERS` | `` | Comma-separated list of customers |
| `OBSERVE_UTIL_APPS` | `` | Comma-separated list of apps |

## Metrics Exposed

### Request Metrics (Automatic)

- `telemetry_obsv_requests_total`: Total HTTP requests
  - Labels: `organization`, `app`, `method`, `endpoint`, `status_code`
- `telemetry_obsv_request_duration_seconds`: Request duration histogram
  - Labels: `organization`, `app`, `method`, `endpoint`

### Business Metrics (Automatic)

- `telemetry_obsv_tts_characters_synthesized`: TTS characters (extracted from request body)
- `telemetry_obsv_nmt_characters_translated`: NMT characters (extracted from request body)
- `telemetry_obsv_asr_audio_seconds_processed`: ASR audio seconds (extracted from request body)
- `telemetry_obsv_llm_tokens_processed_total`: LLM tokens
- Plus many more (OCR, transliteration, NER, etc.)

### System Metrics

- `telemetry_obsv_system_cpu_percent`: CPU usage
- `telemetry_obsv_system_memory_percent`: Memory usage
- `telemetry_obsv_sla_availability_percent`: SLA availability
- `telemetry_obsv_sla_compliance_percent`: SLA compliance

## Key Differences from Custom Package

### ✅ Automatic Metric Extraction

**Custom Package (ai4i_observability):**
```python
# Manual recording required
from ai4i_observability.metrics import record_tts_characters
record_tts_characters(organization, api_key_name, user_id, language, characters)
```

**Dhruva Plugin:**
```python
# Fully automatic - extracts from request body
# No manual code needed!
```

### ✅ More Features

- Automatic service type detection
- Automatic metric extraction from request bodies
- SLA tracking
- Organization quotas
- System metrics
- More comprehensive error tracking

## Endpoints

After registration, the following endpoints are available:

- `GET /enterprise/metrics`: Prometheus metrics
- `GET /enterprise/health`: Health check
- `GET /enterprise/config`: Configuration

## Integration Guide

See [INTEGRATION_GUIDE.md](../../docs/DHRUVA_OBSERVABILITY_INTEGRATION.md) for detailed integration steps.

## Version

**1.0.9** - Enterprise-grade observability plugin

## License

MIT

