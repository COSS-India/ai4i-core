# Metrics Feasibility Analysis

Based on the `ai4icore_observability` library implementation using `prometheus_client`, this document provides feasibility assessment for each proposed metric.

## Key Findings

**Available Metrics:**
- `telemetry_obsv_requests_total` (Counter) - Labels: `organization`, `app`, `method`, `endpoint`, `status_code`
- `telemetry_obsv_service_requests_total` (Counter) - Labels: `organization`, `app`, `service_type`
- `telemetry_obsv_request_duration_seconds` (Histogram) - Labels: `organization`, `app`, `method`, `endpoint`
- `telemetry_obsv_errors_total` (Counter) - Labels: `organization`, `app`, `endpoint`, `status_code`, `error_type`
- `telemetry_obsv_system_cpu_percent` (Gauge)
- `telemetry_obsv_system_memory_percent` (Gauge`
- `telemetry_obsv_sla_availability_percent` (Gauge) - Labels: `organization`, `app`
- `telemetry_obsv_sla_compliance_percent` (Gauge) - Labels: `organization`, `app`, `sla_type`

**Missing Labels:**
- No `model_type` label (only `service_type` exists)
- No `customer_id` label (only `organization` exists)
- No `api_version` label
- No `http_requests_in_flight` gauge
- No `queue_depth` metric
- No `up` metric (would need Prometheus service discovery)

---

## Platform Health Metrics

| Metric Name | Feasibility | Notes |
|------------|-------------|-------|
| **System Availability** | ⚠️ **Partially Feasible** | **Issue**: Query uses `up{job="service"}` which is a Prometheus service discovery metric, not exposed by the observability library. **Alternative**: Can use `count(telemetry_obsv_requests_total) > 0` to infer service is up, but this is indirect. **Recommendation**: Use Prometheus `up` metric from service discovery, or implement a health check metric. |
| **SLA Compliance Rate** | ✅ **Feasible** | Metric exists: `telemetry_obsv_sla_compliance_percent{organization, app, sla_type}`. Query needs adjustment: `avg(telemetry_obsv_sla_compliance_percent)` or filter by specific SLA type. **Clarification Needed**: Which SLA types should be considered? |
| **Throughput (Requests per Second)** | ✅ **Feasible** | Use `rate(telemetry_obsv_requests_total[1m])` or `rate(telemetry_obsv_service_requests_total{service_type="ocr"}[1m])`. **Clarification Needed**: Time range can be adjusted (1m, 5m, etc.) based on requirements. |
| **Critical Alerts/Red Flags Count** | ⚠️ **Partially Feasible** | **Issue**: `ALERTS` metric is from Alertmanager, not directly queryable in Prometheus. **Alternative**: Use `sum(telemetry_obsv_errors_total{status_code=~"5.."})` for server errors, or query Alertmanager API. **Clarification Needed**: Define what constitutes "critical" - error codes, thresholds, or Alertmanager alert states? |
| **Success Rate** | ✅ **Feasible** | Query: `(sum(rate(telemetry_obsv_requests_total{status_code=~"2.."}[5m])) / sum(rate(telemetry_obsv_requests_total[5m]))) * 100`. **Note**: This is similar to SLA Compliance but calculated differently. |
| **Failed Requests Count** | ✅ **Feasible** | Query: `sum(increase(telemetry_obsv_requests_total{status_code=~"[45].."}[1h]))`. **Note**: Already have error rate breakdown via `telemetry_obsv_errors_total`. |
| **Timeout Rate** | ⚠️ **Partially Feasible** | **Issue**: Status code 504 (Gateway Timeout) may not be the only timeout indicator. **Alternative**: Query `(sum(rate(telemetry_obsv_requests_total{status_code="504"}[5m])) / sum(rate(telemetry_obsv_requests_total[5m]))) * 100`. **Clarification Needed**: Define timeout criteria - HTTP 504, request duration thresholds, or both? |
| **Concurrent Requests** | ❌ **Not Feasible** | **Issue**: No `http_requests_in_flight` gauge exists. **Alternative**: Would need to implement a custom gauge that tracks active requests. **Recommendation**: Add middleware to track in-flight requests using a Gauge metric. |
| **Queue Depth** | ❌ **Not Feasible** | **Issue**: No `queue_depth` metric exists. This would require application-level queue monitoring. **Recommendation**: Implement queue depth tracking if using a message queue system (Redis, RabbitMQ, etc.). |

---

## Usage & Adoption Metrics

| Metric Name | Feasibility | Notes |
|------------|-------------|-------|
| **Total API Requests (Daily/Monthly)** | ✅ **Feasible** | Query: `sum(increase(telemetry_obsv_requests_total[24h]))` or `sum(increase(telemetry_obsv_requests_total[30d]))`. **Note**: Replace `model_type` with `service_type` in filters. |
| **Requests per Model (Daily Avg)** | ⚠️ **Partially Feasible** | **Issue**: No `model_type` label exists, only `service_type`. **Alternative**: Use `avg_over_time(sum(rate(telemetry_obsv_service_requests_total[1h])) by (service_type)[24h:1h])`. **Clarification Needed**: Is "model" referring to service type (OCR, TTS, etc.) or specific model instances? |
| **Top 5 Models by Usage** | ⚠️ **Partially Feasible** | **Issue**: No `model_type` label. **Alternative**: `topk(5, sum(rate(telemetry_obsv_service_requests_total[24h])) by (service_type))`. **Note**: This shows top 5 service types, not individual models. **Clarification Needed**: Define what "model" means - service type or specific model version? |
| **Requests by Time of Day** | ⚠️ **Partially Feasible** | **Issue**: Prometheus doesn't have a native `hour` label. **Alternative**: Use `hour(timestamp(telemetry_obsv_requests_total))` in Grafana, or use recording rules to extract hour. **Note**: Heatmap visualization is feasible in Grafana, but requires query transformation. |
| **Peak Usage Hours** | ✅ **Feasible** | Query: `max_over_time(sum(rate(telemetry_obsv_requests_total[1h]))[24h:1h])`. Can be visualized as time series. |
| **Request Volume Trends (Week/Month)** | ✅ **Feasible** | Query: `sum(increase(telemetry_obsv_service_requests_total[7d])) by (service_type)`. Time series visualization works well. |
| **API Version Usage Distribution** | ❌ **Not Feasible** | **Issue**: No `api_version` label exists in metrics. **Recommendation**: Add `api_version` label to `telemetry_obsv_requests_total` if API versioning is tracked in headers or endpoints. |

---

## Customer Reach Metrics

| Metric Name | Feasibility | Notes |
|------------|-------------|-------|
| **Total Customers** | ✅ **Feasible** | Query: `count(count(telemetry_obsv_requests_total) by (organization))`. Uses `organization` label (maps to customer via X-Customer-ID header or JWT). |
| **Total Active Customers** | ✅ **Feasible** | Query: `count(count(telemetry_obsv_requests_total[30d]) by (organization))`. **Clarification Needed**: Define "active" - customers with requests in last 30 days? |
| **Total Customers Using APIs by Service** | ✅ **Feasible** | Query: `count(count(telemetry_obsv_service_requests_total) by (organization, service_type)) by (service_type)`. **Note**: Uses `service_type` instead of model. |
| **Top 10 Customers by Usage** | ✅ **Feasible** | Query: `topk(10, sum(rate(telemetry_obsv_requests_total[24h])) by (organization))`. |
| **Unique Customers per Model** | ⚠️ **Partially Feasible** | **Issue**: No `model_type` label. **Alternative**: `count(count(telemetry_obsv_service_requests_total) by (organization)) by (service_type)`. Shows unique customers per service type. |
| **New Customers (Daily/Weekly/Monthly)** | ✅ **Feasible** | Query: `count(count(telemetry_obsv_requests_total[24h]) by (organization)) - count(count(telemetry_obsv_requests_total[48h] offset 24h) by (organization))`. **Note**: This calculates new customers by comparing time windows. |

---

## Growth Metrics

| Metric Name | Feasibility | Notes |
|------------|-------------|-------|
| **Growth Rate (MoM)** | ✅ **Feasible** | Query: `((sum(increase(telemetry_obsv_requests_total[30d])) - sum(increase(telemetry_obsv_requests_total[30d] offset 30d))) / sum(increase(telemetry_obsv_requests_total[30d] offset 30d))) * 100`. |
| **Usage Growth by Model Type** | ⚠️ **Partially Feasible** | **Issue**: No `model_type` label. **Alternative**: `((sum(rate(telemetry_obsv_service_requests_total[7d])) by (service_type) - sum(rate(telemetry_obsv_service_requests_total[7d] offset 7d)) by (service_type)) / sum(rate(telemetry_obsv_service_requests_total[7d] offset 7d)) by (service_type)) * 100`. Shows growth by service type. |

---

## Customer Health Metrics

| Metric Name | Feasibility | Notes |
|------------|-------------|-------|
| **Inactive Customers Count** | ✅ **Feasible** | Query: `count(count(telemetry_obsv_requests_total[90d]) by (organization)) - count(count(telemetry_obsv_requests_total[30d]) by (organization))`. **Clarification Needed**: Define "inactive" - customers with requests 30-90 days ago but not in last 30 days? |
| **Customer Retention Rate** | ✅ **Feasible** | Query: `(count(count(telemetry_obsv_requests_total[30d]) by (organization)) / count(count(telemetry_obsv_requests_total[60d] offset 30d) by (organization))) * 100`. **Clarification Needed**: Define retention - customers active in both periods? |

---

## Resource Utilization Metrics

| Metric Name | Feasibility | Notes |
|------------|-------------|-------|
| **CPU Usage by Service** | ⚠️ **Partially Feasible** | **Issue**: `telemetry_obsv_system_cpu_percent` is system-wide, not per-service. **Alternative**: Use `telemetry_obsv_organization_cpu_percent{organization}` for org-level CPU, or use Prometheus `process_cpu_seconds_total` if exposed. **Clarification Needed**: Do you need per-service CPU or per-organization CPU? |
| **Memory Usage by Service** | ⚠️ **Partially Feasible** | **Issue**: `telemetry_obsv_system_memory_percent` is system-wide. **Alternative**: Use `telemetry_obsv_organization_memory_percent{organization}` for org-level, or Prometheus `process_resident_memory_bytes` if exposed. **Clarification Needed**: Per-service or per-organization memory? |
| **API Rate Limit Hits** | ⚠️ **Partially Feasible** | **Issue**: Status code 429 (Too Many Requests) may not be the only rate limit indicator. **Alternative**: `sum(increase(telemetry_obsv_requests_total{status_code="429"}[1h]))`. **Clarification Needed**: Is 429 the only rate limit indicator, or are there custom rate limit headers/metrics? |
| **Throttled Requests Count** | ⚠️ **Partially Feasible** | **Issue**: Same as above - depends on how throttling is indicated. **Alternative**: `sum(increase(telemetry_obsv_service_requests_total{status_code="429"}[1h])) by (service_type)`. **Note**: This requires status_code label on service_requests_total, which may not exist. Use `telemetry_obsv_requests_total` instead. |

---

## Summary of Required Changes

### High Priority (P0 Metrics)
1. **System Availability**: Implement health check metric or use Prometheus `up` metric
2. **SLA Compliance Rate**: Clarify which SLA types to include
3. **Critical Alerts**: Define critical error criteria and implement alerting rules
4. **Success Rate**: Already feasible, but clarify difference from SLA Compliance

### Medium Priority (P1 Metrics)
1. **Model Type Label**: Add `model_type` or clarify if `service_type` is sufficient
2. **API Version Label**: Add `api_version` label if API versioning is tracked
3. **Concurrent Requests**: Implement `http_requests_in_flight` Gauge metric
4. **Queue Depth**: Implement if using message queues

### Low Priority (P2 Metrics)
1. **Requests by Time of Day**: Implement recording rules or use Grafana transformations
2. **Per-Service CPU/Memory**: Clarify if organization-level metrics are sufficient

---

## Recommendations

1. **Use `service_type` instead of `model_type`** for service-level aggregations
2. **Use `organization` instead of `customer_id`** (they map to the same concept)
3. **Add missing labels** if needed: `api_version`, `model_type` (if different from service_type)
4. **Implement missing metrics**: `http_requests_in_flight`, `queue_depth` (if applicable)
5. **Clarify definitions**: "active customer", "inactive customer", "critical alerts", "timeout criteria"
6. **Use Prometheus service discovery** for `up` metric instead of application-level tracking

