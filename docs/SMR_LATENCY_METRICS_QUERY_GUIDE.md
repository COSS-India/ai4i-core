# Querying Latency Metrics for Smart Model Routing (SMR)

This document explains how the SMR service can query Prometheus for per-`service_id` latency percentiles (p50, p95, p99) to make model routing decisions.

---

## 1. Metric Overview

All AI4I services emit request latency via the observability middleware. The metric relevant to SMR is:

| Metric | Type | Description |
|---|---|---|
| `telemetry_obsv_request_duration_seconds` | Histogram | Request duration in seconds |

### Labels

| Label | Description | Example |
|---|---|---|
| `service_id` | Model/service identifier (set by model-management middleware) | `asr-model-v1` |
| `app` | Application identifier | `voice-app` |
| `method` | HTTP method | `POST` |
| `endpoint` | Request path | `/v1/inference` |
| `tenant` | Tenant ID | `tenant-123` |

### How Histograms Work

Prometheus histograms store data as cumulative bucket counters, not raw values. For `telemetry_obsv_request_duration_seconds`, the default buckets are:

```
.005, .01, .025, .05, .075, .1, .25, .5, .75, 1.0, 2.5, 5.0, 7.5, 10.0, +Inf
```

This means Prometheus tracks "how many requests completed in <= X seconds" for each bucket boundary. The `histogram_quantile()` function interpolates across these buckets to estimate percentiles.

---

## 2. Prometheus HTTP API

Prometheus exposes a query API at:

```
GET http://<PROMETHEUS_HOST>:9090/api/v1/query?query=<PromQL>
```

Within the Docker Compose stack, Prometheus is reachable at `prometheus:9090`.

### Response Format

```json
{
  "status": "success",
  "data": {
    "resultType": "vector",
    "result": [
      {
        "metric": { "service_id": "asr-model-v1" },
        "value": [1712700000, "0.245"]
      }
    ]
  }
}
```

The `value` array contains `[unix_timestamp, "metric_value_as_string"]`.

---

## 3. PromQL Queries for Latency Percentiles

### 3.1 Single service_id, single percentile

**p95 latency for a specific service_id (over the last 5 minutes):**

```promql
histogram_quantile(
  0.95,
  rate(telemetry_obsv_request_duration_seconds_bucket{service_id="asr-model-v1"}[5m])
)
```

**p50 (median):**

```promql
histogram_quantile(
  0.50,
  rate(telemetry_obsv_request_duration_seconds_bucket{service_id="asr-model-v1"}[5m])
)
```

**p99:**

```promql
histogram_quantile(
  0.99,
  rate(telemetry_obsv_request_duration_seconds_bucket{service_id="asr-model-v1"}[5m])
)
```

### 3.2 Compare multiple service_ids

To get p95 latency for multiple service_ids in a single query (useful for routing comparisons):

```promql
histogram_quantile(
  0.95,
  sum by (le, service_id) (
    rate(telemetry_obsv_request_duration_seconds_bucket{service_id=~"asr-model-v1|asr-model-v2|asr-model-v3"}[5m])
  )
)
```

This returns one result per `service_id`, letting SMR compare them directly.

### 3.3 All service_ids (discover available models)

```promql
histogram_quantile(
  0.95,
  sum by (le, service_id) (
    rate(telemetry_obsv_request_duration_seconds_bucket[5m])
  )
)
```

### 3.4 Filter by tenant

To get latency for a specific service_id scoped to a particular tenant:

```promql
histogram_quantile(
  0.95,
  sum by (le, service_id) (
    rate(telemetry_obsv_request_duration_seconds_bucket{service_id="asr-model-v1", tenant="tenant-123"}[5m])
  )
)
```

Compare multiple service_ids for a specific tenant:

```promql
histogram_quantile(
  0.95,
  sum by (le, service_id) (
    rate(telemetry_obsv_request_duration_seconds_bucket{service_id=~"asr-model-v1|asr-model-v2", tenant="tenant-123"}[5m])
  )
)
```

### 3.5 Average latency (alternative to percentiles)

```promql
rate(telemetry_obsv_request_duration_seconds_sum{service_id="asr-model-v1"}[5m])
/
rate(telemetry_obsv_request_duration_seconds_count{service_id="asr-model-v1"}[5m])
```

### 3.6 Request throughput (requests per second)

Useful alongside latency for routing weight decisions:

```promql
sum by (service_id) (
  rate(telemetry_obsv_requests_total{service_id=~"asr-model-v1|asr-model-v2"}[5m])
)
```

---

## 4. Querying from Python (httpx)

```python
import httpx

PROMETHEUS_URL = "http://prometheus:9090"

async def get_latency_percentile(
    service_id: str,
    quantile: float = 0.95,
    range_window: str = "5m",
) -> float | None:
    """
    Query Prometheus for a latency percentile of a given service_id.

    Args:
        service_id:   The model/service identifier (e.g. "asr-model-v1").
        quantile:     The percentile as a float (0.50, 0.95, 0.99).
        range_window: The PromQL range window (e.g. "5m", "10m").

    Returns:
        Latency in seconds, or None if no data is available.
    """
    query = (
        f'histogram_quantile({quantile}, '
        f'rate(telemetry_obsv_request_duration_seconds_bucket'
        f'{{service_id="{service_id}"}}[{range_window}]))'
    )
    async with httpx.AsyncClient(timeout=5.0) as client:
        resp = await client.get(
            f"{PROMETHEUS_URL}/api/v1/query",
            params={"query": query},
        )
        resp.raise_for_status()
        data = resp.json()

    results = data.get("data", {}).get("result", [])
    if not results:
        return None

    value = float(results[0]["value"][1])
    # NaN means no observations in the window
    if value != value:  # IEEE 754 NaN check
        return None
    return value


async def compare_service_latencies(
    service_ids: list[str],
    quantile: float = 0.95,
    range_window: str = "5m",
) -> dict[str, float]:
    """
    Compare latency percentiles across multiple service_ids in a single query.

    Returns:
        Dict mapping service_id -> latency in seconds.
    """
    id_regex = "|".join(service_ids)
    query = (
        f'histogram_quantile({quantile}, '
        f'sum by (le, service_id) ('
        f'rate(telemetry_obsv_request_duration_seconds_bucket'
        f'{{service_id=~"{id_regex}"}}[{range_window}])))'
    )
    async with httpx.AsyncClient(timeout=5.0) as client:
        resp = await client.get(
            f"{PROMETHEUS_URL}/api/v1/query",
            params={"query": query},
        )
        resp.raise_for_status()
        data = resp.json()

    latencies = {}
    for result in data.get("data", {}).get("result", []):
        sid = result["metric"].get("service_id", "")
        val = float(result["value"][1])
        if val == val:  # skip NaN
            latencies[sid] = val
    return latencies
```

### Usage example

```python
# Single service
p95 = await get_latency_percentile("asr-model-v1", quantile=0.95)
p50 = await get_latency_percentile("asr-model-v1", quantile=0.50)
p99 = await get_latency_percentile("asr-model-v1", quantile=0.99)

# Compare multiple services for routing
latencies = await compare_service_latencies(
    ["asr-model-v1", "asr-model-v2", "asr-model-v3"],
    quantile=0.95,
)
# latencies = {"asr-model-v1": 0.23, "asr-model-v2": 0.18, "asr-model-v3": 0.41}
fastest = min(latencies, key=latencies.get)
```

---

## 6. Scrape Configuration

Prometheus scrapes all services every **5 seconds** (see `infrastructure/prometheus/prometheus.yml`). Enterprise metrics are scraped from `/enterprise/metrics`. This means:

- Latency data is at most **5 seconds stale** in Prometheus.
- A `[5m]` range window covers the last 5 minutes of scrapes (~60 data points).
- Shorter windows (e.g., `[1m]`) are more responsive but noisier; longer windows (e.g., `[15m]`) are smoother but slower to react.

**Recommendation for SMR**: Use `[5m]` as default. Consider `[1m]` if fast reaction to latency spikes is more important than smoothness.

---

## 8. Quick Reference

| What you want | PromQL |
|---|---|
| p50 for one service | `histogram_quantile(0.50, rate(..._bucket{service_id="X"}[5m]))` |
| p95 for one service | `histogram_quantile(0.95, rate(..._bucket{service_id="X"}[5m]))` |
| p99 for one service | `histogram_quantile(0.99, rate(..._bucket{service_id="X"}[5m]))` |
| p95 across multiple services | `histogram_quantile(0.95, sum by (le, service_id) (rate(..._bucket{service_id=~"A\|B\|C"}[5m])))` |
| Average latency | `rate(..._sum{service_id="X"}[5m]) / rate(..._count{service_id="X"}[5m])` |
| Throughput (req/s) | `sum by (service_id) (rate(telemetry_obsv_requests_total{service_id="X"}[5m]))` |

Where `...` = `telemetry_obsv_request_duration_seconds`

---

## 9. Related Files

| File | Purpose |
|---|---|
| `libs/ai4icore_observability/ai4icore_observability/metrics.py` | Metric definitions (histogram, labels, buckets) |
| `libs/ai4icore_observability/ai4icore_observability/middleware.py` | Where `service_id` label is populated and `duration` is observed |
| `infrastructure/prometheus/prometheus.yml` | Scrape targets and intervals |
