# AI4ICore Model Management Plugin

Reusable Model Management integration module for AI4ICore microservices. Provides Model Management Service client, Triton client, caching, and middleware for automatic service resolution.

## Features

- ✅ **Model Management Service Client** - HTTP client with Redis + in-memory caching
- ✅ **Triton Client Wrapper** - Generic Triton Inference Server client
- ✅ **Model Resolution Middleware** - Automatic `serviceId` → `endpoint` + `model_name` resolution
- ✅ **Multi-layer Caching** - In-memory + Redis for shared caching across instances
- ✅ **Easy Integration** - Simple plugin pattern like observability module

## Installation

### Option 1: Copy-paste at build time (Recommended)

Copy the entire `libs/ai4icore_model_management/` directory to your service during Docker build:

```dockerfile
# In your service Dockerfile
COPY libs/ai4icore_model_management /app/libs/ai4icore_model_management
```

### Option 2: Install as package

```bash
cd libs/ai4icore_model_management
pip install -e .
```

## Quick Start

### 1. Basic Integration (with Middleware)

```python
from fastapi import FastAPI
from ai4icore_model_management import ModelManagementPlugin, ModelManagementConfig
import redis.asyncio as redis

app = FastAPI()

# Initialize Redis (optional, for shared caching)
redis_client = redis.Redis(host="redis", port=6379, decode_responses=True)

# Initialize plugin
config = ModelManagementConfig.from_env()
plugin = ModelManagementPlugin(config)
plugin.register_plugin(app, redis_client=redis_client)

# Your routes can now access resolved service info
@app.post("/api/v1/nmt/inference")
async def inference(request: Request, body: NMTRequest):
    # Middleware automatically resolves serviceId and attaches to request.state
    service_id = request.state.service_id  # From middleware
    triton_endpoint = request.state.triton_endpoint  # Resolved by middleware
    triton_model_name = request.state.triton_model_name  # Resolved by middleware
    triton_client = request.state.triton_client  # Created by middleware
    
    # Use triton_client directly
    # ... your inference logic ...
```

### 2. Manual Usage (without Middleware)

```python
from ai4icore_model_management import ModelManagementClient, TritonClient
from fastapi import Request

# In your dependency or route
async def get_model_info(request: Request):
    model_mgmt_client = request.app.state.model_management_client
    redis_client = request.app.state.redis_client
    
    # Extract auth headers
    auth_headers = {
        "Authorization": request.headers.get("Authorization"),
        "X-API-Key": request.headers.get("X-API-Key")
    }
    
    # Get service info
    service_info = await model_mgmt_client.get_service(
        service_id="ai4bharat/indictrans--gpu-t4",
        use_cache=True,
        redis_client=redis_client,
        auth_headers=auth_headers
    )
    
    # Create Triton client
    triton_client = TritonClient(
        triton_url=service_info.endpoint,
        api_key=service_info.api_key
    )
    
    return triton_client, service_info.triton_model
```

## Configuration

### Environment Variables

```bash
# Model Management Service
MODEL_MANAGEMENT_SERVICE_URL=http://model-management-service:8091
MODEL_MANAGEMENT_SERVICE_API_KEY=your-api-key  # Optional, fallback

# Cache settings
MODEL_MANAGEMENT_CACHE_TTL=300  # 5 minutes
TRITON_ENDPOINT_CACHE_TTL=300

# Default Triton (fallback)
TRITON_ENDPOINT=default-triton-host:8000
TRITON_API_KEY=default-api-key
```

### Programmatic Configuration

```python
from ai4icore_model_management import ModelManagementConfig

config = ModelManagementConfig(
    model_management_service_url="http://model-management-service:8091",
    cache_ttl_seconds=300,
    middleware_enabled=True,
    middleware_paths=["/api/v1/nmt", "/api/v1/transliteration"]
)
```

## Migration Guide

### From NMT Service to Module

**Before (NMT Service):**
```python
# services/nmt-service/services/nmt_service.py
from utils.model_management_client import ModelManagementClient
from utils.triton_client import TritonClient

class NMTService:
    def __init__(self, ..., model_management_client, ...):
        self.model_management_client = model_management_client
    
    async def get_triton_client(self, service_id, auth_headers):
        # Complex resolution logic...
        service_info = await self.model_management_client.get_service(...)
        # ...
```

**After (Using Module):**
```python
# services/nmt-service/main.py
from ai4icore_model_management import ModelManagementPlugin

plugin = ModelManagementPlugin()
plugin.register_plugin(app, redis_client=redis_client)

# services/nmt-service/services/nmt_service.py
async def run_inference(self, request, http_request: Request):
    # Just read from request.state (middleware did the work)
    triton_client = http_request.state.triton_client
    model_name = http_request.state.triton_model_name
    # ... use directly ...
```

## API Reference

### ModelManagementClient

```python
client = ModelManagementClient(
    base_url="http://model-management-service:8091",
    api_key="optional-api-key",
    cache_ttl_seconds=300,
    timeout=10.0
)

# Get single service
service_info = await client.get_service(
    service_id="ai4bharat/indictrans",
    use_cache=True,
    redis_client=redis_client,
    auth_headers={"Authorization": "Bearer token"}
)

# List all services
services = await client.list_services(
    use_cache=True,
    redis_client=redis_client,
    auth_headers=auth_headers,
    task_type="nmt"  # Optional filter
)
```

### TritonClient

```python
client = TritonClient(
    triton_url="triton-host:8000",  # Without http://
    api_key="optional-api-key"
)

# Send inference request
result = client.send_triton_request(
    model_name="indictrans",
    inputs=[...],  # List[InferInput]
    outputs=[...]   # List[InferRequestedOutput]
)

# Check server health
is_ready = client.is_server_ready()

# List available models
models = client.list_models()
```

### ModelResolutionMiddleware

The middleware automatically:
1. Extracts `serviceId` from request body (`config.serviceId`)
2. Resolves to `endpoint` and `model_name` via Model Management Service
3. Creates and caches `TritonClient` instance
4. Attaches to `request.state`:
   - `request.state.service_id`
   - `request.state.triton_endpoint`
   - `request.state.triton_model_name`
   - `request.state.triton_client`

## Caching Strategy

The module uses a 3-layer caching strategy:

1. **In-memory cache** (per instance) - Fastest, but not shared
2. **Redis cache** (shared) - Fast, shared across all instances
3. **Model Management API** (source of truth) - Only called on cache miss

Cache keys:
- `model_mgmt:service:{serviceId}` - Service info
- `model_mgmt:triton:registry:{serviceId}` - Endpoint + model_name mapping

## Examples

### Example 1: NMT Service Integration

```python
# main.py
from ai4icore_model_management import ModelManagementPlugin
import redis.asyncio as redis

app = FastAPI()

redis_client = redis.Redis(host="redis", port=6379, decode_responses=True)
plugin = ModelManagementPlugin()
plugin.register_plugin(app, redis_client=redis_client)

# routers/inference_router.py
@app.post("/api/v1/nmt/inference")
async def inference(request: Request, body: NMTRequest):
    # Middleware already resolved everything
    triton_client = request.state.triton_client
    model_name = request.state.triton_model_name
    
    # Use directly
    inputs, outputs = prepare_triton_io(body.input)
    result = triton_client.send_triton_request(model_name, inputs, outputs)
    return process_result(result)
```

### Example 2: Transliteration Service Integration

```python
# Same pattern - just copy the module and register plugin
plugin = ModelManagementPlugin()
plugin.register_plugin(app, redis_client=redis_client)

# In your transliteration service
@app.post("/api/v1/transliteration/inference")
async def transliterate(request: Request, body: TransliterationRequest):
    triton_client = request.state.triton_client
    model_name = request.state.triton_model_name
    # ... use for transliteration ...
```

## Troubleshooting

### Middleware not resolving serviceId

- Check that request path matches `middleware_paths` (default: `/api/v1`)
- Verify request body contains `config.serviceId` field
- Check logs for middleware processing

### Cache not working

- Verify Redis connection if using shared cache
- Check cache TTL settings
- Clear cache: `await model_mgmt_client.clear_cache(redis_client)`

### Model Management API errors

- Verify `MODEL_MANAGEMENT_SERVICE_URL` is correct
- Check authentication headers are forwarded correctly
- Verify service exists in Model Management Service

## License

MIT

## Support

For issues and questions, contact the AI4X Team.

