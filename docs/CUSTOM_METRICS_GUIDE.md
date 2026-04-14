# Custom Metrics Guide for Adopters

This guide documents the end-to-end steps required to define, configure, and enable custom Prometheus metrics beyond the default metrics provided by the AI4I observability library.

---

## 1. Prerequisites

Before creating custom metrics, ensure the following:

| Requirement | How to verify |
|---|---|
| `ai4icore-observability` library installed | `pip show ai4icore-observability` (v1.0.9+) |
| `prometheus-client` available | Included as a dependency of the observability library |
| Observability plugin enabled on your service | `OBSERVE_UTIL_ENABLED=true` in your environment |
| Prometheus scraping your service | Your service is listed in `infrastructure/prometheus/prometheus.yml` |

### Default metrics (already provided)

The observability middleware automatically tracks these without any code changes:

| Metric | Type | What it tracks |
|---|---|---|
| `telemetry_obsv_requests_total` | Counter | Total HTTP requests (by method, endpoint, status_code, tenant, service_id) |
| `telemetry_obsv_request_duration_seconds` | Histogram | Request latency in seconds |
| `telemetry_obsv_errors_total` | Counter | Error counts (by status_code, error_type) |
| `telemetry_obsv_service_requests_total` | Counter | Requests by service type |
| `node_cpu_seconds_total` | Counter | CPU usage (from node-exporter) |
| `node_memory_MemAvailable_bytes` | Gauge | Available memory (from node-exporter) |
| `node_filesystem_avail_bytes` | Gauge | Available disk space (from node-exporter) |

Additionally, per-service business metrics are automatically extracted from request bodies by the middleware (e.g., characters translated for NMT, audio seconds processed for ASR). See Section 7 for the full list.

---

## 2. Understanding the Architecture

```
Your Service Code
    │
    ├──► ObservabilityMiddleware (automatic: latency, errors, business metrics)
    │
    ├──► MetricsCollector (programmatic: track_*() methods)
    │
    └──► Your Custom Metrics (prometheus_client Counter/Histogram/Gauge)
            │
            ▼
    CollectorRegistry  ◄── all metrics share one registry
            │
            ▼
    GET /enterprise/metrics  ◄── Prometheus scrapes this
            │
            ▼
    Prometheus ──► Grafana / Alerts
```

All metrics — default and custom — must be registered on the same `CollectorRegistry` instance so they are exposed together at `/enterprise/metrics`.

---

## 3. Creating Custom Metrics — Step by Step

### Step 1: Access the metrics collector

The global `MetricsCollector` instance holds the shared `CollectorRegistry`. Access it in your service code:

```python
from ai4icore_observability.metrics import get_global_collector

collector = get_global_collector()
registry = collector.registry  # The shared CollectorRegistry
```

### Step 2: Define your custom metric

Use `prometheus_client` types, passing the shared `registry`:

```python
from prometheus_client import Counter, Histogram, Gauge

# Counter — tracks cumulative totals (e.g., items processed)
my_counter = Counter(
    "telemetry_custom_documents_processed_total",
    "Total documents processed by the custom pipeline",
    ["organization", "tenant", "document_type"],
    registry=registry,
)

# Histogram — tracks distributions (e.g., processing time, payload size)
my_histogram = Histogram(
    "telemetry_custom_processing_duration_seconds",
    "Time spent processing custom requests",
    ["organization", "tenant", "pipeline_stage"],
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, float("inf")),
    registry=registry,
)

# Gauge — tracks current values (e.g., queue depth, active connections)
my_gauge = Gauge(
    "telemetry_custom_queue_depth",
    "Number of items currently in the processing queue",
    ["organization", "tenant"],
    registry=registry,
)
```

### Step 3: Record metric values in your endpoint handlers

```python
from fastapi import APIRouter, Request

router = APIRouter()

@router.post("/api/v1/custom/process")
async def process_document(request: Request):
    # Extract tenant info (set by middleware on request.state)
    tenant = getattr(request.state, "tenant_id", "unknown") or "unknown"
    organization = getattr(request.state, "organization_name", "unknown") or "unknown"

    # ... your processing logic ...
    start = time.time()
    result = do_processing(document)
    duration = time.time() - start

    # Record metrics
    my_counter.labels(
        organization=organization,
        tenant=tenant,
        document_type="pdf",
    ).inc()

    my_histogram.labels(
        organization=organization,
        tenant=tenant,
        pipeline_stage="inference",
    ).observe(duration)

    my_gauge.labels(
        organization=organization,
        tenant=tenant,
    ).set(get_queue_depth())

    return result
```

### Step 4: Verify the metric is exposed

Once your service is running, check that your metric appears:

```bash
curl http://localhost:<SERVICE_PORT>/enterprise/metrics | grep telemetry_custom
```

You should see output like:

```
# HELP telemetry_custom_documents_processed_total Total documents processed by the custom pipeline
# TYPE telemetry_custom_documents_processed_total counter
telemetry_custom_documents_processed_total{document_type="pdf",organization="acme-corp",tenant="tenant-123"} 42.0
```

---

## 4. Putting It All Together — Complete Example

Here is a full example of a service that adds a custom metric alongside the default observability:

```python
# services/my-custom-service/main.py
import time
from fastapi import APIRouter, Request
from prometheus_client import Histogram

from ai4icore_service_base import create_inference_app
from ai4icore_observability.metrics import get_global_collector
from app.models import Base

# ── Define custom metric ──
collector = get_global_collector()

custom_inference_time = Histogram(
    "telemetry_custom_model_inference_seconds",
    "Time spent on model inference (excluding pre/post processing)",
    ["organization", "tenant", "model_name", "service_id"],
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, float("inf")),
    registry=collector.registry,
)

# ── Routes ──
api_router = APIRouter()

@api_router.post("/inference")
async def inference(request: Request):
    tenant = getattr(request.state, "tenant_id", "unknown") or "unknown"
    organization = getattr(request.state, "organization_name", "unknown") or "unknown"
    service_id = getattr(request.state, "service_id", "") or ""

    payload = await request.json()

    # Pre-processing
    input_data = preprocess(payload)

    # Model inference — track this separately
    start = time.time()
    result = run_model(input_data)
    inference_duration = time.time() - start

    custom_inference_time.labels(
        organization=organization,
        tenant=tenant,
        model_name="my-model-v2",
        service_id=service_id,
    ).observe(inference_duration)

    # Post-processing
    output = postprocess(result)
    return output

# ── Bootstrap ──
app = create_inference_app(
    service_name="my-custom-service",
    title="My Custom Service",
    description="Custom inference service with additional metrics.",
    api_prefix="/api/v1/custom",
    router=api_router,
    db_base=Base,
)
```

This service will automatically get all default metrics (request count, latency, errors) via the middleware, **plus** the custom `telemetry_custom_model_inference_seconds` histogram.

---

## 5. Enabling Prometheus to Scrape Your Service

If your service is new (not already in the scrape config), add it to `infrastructure/prometheus/prometheus.yml` under both scrape jobs:

```yaml
scrape_configs:
  # Job 1: Standard /metrics endpoint
  - job_name: "ai4i-services"
    metrics_path: /metrics
    static_configs:
      - targets:
          # ... existing services ...
          - "my-custom-service:8100"   # ← add your service

  # Job 2: Enterprise metrics from observability plugin
  - job_name: "ai4icore-enterprise"
    metrics_path: /enterprise/metrics
    static_configs:
      - targets:
          # ... existing services ...
          - "my-custom-service:8100"   # ← add your service
```

After updating, reload Prometheus:

```bash
# Option 1: Restart the container
docker compose restart prometheus

# Option 2: Hot reload (if --web.enable-lifecycle is enabled)
curl -X POST http://localhost:9090/-/reload
```

Verify scraping is active:

```bash
# Check target health
curl -s http://localhost:9090/api/v1/targets | python -m json.tool | grep my-custom-service
```

---

## 6. Querying Custom Metrics in Prometheus

Once scraped, your custom metrics are available via PromQL.

### Instant value

```promql
telemetry_custom_documents_processed_total{organization="acme-corp"}
```

### Rate (per second over 5 minutes)

```promql
rate(telemetry_custom_documents_processed_total[5m])
```

### Histogram percentiles

```promql
# P95 processing time
histogram_quantile(0.95,
  rate(telemetry_custom_processing_duration_seconds_bucket[5m])
)

# P95 by tenant
histogram_quantile(0.95,
  sum by (le, tenant) (
    rate(telemetry_custom_processing_duration_seconds_bucket[5m])
  )
)
```

### Average value from histogram

```promql
rate(telemetry_custom_processing_duration_seconds_sum[5m])
/
rate(telemetry_custom_processing_duration_seconds_count[5m])
```

---

## 7. Built-in Business Metrics (Automatic)

These are tracked automatically by the middleware by inspecting request/response bodies. No code changes needed if your service follows the standard API patterns.

| Metric | Service Type | What it extracts |
|---|---|---|
| `telemetry_obsv_tts_characters_synthesized` | TTS | Character count from `input[].source` |
| `telemetry_obsv_nmt_characters_translated` | NMT | Character count from `input[].source` |
| `telemetry_obsv_asr_audio_seconds_processed` | ASR | Audio duration from base64 payload |
| `telemetry_obsv_ocr_characters_processed` | OCR | Estimated from image size |
| `telemetry_obsv_ocr_image_size_kb` | OCR | Size of `imageContent` base64 payload |
| `telemetry_obsv_transliteration_characters_processed` | Transliteration | Character count from `input[].source` |
| `telemetry_obsv_language_detection_characters_processed` | Lang Detection | Character count from `input[].source` |
| `telemetry_obsv_ner_tokens_processed` | NER | Word count from `input[].source` |
| `telemetry_obsv_speaker_diarization_seconds_processed` | Speaker Diarization | Audio duration |
| `telemetry_obsv_language_diarization_seconds_processed` | Lang Diarization | Audio duration |

Service type is auto-detected from the request path (e.g., paths containing `/nmt` or `/translate` are detected as NMT).

---

## 8. Built-in Tracking Methods (Programmatic)

If the automatic middleware extraction does not cover your use case, you can call tracking methods directly on the `MetricsCollector`:

```python
from ai4icore_observability.metrics import get_global_collector

collector = get_global_collector()

# Track data processing volume
collector.track_data_processing(
    organization="acme-corp",
    app="my-app",
    data_type="custom_units",
    amount=500,
    tenant="tenant-123",
)

# Track component-level latency
collector.track_component_latency(
    organization="acme-corp",
    app="my-app",
    component="ml-inference",
    duration=0.25,
    tenant="tenant-123",
)

# Track LLM token usage
collector.track_llm_tokens(
    organization="acme-corp",
    app="my-app",
    model="gpt-4",
    tokens=1500,
    tenant="tenant-123",
)
```

Full list of available tracking methods:

| Method | Records to metric |
|---|---|
| `track_request()` | `telemetry_obsv_requests_total` + `_request_duration_seconds` |
| `track_data_processing()` | `telemetry_obsv_data_processed_total` |
| `track_llm_tokens()` | `telemetry_obsv_llm_tokens_processed_total` |
| `track_tts_characters()` | `telemetry_obsv_tts_characters_synthesized` |
| `track_nmt_characters()` | `telemetry_obsv_nmt_characters_translated` |
| `track_asr_audio_length()` | `telemetry_obsv_asr_audio_seconds_processed` |
| `track_ocr_characters()` | `telemetry_obsv_ocr_characters_processed` |
| `track_transliteration_characters()` | `telemetry_obsv_transliteration_characters_processed` |
| `track_language_detection_characters()` | `telemetry_obsv_language_detection_characters_processed` |
| `track_ner_tokens()` | `telemetry_obsv_ner_tokens_processed` |
| `track_speaker_diarization_length()` | `telemetry_obsv_speaker_diarization_seconds_processed` |
| `track_language_diarization_length()` | `telemetry_obsv_language_diarization_seconds_processed` |
| `track_component_latency()` | `telemetry_obsv_component_latency_seconds` |

---

## 9. Naming Conventions and Best Practices

### Naming

| Rule | Example |
|---|---|
| Prefix all custom metrics with `telemetry_custom_` | `telemetry_custom_documents_processed_total` |
| Use `_total` suffix for Counters | `telemetry_custom_requests_total` |
| Use `_seconds` suffix for time-based Histograms | `telemetry_custom_inference_seconds` |
| Use `_bytes` suffix for size-based metrics | `telemetry_custom_payload_bytes` |
| Use snake_case | `telemetry_custom_model_inference_seconds` |

### Labels

| Practice | Why |
|---|---|
| Always include `organization` and `tenant` labels | Enables multi-tenant filtering, consistent with platform metrics |
| Include `service_id` if metric is model-specific | Enables per-model breakdowns and SMR routing |
| Keep label cardinality low (<100 unique values per label) | High cardinality causes Prometheus memory issues |
| Never use request IDs, timestamps, or user IDs as labels | These are unbounded and will crash Prometheus |
| Access tenant/org from `request.state` (set by middleware) | Ensures consistent resolution with default metrics |

### Metric types — when to use which

| Type | Use when | Example |
|---|---|---|
| Counter | Value only goes up (counts, totals) | Documents processed, tokens consumed |
| Histogram | You need percentiles or distributions | Latency, payload sizes |
| Gauge | Value can go up or down (current state) | Queue depth, active connections, cache size |

### Histogram buckets

Choose buckets based on your expected value range:

```python
# For latency (seconds) — most inference workloads
buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, float("inf"))

# For payload sizes (KB)
buckets=(1, 10, 50, 100, 500, 1000, 5000, 10000, float("inf"))

# For character/token counts
buckets=(10, 50, 100, 500, 1000, 5000, 10000, 50000, float("inf"))
```

---

## 10. Creating Alerts on Custom Metrics

Once your custom metric is being scraped, you can create alerts through the Alert Management API:

```bash
curl -X POST http://localhost:8098/api/v1/alert-definitions \
  -H "Content-Type: application/json" \
  -d '{
    "name": "CustomProcessingLatencyHigh",
    "category": "application",
    "alert_type": "Latency",
    "signal": "latency",
    "signal_metric": "latency_p99",
    "promql_expr": "histogram_quantile(0.99, rate(telemetry_custom_processing_duration_seconds_bucket[5m])) > 5.0",
    "threshold_value": 5.0,
    "threshold_unit": "s",
    "condition_operator": ">",
    "for_duration": "2m",
    "severity": "warning",
    "urgency": "medium",
    "service": "my-custom-service",
    "enabled": true
  }'
```

Or add a static alert rule directly in `infrastructure/prometheus/rules/`:

```yaml
# infrastructure/prometheus/rules/custom-alerts.yml
groups:
  - name: custom-service-alerts
    rules:
      - alert: CustomProcessingLatencyHigh
        expr: >
          histogram_quantile(0.99,
            rate(telemetry_custom_processing_duration_seconds_bucket[5m])
          ) > 5.0
        for: 2m
        labels:
          severity: warning
          category: application
        annotations:
          summary: "Custom processing P99 latency exceeds 5s"
```

---

## 11. Environment Variables Reference

| Variable | Default | Description |
|---|---|---|
| `OBSERVE_UTIL_ENABLED` | `false` | Enable the observability plugin |
| `OBSERVE_UTIL_DEBUG` | `false` | Enable debug logging for metric collection |
| `OBSERVE_UTIL_METRICS_PATH` | `/enterprise/metrics` | Path where metrics are exposed |
| `OBSERVE_UTIL_HEALTH_PATH` | `/enterprise/health` | Path for health check endpoint |
| `OBSERVE_UTIL_CUSTOMERS` | (empty) | Comma-separated list of organization names to pre-initialize |
| `OBSERVE_UTIL_APPS` | (empty) | Comma-separated list of app labels to pre-initialize |
| `OBSERVE_UTIL_COLLECT_SYSTEM_METRICS` | `true` | Collect CPU/memory system metrics |
| `OBSERVE_UTIL_COLLECT_GPU_METRICS` | `false` | Collect GPU metrics (requires GPU) |
| `OBSERVE_UTIL_AVAILABILITY_TARGET` | `100.0` | SLA availability target (%) |
| `OBSERVE_UTIL_RESPONSE_TIME_TARGET` | `1.0` | SLA response time target (seconds) |

---

## 12. Validation Checklist

Use this checklist before deploying custom metrics to production:

- [ ] Metric name starts with `telemetry_custom_` prefix
- [ ] Metric registered on the shared `collector.registry` (not the default registry)
- [ ] Labels include `organization` and `tenant` for multi-tenant compatibility
- [ ] No high-cardinality labels (request IDs, timestamps, user IDs)
- [ ] Histogram buckets are appropriate for expected value range
- [ ] Metric appears in `GET /enterprise/metrics` output
- [ ] Service is listed in both `ai4i-services` and `ai4icore-enterprise` scrape jobs in `prometheus.yml`
- [ ] Prometheus target shows as "UP" in `http://prometheus:9090/targets`
- [ ] PromQL query returns expected values: `curl http://prometheus:9090/api/v1/query --data-urlencode 'query=your_metric_name'`
- [ ] Alert rule (if any) fires correctly when threshold is breached

---

## 13. Troubleshooting

| Problem | Cause | Solution |
|---|---|---|
| Metric not in `/enterprise/metrics` output | Not registered on shared registry | Use `registry=collector.registry` when creating the metric |
| `ValueError: Duplicated timeseries` | Metric name already exists | Check if the metric is already defined in `metrics.py`; use a unique name |
| Prometheus shows metric but with no data | No requests have recorded values yet | Send a test request and check again |
| Prometheus target is DOWN | Service not reachable or wrong port | Verify service is running and port matches `prometheus.yml` |
| `NaN` in histogram_quantile | Zero observations in the time window | Normal for idle services; will resolve when traffic arrives |
| Metric disappears after restart | Counters/histograms reset on restart | Expected behavior; `rate()` and `increase()` handle resets correctly |

---

## 14. Related Files

| File | Purpose |
|---|---|
| `libs/ai4icore_observability/ai4icore_observability/metrics.py` | MetricsCollector class, all default metric definitions, tracking methods |
| `libs/ai4icore_observability/ai4icore_observability/middleware.py` | Automatic metric extraction from requests |
| `libs/ai4icore_observability/ai4icore_observability/plugin.py` | ObservabilityPlugin — registers middleware and /enterprise/metrics endpoint |
| `libs/ai4icore_observability/ai4icore_observability/config.py` | PluginConfig — environment variable mapping |
| `libs/ai4icore_service_base/ai4icore_service_base/app_factory.py` | create_inference_app() — automatic observability wiring |
| `infrastructure/prometheus/prometheus.yml` | Prometheus scrape targets |
| `infrastructure/prometheus/rules/` | Alert rule definitions |
