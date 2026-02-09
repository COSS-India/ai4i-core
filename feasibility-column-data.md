# Feasibility Column Data for Metrics Table

This document provides the "Feasibility Assessment" column data that can be added to your original metrics table.

## Column Format

Each row contains:
- **Feasibility Status**: ✅ Feasible, ⚠️ Partially Feasible, ❌ Not Feasible
- **Reason/Notes**: Explanation of feasibility and any required changes or clarifications

---

## Platform Health Metrics

| Metric Name | Feasibility Assessment |
|------------|----------------------|
| **System Availability** | ⚠️ **Partially Feasible** - Query uses `up{job="service"}` which is Prometheus service discovery, not from observability library. Alternative: Use `count(telemetry_obsv_requests_total) > 0` or Prometheus `up` metric. **Clarification**: What metric indicates system is up? |
| **SLA Compliance Rate** | ✅ **Feasible** - Metric exists: `telemetry_obsv_sla_compliance_percent`. Query needs adjustment: `avg(telemetry_obsv_sla_compliance_percent)` or filter by SLA type. **Clarification**: Which SLA types should be considered? |
| **Throughput (Requests per Second)** | ✅ **Feasible** - Use `rate(telemetry_obsv_requests_total[1m])` or `rate(telemetry_obsv_service_requests_total{service_type="ocr"}[1m])`. **Clarification**: Time range can be adjusted (1m, 5m, etc.) based on requirements. |
| **Critical Alerts/Red Flags Count** | ⚠️ **Partially Feasible** - `ALERTS` metric is from Alertmanager, not directly queryable. Alternative: Use `sum(telemetry_obsv_errors_total{status_code=~"5.."})` for server errors, or query Alertmanager API. **Clarification**: Define what is "critical" - error codes, thresholds, or Alertmanager alert states? |
| **Success Rate** | ✅ **Feasible** - Query: `(sum(rate(telemetry_obsv_requests_total{status_code=~"2.."}[5m])) / sum(rate(telemetry_obsv_requests_total[5m]))) * 100`. **Note**: Similar to SLA Compliance but calculated differently. |
| **Failed Requests Count** | ✅ **Feasible** - Query: `sum(increase(telemetry_obsv_requests_total{status_code=~"[45].."}[1h]))`. **Note**: Already have error breakdown via `telemetry_obsv_errors_total`. |
| **Timeout Rate** | ⚠️ **Partially Feasible** - Status code 504 may not be the only timeout indicator. Query: `(sum(rate(telemetry_obsv_requests_total{status_code="504"}[5m])) / sum(rate(telemetry_obsv_requests_total[5m]))) * 100`. **Clarification**: Define timeout criteria - HTTP 504, request duration thresholds, or both? |
| **Concurrent Requests** | ❌ **Not Feasible** - No `http_requests_in_flight` gauge exists. **Recommendation**: Implement middleware to track active requests using a Gauge metric. |
| **Queue Depth** | ❌ **Not Feasible** - No `queue_depth` metric exists. **Recommendation**: Implement queue depth tracking if using message queue system (Redis, RabbitMQ, etc.). |

---

## Usage & Adoption Metrics

| Metric Name | Feasibility Assessment |
|------------|----------------------|
| **Total API Requests (Daily/Monthly)** | ✅ **Feasible** - Query: `sum(increase(telemetry_obsv_requests_total[24h]))` or `sum(increase(telemetry_obsv_requests_total[30d]))`. **Note**: Replace `model_type` with `service_type` in filters. |
| **Requests per Model (Daily Avg)** | ⚠️ **Partially Feasible** - No `model_type` label exists, only `service_type`. Alternative: `avg_over_time(sum(rate(telemetry_obsv_service_requests_total[1h])) by (service_type)[24h:1h])`. **Clarification**: Is "model" referring to service type (OCR, TTS, etc.) or specific model instances? |
| **Top 5 Models by Usage** | ⚠️ **Partially Feasible** - No `model_type` label. Alternative: `topk(5, sum(rate(telemetry_obsv_service_requests_total[24h])) by (service_type))`. **Note**: Shows top 5 service types, not individual models. **Clarification**: Define what "model" means - service type or specific model version? |
| **Requests by Time of Day** | ⚠️ **Partially Feasible** - Prometheus doesn't have native `hour` label. Alternative: Use `hour(timestamp(telemetry_obsv_requests_total))` in Grafana, or use recording rules. **Note**: Heatmap visualization is feasible in Grafana with query transformation. |
| **Peak Usage Hours** | ✅ **Feasible** - Query: `max_over_time(sum(rate(telemetry_obsv_requests_total[1h]))[24h:1h])`. Can be visualized as time series. |
| **Request Volume Trends (Week/Month)** | ✅ **Feasible** - Query: `sum(increase(telemetry_obsv_service_requests_total[7d])) by (service_type)`. Time series visualization works well. |
| **API Version Usage Distribution** | ❌ **Not Feasible** - No `api_version` label exists. **Recommendation**: Add `api_version` label to `telemetry_obsv_requests_total` if API versioning is tracked in headers or endpoints. |

---

## Customer Reach Metrics

| Metric Name | Feasibility Assessment |
|------------|----------------------|
| **Total Customers** | ✅ **Feasible** - Query: `count(count(telemetry_obsv_requests_total) by (organization))`. Uses `organization` label (maps to customer via X-Customer-ID header or JWT). |
| **Total Active Customers** | ✅ **Feasible** - Query: `count(count(telemetry_obsv_requests_total[30d]) by (organization))`. **Clarification**: Define "active" - customers with requests in last 30 days? |
| **Total Customers Using APIs by Service** | ✅ **Feasible** - Query: `count(count(telemetry_obsv_service_requests_total) by (organization, service_type)) by (service_type)`. **Note**: Uses `service_type` instead of model. |
| **Top 10 Customers by Usage** | ✅ **Feasible** - Query: `topk(10, sum(rate(telemetry_obsv_requests_total[24h])) by (organization))`. |
| **Unique Customers per Model** | ⚠️ **Partially Feasible** - No `model_type` label. Alternative: `count(count(telemetry_obsv_service_requests_total) by (organization)) by (service_type)`. Shows unique customers per service type. |
| **New Customers (Daily/Weekly/Monthly)** | ✅ **Feasible** - Query: `count(count(telemetry_obsv_requests_total[24h]) by (organization)) - count(count(telemetry_obsv_requests_total[48h] offset 24h) by (organization))`. **Note**: Calculates new customers by comparing time windows. |

---

## Growth Metrics

| Metric Name | Feasibility Assessment |
|------------|----------------------|
| **Growth Rate (MoM)** | ✅ **Feasible** - Query: `((sum(increase(telemetry_obsv_requests_total[30d])) - sum(increase(telemetry_obsv_requests_total[30d] offset 30d))) / sum(increase(telemetry_obsv_requests_total[30d] offset 30d))) * 100`. |
| **Usage Growth by Model Type** | ⚠️ **Partially Feasible** - No `model_type` label. Alternative: `((sum(rate(telemetry_obsv_service_requests_total[7d])) by (service_type) - sum(rate(telemetry_obsv_service_requests_total[7d] offset 7d)) by (service_type)) / sum(rate(telemetry_obsv_service_requests_total[7d] offset 7d)) by (service_type)) * 100`. Shows growth by service type. |

---

## Customer Health Metrics

| Metric Name | Feasibility Assessment |
|------------|----------------------|
| **Inactive Customers Count** | ✅ **Feasible** - Query: `count(count(telemetry_obsv_requests_total[90d]) by (organization)) - count(count(telemetry_obsv_requests_total[30d]) by (organization))`. **Clarification**: Define "inactive" - customers with requests 30-90 days ago but not in last 30 days? |
| **Customer Retention Rate** | ✅ **Feasible** - Query: `(count(count(telemetry_obsv_requests_total[30d]) by (organization)) / count(count(telemetry_obsv_requests_total[60d] offset 30d) by (organization))) * 100`. **Clarification**: Define retention - customers active in both periods? |

---

## Resource Utilization Metrics

| Metric Name | Feasibility Assessment |
|------------|----------------------|
| **CPU Usage by Service** | ⚠️ **Partially Feasible** - `telemetry_obsv_system_cpu_percent` is system-wide, not per-service. Alternative: Use `telemetry_obsv_organization_cpu_percent{organization}` for org-level CPU, or Prometheus `process_cpu_seconds_total` if exposed. **Clarification**: Do you need per-service CPU or per-organization CPU? |
| **Memory Usage by Service** | ⚠️ **Partially Feasible** - `telemetry_obsv_system_memory_percent` is system-wide. Alternative: Use `telemetry_obsv_organization_memory_percent{organization}` for org-level, or Prometheus `process_resident_memory_bytes` if exposed. **Clarification**: Per-service or per-organization memory? |
| **API Rate Limit Hits** | ⚠️ **Partially Feasible** - Status code 429 may not be the only rate limit indicator. Alternative: `sum(increase(telemetry_obsv_requests_total{status_code="429"}[1h]))`. **Clarification**: Is 429 the only rate limit indicator, or are there custom rate limit headers/metrics? |
| **Throttled Requests Count** | ⚠️ **Partially Feasible** - Same as above - depends on how throttling is indicated. Alternative: `sum(increase(telemetry_obsv_requests_total{status_code="429"}[1h])) by (service_type)`. **Note**: Requires filtering `telemetry_obsv_requests_total` by status_code and grouping by service_type. |

---

## Quick Reference: Label Mappings

- **`model_type`** → Use **`service_type`** (values: "ocr", "tts", "asr", "translation", "transliteration", "ner", etc.)
- **`customer_id`** → Use **`organization`** (extracted from X-Customer-ID header or JWT token)
- **`http_requests_total`** → Use **`telemetry_obsv_requests_total`**
- **`http_requests_in_flight`** → **Not available** (needs implementation)
- **`queue_depth`** → **Not available** (needs implementation)
- **`api_version`** → **Not available** (needs label addition)

