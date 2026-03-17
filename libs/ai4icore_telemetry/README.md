# AI4ICore Telemetry Library

Distributed tracing and telemetry capabilities for AI4ICore services using OpenTelemetry and Jaeger.

## Features

- ✅ **Distributed Tracing**: OpenTelemetry integration with Jaeger
- ✅ **Plugin Pattern**: Standard plugin pattern consistent with other AI4ICore modules
- ✅ **Automatic Instrumentation**: FastAPI, HTTPX, and requests library instrumentation
- ✅ **IP Capture**: Automatic client IP capture for request tracing
- ✅ **Span Filtering**: Intelligent filtering of noisy HTTP spans
- ✅ **Multi-tenant Support**: Organization and tenant ID attributes on spans
- ✅ **Easy Integration**: Simple setup for FastAPI services

## Installation

### Option 1: Editable Install (Development)

```bash
cd libs/ai4icore_telemetry
pip install -e .
```

### Option 2: From Service Dockerfile

```dockerfile
COPY libs/ai4icore_telemetry /app/libs/ai4icore_telemetry
RUN pip install --no-cache-dir -e /app/libs/ai4icore_telemetry
```

## Quick Start

### Recommended: Plugin Pattern (New Services)

The plugin pattern provides a unified initialization approach consistent with other AI4ICore modules:

```python
from fastapi import FastAPI
from ai4icore_telemetry import register_telemetry_plugin, TelemetryConfig

app = FastAPI()

# Option 1: Register with default config (from environment variables)
plugin = register_telemetry_plugin(app)

# Option 2: Register with custom config
config = TelemetryConfig()
config.service_name = "my-service"
config.jaeger_endpoint = "http://jaeger:4317"
plugin = register_telemetry_plugin(app, config=config)

# Option 3: Load config from environment variables
config = TelemetryConfig.from_env()
plugin = register_telemetry_plugin(app, config=config)
```

### Alternative: Manual Plugin Setup

```python
from fastapi import FastAPI
from ai4icore_telemetry import TelemetryPlugin, TelemetryConfig

app = FastAPI()

# Create plugin
config = TelemetryConfig.from_env()
plugin = TelemetryPlugin(config)

# Register plugin
plugin.register_plugin(app)

# Access tracer if needed
tracer = plugin.get_tracer()
```

### Legacy: Direct Function Call (Backward Compatibility)

For existing services or simple use cases:

```python
from ai4icore_telemetry import setup_tracing
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

# Setup tracing
tracer = setup_tracing("my-service")

# Instrument FastAPI app
FastAPIInstrumentor.instrument_app(app)

# Instrument HTTPX client
HTTPXClientInstrumentor().instrument()
```

## Configuration

### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `SERVICE_NAME` | ✅ **Yes** | - | Name of the service (used in traces) |
| `JAEGER_ENDPOINT` | ✅ **Yes** | - | Jaeger OTLP endpoint (e.g., `http://jaeger:4317`) |
| `TELEMETRY_ENABLED` | No | `true` | Enable/disable telemetry plugin |
| `SERVICE_VERSION` | No | - | Version of the service (optional, added to traces if set) |
| `TELEMETRY_INSTRUMENT_FASTAPI` | No | `true` | Enable FastAPI instrumentation |
| `TELEMETRY_INSTRUMENT_HTTPX` | No | `true` | Enable HTTPX client instrumentation |
| `TELEMETRY_INSTRUMENT_REQUESTS` | No | `false` | Enable requests library instrumentation |
| `TELEMETRY_IP_CAPTURE_ENABLED` | No | `true` | Enable IP capture middleware |
| `TELEMETRY_FILTER_HTTP_SPANS` | No | `true` | Filter noisy HTTP receive/send spans |

**Note**: `SERVICE_NAME` and `JAEGER_ENDPOINT` are required. The plugin will fail to initialize if these are not set.

### TelemetryConfig Class

```python
from ai4icore_telemetry import TelemetryConfig

# Create config with defaults
config = TelemetryConfig()

# Create config from environment variables
config = TelemetryConfig.from_env()

# Create config from dictionary
config = TelemetryConfig.from_dict({
    "service_name": "my-service",
    "enabled": True,
    "jaeger_endpoint": "http://jaeger:4317"
})

# Access configuration
print(config.service_name)
print(config.jaeger_endpoint)
print(config.to_dict())
```

## API Reference

### TelemetryPlugin

Main plugin class for telemetry integration.

#### Methods

- `__init__(config: Optional[TelemetryConfig] = None)`: Initialize plugin
- `register_plugin(app: FastAPI, **kwargs) -> None`: Register plugin with FastAPI app
- `register_middleware(app: FastAPI) -> None`: Register middleware only
- `register_instrumentation() -> None`: Register instrumentation only
- `get_tracer()`: Get OpenTelemetry tracer instance
- `get_config() -> TelemetryConfig`: Get configuration instance
- `is_initialized() -> bool`: Check if plugin is initialized
- `get_status() -> Dict[str, Any]`: Get plugin status information
- `update_config(new_config: Dict[str, Any]) -> None`: Update configuration
- `close() -> None`: Cleanup resources (async)

### TelemetryConfig

Configuration class for telemetry plugin.

#### Properties

- `enabled: bool`: Enable/disable telemetry
- `service_name: str`: Service name for traces
- `service_version: str`: Service version
- `jaeger_endpoint: str`: Jaeger OTLP endpoint
- `instrument_fastapi: bool`: Enable FastAPI instrumentation
- `instrument_httpx: bool`: Enable HTTPX instrumentation
- `instrument_requests: bool`: Enable requests instrumentation
- `ip_capture_enabled: bool`: Enable IP capture middleware
- `filter_http_spans: bool`: Filter noisy HTTP spans

#### Methods

- `from_env() -> TelemetryConfig`: Create config from environment variables
- `from_dict(config_dict: Dict) -> TelemetryConfig`: Create config from dictionary
- `to_dict() -> Dict[str, Any]`: Convert config to dictionary

### Convenience Functions

- `create_telemetry_plugin(config: Optional[TelemetryConfig] = None) -> TelemetryPlugin`: Create plugin instance
- `register_telemetry_plugin(app: FastAPI, config: Optional[TelemetryConfig] = None, **kwargs) -> TelemetryPlugin`: Create and register plugin in one call

### Legacy Functions

- `setup_tracing(service_name: str, jaeger_endpoint: Optional[str] = None) -> Optional[object]`: Setup tracing (backward compatible)
- `get_tracer(service_name: str) -> Optional[object]`: Get tracer instance

## Examples

### Example 1: Basic Plugin Integration

```python
from fastapi import FastAPI
from ai4icore_telemetry import register_telemetry_plugin

app = FastAPI()

# Register telemetry plugin
plugin = register_telemetry_plugin(app)

@app.get("/health")
async def health():
    return {"status": "healthy"}
```

### Example 2: Custom Configuration

```python
from fastapi import FastAPI
from ai4icore_telemetry import TelemetryPlugin, TelemetryConfig

app = FastAPI()

# Create custom config
config = TelemetryConfig()
config.service_name = "payment-service"
config.service_version = "2.1.0"
config.jaeger_endpoint = "http://jaeger-prod:4317"
config.instrument_requests = True  # Enable requests library instrumentation

# Create and register plugin
plugin = TelemetryPlugin(config)
plugin.register_plugin(app)
```

### Example 3: Using Tracer in Code

```python
from fastapi import FastAPI
from ai4icore_telemetry import register_telemetry_plugin
from opentelemetry import trace

app = FastAPI()
plugin = register_telemetry_plugin(app)

@app.get("/process")
async def process_data():
    tracer = plugin.get_tracer()
    
    with tracer.start_as_current_span("process_data") as span:
        span.set_attribute("operation", "data_processing")
        
        # Your business logic here
        result = perform_processing()
        
        span.set_attribute("result.size", len(result))
        return result
```

### Example 4: Disable IP Capture

```python
from fastapi import FastAPI
from ai4icore_telemetry import TelemetryConfig, register_telemetry_plugin

app = FastAPI()

config = TelemetryConfig.from_env()
config.ip_capture_enabled = False  # Disable IP capture

plugin = register_telemetry_plugin(app, config=config)
```

### Example 5: Integration with Lifespan

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
from ai4icore_telemetry import register_telemetry_plugin

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    plugin = register_telemetry_plugin(app)
    app.state.telemetry_plugin = plugin
    yield
    # Shutdown
    await plugin.close()

app = FastAPI(lifespan=lifespan)
```

### Example 6: Conditional Registration

```python
from fastapi import FastAPI
from ai4icore_telemetry import TelemetryConfig, register_telemetry_plugin
import os

app = FastAPI()

# Only register if telemetry is enabled
config = TelemetryConfig.from_env()
if config.enabled:
    plugin = register_telemetry_plugin(app, config=config)
```

## Adoption Guide

### For New Services

1. **Install the library** (see Installation section)

2. **Add to your FastAPI app**:
   ```python
   from ai4icore_telemetry import register_telemetry_plugin
   
   app = FastAPI()
   plugin = register_telemetry_plugin(app)
   ```

3. **Set required environment variables**:
   ```bash
   export SERVICE_NAME="my-service"  # Required
   export JAEGER_ENDPOINT="http://jaeger:4317"  # Required
   export SERVICE_VERSION="1.0.0"  # Optional
   ```

4. **That's it!** Your service now has distributed tracing enabled.

### Migrating from Legacy setup_tracing()

If you're using the legacy `setup_tracing()` function, you can migrate to the plugin pattern:

**Before:**
```python
from ai4icore_telemetry import setup_tracing
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

tracer = setup_tracing("my-service")
FastAPIInstrumentor.instrument_app(app)
HTTPXClientInstrumentor().instrument()
```

**After:**
```python
from ai4icore_telemetry import register_telemetry_plugin

plugin = register_telemetry_plugin(app)
```

The plugin pattern automatically handles:
- Tracing setup
- FastAPI instrumentation
- HTTPX instrumentation
- IP capture middleware
- Span filtering

### Best Practices

1. **Use Plugin Pattern**: Always use `register_telemetry_plugin()` for new services
2. **Environment Variables**: Configure via environment variables for different environments
3. **Service Name**: Always set `SERVICE_NAME` environment variable
4. **Lifespan Integration**: Register plugin in lifespan startup for proper initialization order
5. **Error Handling**: Plugin gracefully handles missing dependencies

## Troubleshooting

### Issue: Traces not appearing in Jaeger

**Symptoms**: Service is running but no traces appear in Jaeger UI.

**Solutions**:
1. Check Jaeger endpoint: `echo $JAEGER_ENDPOINT`
2. Verify Jaeger is running: `curl http://jaeger:4317`
3. Check plugin status: `plugin.get_status()`
4. Verify OpenTelemetry is installed: `pip list | grep opentelemetry`
5. Check logs for errors during plugin initialization

### Issue: "OpenTelemetry not available" warning

**Symptoms**: Warning message about OpenTelemetry not being available.

**Solutions**:
1. Install OpenTelemetry: `pip install opentelemetry-api opentelemetry-sdk`
2. Install OTLP exporter: `pip install opentelemetry-exporter-otlp-proto-grpc`
3. Check import errors in logs

### Issue: Too many spans in Jaeger

**Symptoms**: Jaeger UI is cluttered with HTTP receive/send spans.

**Solutions**:
1. Enable span filtering: `export TELEMETRY_FILTER_HTTP_SPANS=true` (default)
2. For API gateway, spans are intentionally kept for detailed breakdown
3. Check `filter_http_spans` config option

### Issue: IP addresses not captured

**Symptoms**: Spans don't have client IP attributes.

**Solutions**:
1. Enable IP capture: `export TELEMETRY_IP_CAPTURE_ENABLED=true` (default)
2. Ensure IPCaptureMiddleware is registered (automatic with plugin)
3. Check that middleware runs after FastAPI instrumentation

### Issue: Plugin not initializing

**Symptoms**: `plugin.is_initialized()` returns `False`.

**Solutions**:
1. Check plugin status: `plugin.get_status()`
2. Verify required environment variables are set:
   - `SERVICE_NAME` (required)
   - `JAEGER_ENDPOINT` (required)
3. Verify `TELEMETRY_ENABLED=true` (if you want to enable it)
4. Review logs for initialization errors - missing required env vars will be logged

### Issue: Instrumentation not working

**Symptoms**: HTTP requests not creating spans.

**Solutions**:
1. Verify FastAPI instrumentation: `config.instrument_fastapi`
2. Check that `register_plugin()` was called with `instrument_app=True` (default)
3. Ensure plugin is registered before app startup
4. Check OpenTelemetry instrumentation packages are installed

### Debug Mode

Enable debug logging to see detailed telemetry information:

```python
import logging
logging.getLogger("ai4icore_telemetry").setLevel(logging.DEBUG)
```

## Architecture

### Plugin Pattern

The telemetry library follows the standard AI4ICore plugin pattern:

```
TelemetryPlugin
├── TelemetryConfig (configuration)
├── setup_tracing() (tracing setup)
├── register_instrumentation() (OpenTelemetry instrumentation)
└── register_middleware() (IP capture middleware)
```

### Span Processing

1. **OrganizationSpanProcessor**: Adds organization and tenant_id attributes to all spans
2. **FilteringSpanExporter**: Filters noisy HTTP receive/send spans (except for API gateway)
3. **BatchSpanProcessor**: Batches spans for efficient export to Jaeger

### Integration Points

- **FastAPI**: Automatic request/response tracing
- **HTTPX**: Automatic HTTP client tracing
- **Requests**: Optional requests library tracing
- **IP Capture**: Automatic client IP extraction from headers

## Additional Utilities

### OpenSearch Client

```python
from ai4icore_telemetry import OpenSearchQueryClient

client = OpenSearchQueryClient()
results = await client.search_logs(query="error", limit=100)
```

### Jaeger Client

```python
from ai4icore_telemetry import JaegerQueryClient

client = JaegerQueryClient()
traces = await client.search_traces(service="my-service", limit=10)
```

### IP Capture

```python
from ai4icore_telemetry import extract_client_ip, add_ip_to_current_span
from fastapi import Request

# Extract IP from request
ip = extract_client_ip(request)

# Add IP to current span
add_ip_to_current_span(request)
```

### RBAC Helpers

```python
from ai4icore_telemetry import get_organization_filter, extract_user_info

# Get organization filter for queries
org_filter = get_organization_filter()

# Extract user info from JWT
user_info = extract_user_info(token)
```

## Version History

- **1.0.0**: Initial release with plugin pattern support

## Support

For issues, questions, or contributions, please contact the AI4ICore team.
