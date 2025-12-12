## Model Management Integration Guide

### Goal
Remove per-service hardcoding (Triton endpoint, Triton model name, language/script rules) and instead resolve **deployment-specific inference details dynamically** from the **Model Management Service**.

This document explains the exact implementation currently used by **`services/nmt-service`**, and how any other microservice can replicate it with minimal changes.

---

## What was removed / de-hardcoded in NMT

### 1) Triton endpoint is no longer hardcoded
- **Before**: A fixed `TRITON_ENDPOINT` (env/config) was effectively the only way to pick a Triton server.
- **Now**: NMT resolves the Triton endpoint at request-time using **Model Management Service** based on `serviceId` in the inference request.
- **Fallback**: `TRITON_ENDPOINT` is still supported **only as a fallback** if Model Management resolution fails or is unavailable.

Where:
- `services/nmt-service/services/nmt_service.py` → `NMTService.get_triton_client()`
- `services/nmt-service/routers/inference_router.py` → constructs the service with a default client only if `app.state.triton_endpoint` is set.

### 2) Triton model name is no longer hardcoded (or tied to task type)
- **Before**: code commonly defaults to a task label like `"nmt"` or a fixed model name.
- **Now**: NMT derives the model name dynamically:
  1. Prefer `model.inferenceEndPoint.{model_name|modelName|model}` returned by Model Management.
  2. Else fall back to a `serviceId` parsing heuristic: `org/model--variant` → `model`.
  3. Else return the `serviceId` (last-resort), rather than a misleading task type.

Where:
- `services/nmt-service/services/nmt_service.py` → `NMTService.get_model_name()` and `_extract_triton_metadata()`

### 3) Script-code “auto append” was removed
NMT now **only appends script codes when explicitly provided in the request** (`sourceScriptCode`, `targetScriptCode`). Automatic mapping-based appending was removed because Triton models may not expect it.

Where:
- `services/nmt-service/services/nmt_service.py` → in `run_inference()` around language handling

---

## Model Management APIs used

NMT uses the following endpoints from the **Model Management Service**:

### 1) View service (authoritative for endpoint + embedded model metadata)
- **Endpoint**: `POST /services/details/view_service`
- **Payload**:
  - `{ "serviceId": "<service-id>" }`
- **Expected fields used by NMT**:
  - `endpoint` (the Triton inference server location)
  - `model.inferenceEndPoint` (optional dict; may contain model name)
  - `model.name` (optional)

Where:
- Model Mgmt router: `services/model-management-service/routers/router_details.py` (`view_service`)
- Client usage: `services/nmt-service/utils/model_management_client.py` → `get_service()`

### 2) List services (optional, mainly for UIs / selection)
- **Endpoint**: `GET /services/details/list_services?task_type=<optional>`

Where:
- Model Mgmt router: `services/model-management-service/routers/router_details.py` (`list_services`)
- Client usage: `services/nmt-service/utils/model_management_client.py` → `list_services()`

---

## End-to-end runtime flow (NMT)

### Step A — API receives inference request
- Endpoint: `POST /api/v1/nmt/inference`
- NMT extracts auth headers from the incoming request.

Where:
- `services/nmt-service/routers/inference_router.py`:
  - `auth_headers = extract_auth_headers(http_request)`
  - passes `auth_headers` into `nmt_service.run_inference(...)`

### Step B — Resolve model name and Triton endpoint dynamically
Inside `NMTService.run_inference()`:
1. Read `service_id = request.config.serviceId`
2. Resolve model name:
   - `model_name = await self.get_model_name(service_id, auth_headers)`
3. Resolve Triton client:
   - `triton_client = await self.get_triton_client(service_id, auth_headers)`

Where:
- `services/nmt-service/services/nmt_service.py`

### Step C — Call Model Management service (with caching)
`NMTService` calls `ModelManagementClient.get_service(service_id, ...)`.

Caching layers:
- **In-memory cache** (per instance):
  - `_service_info_cache`, `_service_registry_cache`, `_triton_clients`
- **Redis cache** (shared across instances):
  - key: `nmt:triton:registry:{serviceId}` → `{ endpoint, model_name }`
- **Model Management client cache** (optional Redis + memory):
  - key: `model_mgmt:service:{serviceId}`

TTL:
- Controlled by `TRITON_ENDPOINT_CACHE_TTL` / `MODEL_MANAGEMENT_CACHE_TTL` (defaults 300 seconds).

Where:
- `services/nmt-service/services/nmt_service.py`:
  - `_get_service_registry_entry()`, `_get_registry_from_redis()`, `_set_registry_in_redis()`
- `services/nmt-service/utils/model_management_client.py`:
  - `get_service()`, `_get_cache_key()`

### Step D — Normalize endpoint for Triton client
Model Management may return `http://host:port`.
- NMT removes scheme and keeps `host:port` because `tritonclient.http.InferenceServerClient` expects that.

Where:
- `services/nmt-service/services/nmt_service.py` → `_extract_triton_metadata()`
- `services/nmt-service/utils/triton_client.py` → `TritonClient._normalize_url()`

### Step E — Forward auth headers to Model Management
NMT forwards authentication to Model Management rather than injecting service-side credentials.

1) Extract headers from incoming request:
- `Authorization`
- `X-API-Key`
- `X-Auth-Source`

Where:
- `services/nmt-service/utils/auth_utils.py` → `extract_auth_headers()`

2) ModelManagementClient builds outgoing headers:
- Forwards `Authorization`, `X-API-Key`, `X-Auth-Source` if present.
- If `Authorization` exists and `X-Auth-Source` missing → sets `X-Auth-Source=AUTH_TOKEN`.
- If only `X-API-Key` exists and `X-Auth-Source` missing → sets `X-Auth-Source=API_KEY`.

Where:
- `services/nmt-service/utils/model_management_client.py` → `_get_headers()`

---

## Cache invalidation
If endpoints move (e.g., Triton migration) you can force refresh.

Where:
- `services/nmt-service/services/nmt_service.py` → `invalidate_cache(service_id)`

What it clears:
- NMT in-memory caches for `service_id`
- Redis key `nmt:triton:registry:{serviceId}`
- (Optionally) Model Management cached key `model_mgmt:service:{serviceId}` when Redis is used

---

## How another service should implement this (copy/paste checklist)

### 1) Add a Model Management client
- Copy the pattern from: `services/nmt-service/utils/model_management_client.py`
- Configure base URL using env: `MODEL_MANAGEMENT_SERVICE_URL`

### 2) Extract and forward auth headers
- Add a small utility like: `services/nmt-service/utils/auth_utils.py`
- In your inference/router handler, extract headers and pass them down to your service layer.

### 3) Resolve endpoint + model dynamically
In your service layer:
- Add a method like:
  - `async def _get_service_registry_entry(service_id, auth_headers) -> (endpoint, model_name)`
- Use Model Management `view_service` as source of truth.
- Normalize endpoint before initializing Triton client.

### 4) Add caching (recommended)
- **Redis shared cache** for `(endpoint, model_name)` keyed by `serviceId`.
- **In-memory** caching to avoid repeated Redis + HTTP calls per instance.

### 5) Keep a fallback for dev / emergency
- Allow an optional default Triton endpoint via `TRITON_ENDPOINT`.
- Use it only when Model Management resolution fails.

### 6) Validate at runtime
- Log endpoint + model selected per request (without leaking secrets).
- Ensure Triton error messages list available models (as NMT does in `TritonClient.send_triton_request`).

---

## Required environment variables (minimum)
For any service implementing this pattern:
- `MODEL_MANAGEMENT_SERVICE_URL` (e.g. `http://model-management-service:8091`)
- `MODEL_MANAGEMENT_CACHE_TTL` (optional; default `300`)
- `TRITON_ENDPOINT_CACHE_TTL` (optional; default `300`)
- `REDIS_HOST`, `REDIS_PORT`, `REDIS_PASSWORD` (optional but recommended for shared caching)
- `TRITON_ENDPOINT` (optional fallback)
- `TRITON_API_KEY` (optional; used by Triton client if your Triton endpoint requires it)

See:
- `services/nmt-service/env.template`

---

## Quick pointers to the exact NMT implementation
- **Dynamic endpoint + model name resolution**: `services/nmt-service/services/nmt_service.py`
- **Model Management client + auth forwarding**: `services/nmt-service/utils/model_management_client.py`
- **Auth header extraction**: `services/nmt-service/utils/auth_utils.py`
- **Triton client URL normalization & inference**: `services/nmt-service/utils/triton_client.py`
- **Model Management API definitions**: `services/model-management-service/routers/router_details.py`
