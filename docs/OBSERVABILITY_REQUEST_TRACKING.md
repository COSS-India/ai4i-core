# How Request Tracking Works with `ai4icore_observability`

A complete, code-level walkthrough of how an inference service starts up, wires observability, handles a request, records metrics, and gets scraped by Prometheus.

There are two phases:

1. **Startup phase** (once) — `ai4icore_service_base` wires `ObservabilityMiddleware` into the FastAPI app
2. **Request phase** (per request) — the middleware captures metadata, calls the handler, records metrics, returns the response

---

# Phase 1: Startup — wiring the app

## Step 1 — The service's `main.py` is tiny

Every inference service calls `create_inference_app()` from the shared factory. Here is the entire [nmt-service/app/main.py](../services/nmt-service/app/main.py):

```python
# services/nmt-service/app/main.py
from ai4icore_service_base import create_inference_app
from app.models import Base
from app.routes import api_router

app = create_inference_app(
    service_name="nmt-service",
    title="NMT Service",
    description="Neural Machine Translation microservice using Triton Inference Server.",
    version="1.0.2",
    api_prefix="/api/v1/nmt",
    router=api_router,
    db_base=Base,
)
```

That's it. All cross-cutting concerns (observability, tracing, auth, CORS, rate limiting, DB, Redis, service registry) are wired inside `create_inference_app()`.

## Step 2 — `create_inference_app()` constructs the FastAPI app

In [libs/ai4icore_service_base/.../app_factory.py:275-324](../libs/ai4icore_service_base/ai4icore_service_base/app_factory.py#L275-L324):

```python
def create_inference_app(*, service_name, title, description, version,
                         api_prefix, router, db_base, extra_state=None,
                         observability_app="", cors_origins=None) -> FastAPI:
    config = InferenceServiceConfig(
        service_name=service_name,                                # "nmt-service"
        title=title,
        ...
        observability_app=observability_app or service_name.replace("-service", ""),  # "nmt"
    )

    application = FastAPI(
        title=config.title,
        version=config.version,
        description=config.description,
        lifespan=_build_lifespan(config, db_base),
    )
```

## Step 3 — Observability plugin is registered on the app

Immediately after the FastAPI app is created, at [app_factory.py:326-334](../libs/ai4icore_service_base/ai4icore_service_base/app_factory.py#L326-L334):

```python
    # ── Observability ──
    if _OBSERVABILITY:
        try:
            obs_config = PluginConfig.from_env()
            obs_config.enabled = True
            obs_config.apps = obs_config.apps or [config.observability_app]  # ["nmt"]
            ObservabilityPlugin(obs_config).register_plugin(application)
        except Exception as e:
            logger.warning("Observability plugin failed: %s", e)
```

## Step 4 — `ObservabilityPlugin.register_plugin()` adds middleware + endpoint

In [libs/ai4icore_observability/.../plugin.py:73-89](../libs/ai4icore_observability/ai4icore_observability/plugin.py#L73-L89):

```python
def register_plugin(self, app: FastAPI) -> None:
    if not self.config.enabled:
        return
    self.register_middleware(app)      # adds ObservabilityMiddleware
    self.register_endpoints(app)       # mounts /enterprise/metrics
    self._initialize_customer_quotas()
    self._initialized = True
```

### 4a. `register_middleware()` — inserts the middleware ([plugin.py:24-34](../libs/ai4icore_observability/ai4icore_observability/plugin.py#L24-L34)):

```python
def register_middleware(self, app: FastAPI) -> None:
    app.add_middleware(
        ObservabilityMiddleware,
        metrics_collector=self.metrics,    # shared MetricsCollector instance
        config=self.config,
    )
```

### 4b. `register_endpoints()` — mounts `/enterprise/metrics` ([plugin.py:45-51](../libs/ai4icore_observability/ai4icore_observability/plugin.py#L45-L51)):

```python
@app.get(self.config.metrics_path)     # "/enterprise/metrics"
async def metrics_endpoint():
    return Response(
        content=self.metrics.get_metrics_text(),
        media_type="text/plain",
    )
```

At this point:
- Every future request will pass through `ObservabilityMiddleware`
- Prometheus can now scrape `GET /enterprise/metrics`
- `ai4icore_service_base` has finished its job — it won't run again per request

---

# Phase 2: Request — tracking a live request

## Incoming request

```http
POST /api/v1/nmt/inference HTTP/1.1
Host: nmt-service:8089
Authorization: Bearer eyJhbGci...
Content-Type: application/json

{
  "controlConfig": {},
  "config": {"serviceId": "nmt-model-v2"},
  "input": [{"source": "Hello world"}, {"source": "How are you?"}]
}
```

## Step 5 — Middleware entry

[middleware.py:102-112](../libs/ai4icore_observability/ai4icore_observability/middleware.py#L102-L112):

```python
async def dispatch(self, request: Request, call_next):
    if not self.config.enabled:
        return await call_next(request)

    start_time = time.time()                    # e.g. 1776401234.123

    path = request.url.path                     # "/api/v1/nmt/inference"
    method = request.method                     # "POST"
    headers = request.headers
```

## Step 6 — Resolve tenant and organization

[middleware.py:114-129](../libs/ai4icore_observability/ai4icore_observability/middleware.py#L114-L129):

```python
    # Priority 1 & 2: X-Customer-ID header or JWT 'name' claim
    organization, app = self._extract_customer_app(request)
    # organization = None, app = "nmt"

    # Resolve tenant_id AND organization_name from multi-tenant service
    tenant_id, tenant_org_name = await self._extract_tenant_info(request)
    # tenant_id = "cloudsphere-analytics-2-fe7854"
    # tenant_org_name = "CloudSphere Analytics-2"  (LRU cached, no network hit after first call)

    # Priority 3: fallback to tenant's organization name
    if organization is None:
        organization = tenant_org_name          # "CloudSphere Analytics-2"

    organization_label = organization if organization else "unknown"
    tenant = str(tenant_id) if tenant_id else "unknown"
```

## Step 7 — Store resolved values on `request.state`

[middleware.py:132-134](../libs/ai4icore_observability/ai4icore_observability/middleware.py#L132-L134):

```python
    # Available to all downstream middlewares and handlers
    request.state.organization = organization_label   # "CloudSphere Analytics-2"
    request.state.tenant_id = tenant_id               # "cloudsphere-analytics-2-fe7854"
```

## Step 8 — Detect service type and extract business metrics from body

[middleware.py:199, 216-233](../libs/ai4icore_observability/ai4icore_observability/middleware.py#L199):

```python
    service_type = self._detect_service_type(path)    # path contains "/nmt" → "translation"

    if method == "POST" and service_type in ["tts", "translation", "asr", "ocr", ...]:
        body_bytes = await request.body()             # reads the JSON body
        # ...
        elif service_type == "translation":
            translation_characters = self._extract_translation_characters_from_body(body_bytes)
            # Sums len("Hello world") + len("How are you?") = 11 + 12 = 23
```

## Step 9 — Run the actual route handler

[middleware.py:262](../libs/ai4icore_observability/ai4icore_observability/middleware.py#L262):

```python
    response = await call_next(request)
    # The NMT route handler runs: calls Triton, returns the translation
    # response.status_code = 200
```

## Step 10 — Compute duration, read `service_id`, call `track_request`

[middleware.py:264-288](../libs/ai4icore_observability/ai4icore_observability/middleware.py#L264-L288):

```python
    service_id = getattr(request.state, "service_id", "") or ""
    # "d77e6d6ab2e2626c6c54567f065fdbc7"  (set by model-management middleware)

    duration = time.time() - start_time              # e.g. 0.324 seconds

    self.metrics_collector.track_request(
        organization=organization_label,              # "CloudSphere Analytics-2"
        app=app,                                      # "nmt"
        method=method,                                # "POST"
        endpoint=path,                                # "/api/v1/nmt/inference"
        status_code=response.status_code,             # 200
        duration=duration,                            # 0.324
        service_type=service_type,                    # "translation"
        tenant=tenant,                                # "cloudsphere-analytics-2-fe7854"
        service_id=service_id,                        # "d77e6d6ab2e2626c6c54567f065fdbc7"
    )

    self._track_additional_metrics(
        organization_label, app, tenant, service_type, path, duration,
        tts_characters=0, translation_characters=23, ...,
        service_id=service_id,
    )
```

## Step 11 — `track_request` increments Prometheus metrics

[metrics.py:547-583](../libs/ai4icore_observability/ai4icore_observability/metrics.py#L547-L583):

```python
    self.enterprise_requests_total.labels(
        organization="CloudSphere Analytics-2",
        app="nmt",
        method="POST",
        endpoint="/api/v1/nmt/inference",
        status_code="200",
        tenant="cloudsphere-analytics-2-fe7854",
        service_id="d77e6d6ab2e2626c6c54567f065fdbc7",
    ).inc()                                           # counter += 1

    self.enterprise_request_duration.labels(...).observe(0.324)
    # histogram records 0.324 → falls into the 0.5s bucket

    # status_code < 400, so enterprise_errors_total is NOT incremented
```

`_track_additional_metrics` then records the NMT-specific histogram:

```python
    self.enterprise_nmt_characters_translated.labels(
        organization="CloudSphere Analytics-2",
        app="nmt",
        source_language="en",
        target_language="hi",
        tenant="cloudsphere-analytics-2-fe7854",
        service_id="d77e6d6ab2e2626c6c54567f065fdbc7",
    ).observe(23)
```

## Step 12 — Response goes back to the client

[middleware.py:295](../libs/ai4icore_observability/ai4icore_observability/middleware.py#L295):

```python
    return response
```

---

# Phase 3: Scraping — Prometheus reads the metrics

## Step 13 — Prometheus scrapes `/enterprise/metrics` every 5 seconds

Configured in [infrastructure/prometheus/prometheus.yml](../infrastructure/prometheus/prometheus.yml):

```yaml
- job_name: "ai4icore-enterprise"
  scrape_interval: 5s
  metrics_path: /enterprise/metrics
  static_configs:
    - targets:
        - "nmt-service:8089"
        - "asr-service:8087"
        - ... (all services)
```

Prometheus runs the equivalent of:

```
GET http://nmt-service:8089/enterprise/metrics
```

## Step 14 — The metrics endpoint serves Prometheus text format

From Step 4b's registered handler ([plugin.py:46-51](../libs/ai4icore_observability/ai4icore_observability/plugin.py#L46-L51)):

```python
async def metrics_endpoint():
    return Response(
        content=self.metrics.get_metrics_text(),   # generate_latest(registry).decode("utf-8")
        media_type="text/plain",
    )
```

The response body looks like:

```
# HELP telemetry_obsv_requests_total Total enterprise requests
# TYPE telemetry_obsv_requests_total counter
telemetry_obsv_requests_total{organization="CloudSphere Analytics-2",app="nmt",method="POST",endpoint="/api/v1/nmt/inference",status_code="200",tenant="cloudsphere-analytics-2-fe7854",service_id="d77e6d6ab2e2626c6c54567f065fdbc7"} 1

# HELP telemetry_obsv_request_duration_seconds Enterprise request duration
# TYPE telemetry_obsv_request_duration_seconds histogram
telemetry_obsv_request_duration_seconds_bucket{...,le="0.25"} 0
telemetry_obsv_request_duration_seconds_bucket{...,le="0.5"} 1
telemetry_obsv_request_duration_seconds_bucket{...,le="1.0"} 1
telemetry_obsv_request_duration_seconds_bucket{...,le="+Inf"} 1
telemetry_obsv_request_duration_seconds_sum{...} 0.324
telemetry_obsv_request_duration_seconds_count{...} 1
```

## Step 15 — Metrics are now queryable

Stored in Prometheus TSDB with 30-day retention. Example query for P99 latency of the specific model:

```promql
histogram_quantile(0.99, sum by (le) (
  rate(telemetry_obsv_request_duration_seconds_bucket{
    service_id="d77e6d6ab2e2626c6c54567f065fdbc7"
  }[5m])
))
```

Consumed downstream by Grafana dashboards, Alertmanager rules, and the Prometheus HTTP API.

---

# Quick mental model

```
┌─────────────────────── STARTUP (once) ───────────────────────┐
│                                                              │
│  nmt-service/main.py                                         │
│      │                                                       │
│      ▼                                                       │
│  create_inference_app()   ◄── ai4icore_service_base          │
│      │                                                       │
│      ▼                                                       │
│  FastAPI() created                                           │
│      │                                                       │
│      ▼                                                       │
│  ObservabilityPlugin(...).register_plugin(app)               │
│      │         ◄── ai4icore_observability                    │
│      ├─► app.add_middleware(ObservabilityMiddleware, ...)    │
│      └─► @app.get("/enterprise/metrics")                     │
│                                                              │
└──────────────────────────────────────────────────────────────┘

┌──────────── PER REQUEST (every inference call) ──────────────┐
│                                                              │
│  POST /api/v1/nmt/inference                                  │
│      │                                                       │
│      ▼                                                       │
│  ObservabilityMiddleware.dispatch()                          │
│    • start_time = time.time()                                │
│    • resolve tenant / organization                           │
│    • request.state.tenant_id = ...                           │
│    • extract translation_characters from body                │
│      │                                                       │
│      ▼                                                       │
│  response = await call_next(request)  # NMT handler runs     │
│      │                                                       │
│      ▼                                                       │
│  ObservabilityMiddleware (after)                             │
│    • duration = time.time() - start_time                     │
│    • service_id = request.state.service_id                   │
│    • metrics_collector.track_request(...)                    │
│    • metrics_collector._track_additional_metrics(...)        │
│      │                                                       │
│      ▼                                                       │
│  return response   ─────────► client                         │
│                                                              │
└──────────────────────────────────────────────────────────────┘

┌─────────── SCRAPE (every 5s, independent) ───────────────────┐
│                                                              │
│  Prometheus ──GET──► /enterprise/metrics                     │
│                          │                                   │
│                          ▼                                   │
│                    generate_latest(registry)                 │
│                          │                                   │
│                          ▼                                   │
│                    Prometheus TSDB                           │
│                          │                                   │
│            ┌─────────────┼─────────────┐                     │
│            ▼             ▼             ▼                     │
│        Grafana      Alertmanager   HTTP API                  │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

---

# Key things to remember

- **`ai4icore_service_base` runs only at startup.** It calls `ObservabilityPlugin(config).register_plugin(app)` once, then steps out. It never runs per request.
- **`ai4icore_observability` owns the hot path.** The `ObservabilityMiddleware` (added in Step 4a) and the `/enterprise/metrics` endpoint (added in Step 4b) handle all per-request work and all scrape requests.
- **Zero code changes** are needed in service handlers — the middleware does everything.
- **Metrics live in-memory** per service instance. If a container restarts, counters reset. Prometheus handles this correctly via `rate()`.
- **Each service has its own `CollectorRegistry`.** Services don't share state; Prometheus scrapes them independently and aggregates at query time.
- **Tenant/organization resolution is cached** (5-min TTL LRU) so it doesn't add latency on every request.
- **Business metrics** (characters, tokens, audio seconds) come from peeking into request bodies, which is why they're service-type-aware.
