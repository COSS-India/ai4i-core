# Model Management Integration for Transliteration Service

## Overview

The transliteration service now integrates with the **Model Management Service** to dynamically fetch service and model information from the database instead of using hardcoded values. This provides:

- **Dynamic Configuration**: Service endpoints and model configurations are fetched at runtime from the model management service
- **Centralized Management**: All model and service metadata is stored in a central database
- **Caching**: Service information is cached (Redis + in-memory) for performance
- **Fallback Support**: Graceful fallback to hardcoded values if model management service is unavailable

## Architecture

### Components

1. **ModelManagementClient** (`utils/model_management_client.py`)
   - HTTP client for communicating with model management service
   - Handles caching (Redis + in-memory)
   - Forwards authentication headers from incoming requests
   - Extracts Triton endpoint and model information from service metadata

2. **TransliterationService** (`services/transliteration_service.py`)
   - Updated to use ModelManagementClient
   - Dynamically fetches service registry entries (endpoint, model_name)
   - Falls back to hardcoded `FALLBACK_SERVICE_REGISTRY` if needed
   - Caches service info and registry entries per service

3. **Auth Utils** (`utils/auth_utils.py`)
   - Helper functions to extract authentication headers from FastAPI requests
   - Forwards Authorization, X-API-Key, and X-Auth-Source headers

4. **Inference Router** (`routers/inference_router.py`)
   - Updated to inject ModelManagementClient into service
   - Extracts and passes auth headers to service methods

5. **Main Application** (`main.py`)
   - Initializes ModelManagementClient on startup
   - Stores client in app.state for dependency injection
   - Closes client on shutdown

## Configuration

### Environment Variables

Add these environment variables to your `.env` file or environment:

```bash
# Model Management Service URL
MODEL_MANAGEMENT_SERVICE_URL=http://model-management-service:8091

# Cache TTL for service endpoint lookups (in seconds)
TRANSLITERATION_ENDPOINT_CACHE_TTL=300

# Existing variables (still needed for fallback)
TRITON_ENDPOINT=65.1.35.3:8200
TRITON_API_KEY=your_api_key
```

### Docker Compose

If using Docker Compose, ensure the transliteration service can reach the model management service:

```yaml
transliteration-service:
  environment:
    - MODEL_MANAGEMENT_SERVICE_URL=http://model-management-service:8091
    - TRANSLITERATION_ENDPOINT_CACHE_TTL=300
  depends_on:
    - model-management-service
```

## How It Works

### Service Lookup Flow

1. **Incoming Request**: Client sends transliteration request with `serviceId`
   ```json
   {
     "input": [{"source": "namaste"}],
     "config": {
       "serviceId": "ai4bharat/indicxlit",
       "language": {
         "sourceLanguage": "en",
         "targetLanguage": "hi"
       }
     }
   }
   ```

2. **Auth Header Extraction**: The inference router extracts authentication headers (Authorization, X-API-Key) from the incoming request

3. **Service Info Fetch**: TransliterationService calls ModelManagementClient to fetch service info
   - First checks in-memory cache (expires after TRANSLITERATION_ENDPOINT_CACHE_TTL)
   - Then checks Redis cache (if available)
   - Finally, makes HTTP call to model management service: `POST /services/details/view_service`
   - Auth headers from incoming request are forwarded to model management service

4. **Service Metadata Extraction**: From the service info response:
   - Extract `endpoint` (Triton server URL)
   - Extract `triton_model` name from service or model metadata
   - Cache the results

5. **Triton Client Creation**: Create or retrieve Triton client for the specific endpoint

6. **Inference**: Execute transliteration using the dynamically configured Triton client

7. **Fallback**: If model management service is unavailable or service not found:
   - Falls back to hardcoded `FALLBACK_SERVICE_REGISTRY` in TransliterationService
   - Logs warnings but continues processing

### Caching Strategy

**Three-tier caching:**

1. **In-Memory Cache** (fastest):
   - Service info cache: `_service_info_cache[service_id] = (ServiceInfo, expires_at)`
   - Service registry cache: `_service_registry_cache[service_id] = (endpoint, model_name, expires_at)`
   - TTL: TRANSLITERATION_ENDPOINT_CACHE_TTL (default 300 seconds)

2. **Redis Cache** (shared across instances):
   - Key: `model_mgmt:service:{service_id}`
   - TTL: TRANSLITERATION_ENDPOINT_CACHE_TTL
   - JSON-serialized ServiceInfo

3. **Model Management Database** (source of truth):
   - PostgreSQL database with services and models tables
   - Accessed via model management service REST API

## Data Flow

```
┌─────────────────┐
│  Client Request │
│  (with Auth)    │
└────────┬────────┘
         │
         ▼
┌─────────────────────────────────────────────┐
│  Inference Router                           │
│  - Extract auth headers (Authorization,     │
│    X-API-Key, X-Auth-Source)                │
└────────┬────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────┐
│  TransliterationService                     │
│  - get_model_name(service_id, auth_headers) │
│  - get_triton_client(service_id, headers)   │
└────────┬────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────┐
│  Check Service Registry Cache               │
│  (in-memory, expires after TTL)             │
└────────┬────────────────────────────────────┘
         │ Cache Miss
         ▼
┌─────────────────────────────────────────────┐
│  ModelManagementClient                      │
│  - get_service(service_id, auth_headers)    │
└────────┬────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────┐
│  Check Redis Cache                          │
│  Key: model_mgmt:service:{service_id}       │
└────────┬────────────────────────────────────┘
         │ Cache Miss
         ▼
┌─────────────────────────────────────────────┐
│  HTTP Request to Model Management Service   │
│  POST /services/details/view_service        │
│  Headers: Authorization, X-API-Key, etc.    │
└────────┬────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────┐
│  Model Management Service                   │
│  - Authenticate request                     │
│  - Fetch from PostgreSQL DB                 │
│  - Return ServiceViewResponse with model    │
└────────┬────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────┐
│  Cache Result (Redis + Memory)              │
│  Extract endpoint & model name              │
└────────┬────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────┐
│  Create/Get Triton Client for Endpoint      │
└────────┬────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────┐
│  Execute Inference on Triton Server         │
└─────────────────────────────────────────────┘
```

## Registering Services in Model Management

To use a new transliteration service, you must first register it in the model management service:

### Step 1: Register the Model

```bash
POST /api/v1/model-management/models
Content-Type: application/json
Authorization: Bearer <token>

{
  "modelId": "ai4bharat/indicxlit-v2",
  "name": "IndicXlit v2",
  "version": "2.0.0",
  "description": "IndicXlit model v2 for Indic language transliteration",
  "task": {
    "type": "transliteration"
  },
  "languages": [
    {
      "sourceLanguage": "en",
      "targetLanguage": "hi"
    },
    {
      "sourceLanguage": "en",
      "targetLanguage": "ta"
    }
  ],
  "domain": ["general"],
  "license": "MIT",
  "inferenceEndPoint": {
    "modelName": "transliteration"
  }
}
```

### Step 2: Register the Service

```bash
POST /services/admin/create/service
Content-Type: application/json
Authorization: Bearer <token>

{
  "serviceId": "ai4bharat/indicxlit-v2",
  "name": "IndicXlit v2 Service",
  "modelId": "ai4bharat/indicxlit-v2",
  "serviceDescription": "Production transliteration service for IndicXlit v2",
  "hardwareDescription": "GPU: Tesla V100, 16GB VRAM",
  "endpoint": "13.200.133.97:8000",
  "apiKey": "your-triton-api-key",
  "healthStatus": {
    "status": "healthy"
  }
}
```

### Step 3: Use the Service

Now you can reference the service in transliteration requests:

```bash
POST /api/v1/transliteration/inference
Content-Type: application/json
Authorization: Bearer <token>

{
  "input": [{"source": "namaste"}],
  "config": {
    "serviceId": "ai4bharat/indicxlit-v2",
    "language": {
      "sourceLanguage": "en",
      "targetLanguage": "hi"
    },
    "isSentence": false,
    "numSuggestions": 0
  }
}
```

## Fallback Behavior

The service maintains backward compatibility with hardcoded configuration:

### Fallback Registry

Located in `TransliterationService.FALLBACK_SERVICE_REGISTRY`:

```python
FALLBACK_SERVICE_REGISTRY = {
    "ai4bharat/indicxlit": ("65.1.35.3:8200", "transliteration"),
    "ai4bharat-transliteration": ("65.1.35.3:8200", "transliteration"),
    "indicxlit": ("65.1.35.3:8200", "transliteration"),
    "default": ("65.1.35.3:8200", "transliteration")
}
```

### Fallback Scenarios

1. **Model Management Service Unavailable**:
   - Client initialization fails → logs warning, continues with fallback
   - HTTP request fails → logs warning, uses fallback registry

2. **Service Not Found**:
   - Service ID not in model management → checks fallback registry
   - Not in fallback registry → uses "default" entry
   - No "default" → uses default Triton client from environment

3. **Authentication Failure**:
   - 401 error from model management → logs detailed error, uses fallback

## Monitoring and Logging

### Log Messages

**Success Cases:**
```
INFO: Fetching service info for ai4bharat/indicxlit from model management service
INFO: Successfully fetched and cached service info for ai4bharat/indicxlit
INFO: Extracted Triton metadata for ai4bharat/indicxlit: endpoint=13.200.133.97:8000, model_name=transliteration
INFO: Using Triton endpoint: 13.200.133.97:8000, model: transliteration for service: ai4bharat/indicxlit
```

**Cache Hits:**
```
DEBUG: Service info cache hit for ai4bharat/indicxlit
DEBUG: Service registry cache hit for ai4bharat/indicxlit
DEBUG: Cache hit for service ai4bharat/indicxlit (Redis)
```

**Fallback Cases:**
```
WARNING: Failed to fetch service info for ai4bharat/indicxlit from model management service: <error>. Will use fallback registry or default Triton client.
WARNING: Service ai4bharat/indicxlit not found, using default fallback: ('65.1.35.3:8200', 'transliteration')
INFO: Using default Triton client for service ai4bharat/indicxlit
```

**Errors:**
```
ERROR: Authentication failed (401) when fetching service ai4bharat/indicxlit from model management service. Please ensure the request includes valid Authorization or X-API-Key headers.
ERROR: HTTP error fetching service ai4bharat/indicxlit: 500 - Internal Server Error
```

## Testing

### Test with Model Management Integration

```bash
# Ensure model management service is running
curl http://model-management-service:8091/health

# Test transliteration with registered service
curl -X POST http://transliteration-service:8090/api/v1/transliteration/inference \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <your-token>" \
  -d '{
    "input": [{"source": "namaste"}],
    "config": {
      "serviceId": "ai4bharat/indicxlit",
      "language": {
        "sourceLanguage": "en",
        "targetLanguage": "hi"
      },
      "isSentence": false,
      "numSuggestions": 0
    }
  }'
```

### Test Fallback Behavior

```bash
# Stop model management service
docker-compose stop model-management-service

# Test transliteration (should use fallback)
curl -X POST http://transliteration-service:8090/api/v1/transliteration/inference \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <your-token>" \
  -d '{
    "input": [{"source": "namaste"}],
    "config": {
      "serviceId": "ai4bharat/indicxlit",
      "language": {
        "sourceLanguage": "en",
        "targetLanguage": "hi"
      }
    }
  }'

# Check logs for fallback messages
docker-compose logs transliteration-service | grep -i fallback
```

## Troubleshooting

### Issue: "No authentication headers will be sent to model management service"

**Cause**: Incoming request doesn't include Authorization or X-API-Key headers

**Solution**: Ensure clients include authentication:
```bash
curl -H "Authorization: Bearer <token>" ...
# or
curl -H "X-API-Key: <api-key>" ...
```

### Issue: "Service X not found in model management service"

**Cause**: Service not registered in model management database

**Solution**: Register the service via model management API (see "Registering Services" section)

### Issue: "Failed to fetch service info... Connection refused"

**Cause**: Model management service not reachable

**Solution**:
1. Check if model management service is running: `docker-compose ps model-management-service`
2. Verify network connectivity: `docker-compose exec transliteration-service ping model-management-service`
3. Check MODEL_MANAGEMENT_SERVICE_URL environment variable

### Issue: Service always uses fallback registry

**Cause**: Multiple possibilities:
1. Model management client not initialized
2. Service not found in database
3. Authentication failure

**Solution**:
1. Check logs during startup: `grep "Model Management Client" <logs>`
2. Verify service exists: `GET /services/details/list_services`
3. Test with proper authentication headers

## Performance Considerations

### Cache Hit Rates

Monitor cache hit rates to tune TRANSLITERATION_ENDPOINT_CACHE_TTL:

- **High hit rate** (>90%): Service lookup is efficient, consider increasing TTL
- **Low hit rate** (<50%): Services change frequently, or TTL too short

### Redis vs In-Memory Cache

- **In-Memory**: Fastest, but not shared across service instances
- **Redis**: Shared cache, reduces load on model management service
- **Recommendation**: Use Redis in production for distributed caching

### Model Management Service Load

Each cache miss triggers HTTP request to model management service:

- **Without cache**: ~1000 requests/sec (for 1000 transliteration requests/sec)
- **With cache (300s TTL)**: ~0.003 requests/sec (1 request per 5 minutes per service)
- **Reduction**: 99.9997% reduction in load

## Migration Guide

### Migrating from Hardcoded Registry

If you have existing hardcoded service mappings:

1. **Identify all service IDs** in use (check logs, config files, client code)

2. **Register models and services** in model management database

3. **Update environment variables**:
   ```bash
   MODEL_MANAGEMENT_SERVICE_URL=http://model-management-service:8091
   TRANSLITERATION_ENDPOINT_CACHE_TTL=300
   ```

4. **Keep fallback registry** for transition period (already done in code)

5. **Monitor logs** for fallback usage:
   ```bash
   docker-compose logs -f transliteration-service | grep -i "fallback\|model management"
   ```

6. **Remove fallback entries** after confirming all services are registered and working

## Summary

✅ **Completed Integration:**
- ModelManagementClient created and integrated
- TransliterationService updated to use dynamic service lookup
- Authentication headers properly forwarded
- Caching implemented (Redis + in-memory)
- Fallback support maintained
- Comprehensive logging added

✅ **Benefits:**
- Dynamic service configuration from database
- Centralized model and service management
- Reduced hardcoded dependencies
- Better scalability and maintainability
- Graceful degradation when model management unavailable

✅ **Next Steps:**
1. Test the integration in your environment
2. Register your transliteration services in model management
3. Monitor logs and cache hit rates
4. Tune TRANSLITERATION_ENDPOINT_CACHE_TTL based on usage patterns

