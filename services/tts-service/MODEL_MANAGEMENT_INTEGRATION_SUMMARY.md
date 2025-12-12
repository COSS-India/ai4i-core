# TTS Service - Model Management Integration Summary

## Overview
Successfully implemented Model Management Service integration in the TTS service following the pattern from the NMT service and the integration guide at `docs/MODEL_MANAGEMENT_INTEGRATION_GUIDE.md`.

## Implementation Date
December 12, 2025

## Changes Made

### 1. New Files Created

#### `utils/model_management_client.py`
- **Purpose**: Client for interacting with the Model Management Service API
- **Features**:
  - Multi-layer caching (in-memory + Redis)
  - Auth header forwarding
  - Service info retrieval via `view_service` and `list_services` endpoints
  - Configurable cache TTL (default: 300 seconds)

#### `utils/auth_utils.py`
- **Purpose**: Extract and normalize authentication headers from incoming requests
- **Features**:
  - Case-insensitive header extraction
  - Supports Authorization, X-API-Key, and X-Auth-Source headers
  - Headers are forwarded to downstream services (Model Management)

### 2. Modified Files

#### `services/tts_service.py`
**Major Changes**:
- Updated `__init__` signature to accept:
  - `default_triton_client` (fallback when Model Management unavailable)
  - `get_triton_client_func` (factory for creating clients with different endpoints)
  - `model_management_client` (for resolving service metadata)
  - `redis_client` (for distributed caching)
  - `cache_ttl_seconds` (cache expiration time)

**New Methods**:
- `_get_service_info()`: Fetch service details from Model Management with caching
- `_get_service_registry_entry()`: Get (endpoint, model_name) tuple for a service
- `get_triton_client()`: Dynamically resolve Triton client based on service ID
- `get_model_name()`: Dynamically resolve Triton model name from service metadata
- `_extract_triton_metadata()`: Extract and normalize endpoint + model name from ServiceInfo
- `_get_registry_from_redis()`: Read cached registry entry from Redis
- `_set_registry_in_redis()`: Write registry entry to Redis with TTL
- `invalidate_cache()`: Clear all cache layers for a service

**Updated Methods**:
- `run_inference()`: Now accepts `auth_headers` parameter and uses dynamic endpoint/model resolution

**Key Behavior**:
- Triton endpoint is now resolved at request-time using Model Management Service
- Model name is extracted from service metadata (not hardcoded to "tts")
- Fallback to `TRITON_ENDPOINT` env var if Model Management is unavailable
- Multi-layer caching: in-memory → Redis → Model Management API

#### `routers/inference_router.py`
**Changes**:
- Added imports for `ModelManagementClient` and `extract_auth_headers`
- Updated `get_tts_service()` dependency:
  - Now retrieves `model_management_client` from app state
  - Retrieves `redis_client` from app state
  - Retrieves `get_triton_client_func` from app state
  - Creates `default_triton_client` as fallback (optional)
  - Passes all dependencies to `TTSService` constructor
- Updated `run_inference()` endpoint:
  - Extracts auth headers using `extract_auth_headers()`
  - Passes `auth_headers` to `tts_service.run_inference()`

#### `main.py`
**Changes**:
- Added import for `ModelManagementClient`
- In `lifespan()` startup:
  - Initialize `ModelManagementClient` with URL and cache TTL
  - Create `get_triton_client_func` factory function
  - Store both in `app.state` for access by routers
- In `lifespan()` shutdown:
  - Close `model_management_client` HTTP client

#### `utils/triton_client.py`
**Changes**:
- Added `_normalize_url()` static method:
  - Strips `http://` and `https://` prefixes
  - Ensures URL is in `host:port` format expected by Triton client
- Updated `__init__` to call `_normalize_url()` on the provided URL

#### `env.template`
**New Variables**:
```bash
# Model Management Service Configuration
MODEL_MANAGEMENT_SERVICE_URL=http://model-management-service:8091
MODEL_MANAGEMENT_CACHE_TTL=300
TRITON_ENDPOINT_CACHE_TTL=300

# Triton Inference Server Configuration (fallback if Model Management is unavailable)
TRITON_ENDPOINT=http://triton-server:8000
```

**Note**: `TRITON_ENDPOINT` is now optional and serves as a fallback only.

## Architecture

### Request Flow

```
1. Client sends TTS inference request
   ↓
2. inference_router.run_inference()
   - Extracts auth headers (Authorization, X-API-Key, X-Auth-Source)
   ↓
3. TTSService.run_inference(auth_headers=...)
   - Calls get_model_name(service_id, auth_headers)
   - Calls get_triton_client(service_id, auth_headers)
   ↓
4. get_triton_client() resolution:
   a) Check in-memory cache → if found and not expired, return
   b) Check Redis cache → if found, return
   c) Call Model Management API (view_service) with forwarded auth headers
   d) Extract endpoint and model name from response
   e) Create TritonClient for that endpoint
   f) Cache in memory and Redis
   ↓
5. Send inference request to dynamically resolved Triton endpoint
   ↓
6. Return response to client
```

### Caching Strategy

**Three-layer cache**:
1. **In-memory** (per instance): `_service_info_cache`, `_service_registry_cache`, `_triton_clients`
2. **Redis** (shared): `tts:triton:registry:{serviceId}`
3. **Model Management Client cache**: `model_mgmt:service:{serviceId}`

**Cache TTL**:
- Controlled by `TRITON_ENDPOINT_CACHE_TTL` and `MODEL_MANAGEMENT_CACHE_TTL`
- Default: 300 seconds (5 minutes)

**Cache Invalidation**:
- Call `TTSService.invalidate_cache(service_id)` to force refresh
- Clears all cache layers for a specific service

### Fallback Behavior

If Model Management Service is unavailable or returns an error:
1. TTS service logs a warning
2. Falls back to `default_triton_client` (created from `TRITON_ENDPOINT` env var)
3. Uses default model name "tts" instead of dynamically resolved name
4. Service continues to function with static configuration

## Authentication Flow

**Auth Header Forwarding**:
1. Client sends request with `Authorization` or `X-API-Key` header
2. `extract_auth_headers()` extracts these headers
3. Headers are forwarded to Model Management Service
4. Model Management validates the auth and returns service metadata
5. No service-side credentials are injected; auth is pass-through only

**X-Auth-Source Header**:
- Automatically set by `ModelManagementClient._get_headers()`:
  - `AUTH_TOKEN` if Authorization header present
  - `API_KEY` if X-API-Key header present

## Environment Variables

### Required (Recommended)
- `MODEL_MANAGEMENT_SERVICE_URL`: Model Management Service base URL
- `REDIS_HOST`, `REDIS_PORT`, `REDIS_PASSWORD`: For distributed caching

### Optional
- `MODEL_MANAGEMENT_CACHE_TTL`: Cache TTL in seconds (default: 300)
- `TRITON_ENDPOINT_CACHE_TTL`: Triton registry cache TTL (default: 300)
- `TRITON_ENDPOINT`: Fallback Triton endpoint (only used if Model Management unavailable)
- `TRITON_API_KEY`: API key for Triton endpoint (if required)

## Testing Checklist

### Basic Functionality
- [ ] TTS service starts successfully with Model Management integration
- [ ] Inference requests resolve endpoint dynamically from Model Management
- [ ] Model name is extracted from service metadata (not hardcoded)
- [ ] Auth headers are forwarded correctly to Model Management

### Caching
- [ ] First request fetches from Model Management API
- [ ] Subsequent requests use cached data (check logs for cache hits)
- [ ] Cache expires after configured TTL
- [ ] Redis cache is shared across multiple service instances

### Fallback Behavior
- [ ] Service continues to work if Model Management is down (using TRITON_ENDPOINT)
- [ ] Service logs appropriate warnings when falling back
- [ ] Default model name "tts" is used when Model Management unavailable

### Cache Invalidation
- [ ] `invalidate_cache(service_id)` clears all cache layers
- [ ] Next request fetches fresh data from Model Management

### Authentication
- [ ] Requests with valid Authorization header succeed
- [ ] Requests with valid X-API-Key header succeed
- [ ] Requests without auth headers fail appropriately
- [ ] Model Management 401 errors are logged clearly

## Migration Notes

### For Existing Deployments
1. Add new environment variables to deployment configs:
   - `MODEL_MANAGEMENT_SERVICE_URL`
   - `MODEL_MANAGEMENT_CACHE_TTL` (optional)
   - `TRITON_ENDPOINT_CACHE_TTL` (optional)

2. Keep existing `TRITON_ENDPOINT` as fallback (recommended for safety)

3. No changes required to client code or API contracts

### For New Deployments
1. Set `MODEL_MANAGEMENT_SERVICE_URL` (required)
2. Optionally set cache TTLs
3. `TRITON_ENDPOINT` can be omitted if Model Management is reliable

## Benefits

1. **Dynamic Endpoint Resolution**: Triton endpoints can be changed in Model Management without restarting TTS service
2. **Model Name Resolution**: Model names are discovered from metadata, not hardcoded
3. **Auth Forwarding**: User authentication flows through to Model Management
4. **Multi-layer Caching**: Efficient with minimal latency overhead
5. **Graceful Degradation**: Falls back to static config if Model Management unavailable
6. **Consistency**: Same pattern as NMT service for maintainability

## Known Limitations

1. Cache invalidation requires explicit API call (no automatic invalidation)
2. Linting warnings about cognitive complexity (inherited from NMT pattern)
3. Requires Redis for optimal performance (works without but less efficient)

## References

- Implementation Guide: `docs/MODEL_MANAGEMENT_INTEGRATION_GUIDE.md`
- NMT Service Implementation: `services/nmt-service/`
- Model Management API: `services/model-management-service/routers/router_details.py`
