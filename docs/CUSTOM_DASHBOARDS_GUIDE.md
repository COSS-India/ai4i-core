# Custom Grafana Dashboards Guide for Adopters

This guide documents the end-to-end steps required to create, configure, and manage custom Grafana dashboards beyond the default dashboards provided by the AI4I platform.

---

## 1. Prerequisites

| Requirement | How to verify |
|---|---|
| Grafana is running | Open `http://localhost:3001` (or your configured Grafana URL) |
| Prometheus datasource is configured | Grafana > Settings > Data Sources > "Prometheus" should show status "OK" |
| Services are being scraped | `http://localhost:9090/targets` shows all targets as UP |
| Admin or Editor role in Grafana | You need at least Editor permissions to create dashboards |

### Default credentials

| Setting | Value |
|---|---|
| Grafana URL | `http://localhost:3001` (mapped from container port 3000) |
| Admin user | `admin` (configurable via `GRAFANA_ADMIN_USER`) |
| Admin password | `admin` (configurable via `GRAFANA_ADMIN_PASSWORD`) |
| Prometheus URL (internal) | `http://prometheus:9090` |

### Default dashboards already provided

| Dashboard | Purpose |
|---|---|
| AI4ICore DevOps Operations Dashboard | Operational metrics across all services |
| System Metrics Overview | CPU, memory, disk from node-exporter |
| Alert Validation Dashboard | Validates alert rule PromQL expressions |

---

## 2. Available Data Sources

### Prometheus (Primary)

The Prometheus datasource is pre-configured and set as the default. It scrapes metrics from two endpoints on every service:

| Scrape Job | Path | What it collects |
|---|---|---|
| `ai4i-services` | `/metrics` | Standard Prometheus metrics |
| `ai4icore-enterprise` | `/enterprise/metrics` | AI4I platform metrics (`telemetry_obsv_*`) |

Scrape interval: **5 seconds** for both jobs.

### How to add additional data sources

If you need other data sources (e.g., PostgreSQL, InfluxDB, Elasticsearch):

1. Go to Grafana > **Settings** (gear icon) > **Data Sources** > **Add data source**
2. Select the type and fill in the connection details
3. Click **Save & Test**

Or provision them by adding a YAML file to `infrastructure/grafana/provisioning/datasources/`:

```yaml
apiVersion: 1
datasources:
  - name: InfluxDB
    type: influxdb
    access: proxy
    url: http://influxdb:8086
    jsonData:
      defaultBucket: metrics
      organization: ai4i-org
    secureJsonData:
      token: ${INFLUXDB_ADMIN_TOKEN}
```

---

## 3. Available Metrics Reference

### 3.1 Request and Latency Metrics

| Metric | Type | Labels | Description |
|---|---|---|---|
| `telemetry_obsv_requests_total` | Counter | organization, app, method, endpoint, status_code, tenant, service_id | Total HTTP requests |
| `telemetry_obsv_request_duration_seconds` | Histogram | organization, app, method, endpoint, tenant, service_id | Request latency (seconds) |
### 3.2 Error Metrics

| Metric | Type | Labels | Description |
|---|---|---|---|
| `telemetry_obsv_errors_total` | Counter | organization, app, endpoint, status_code, error_type, tenant, service_id | Errors by status code. `error_type`: `client_error` (4xx), `server_error` (5xx) |

### 3.3 Business / Service-Specific Metrics

| Metric | Type | Key Labels | Description |
|---|---|---|---|
| `telemetry_obsv_tts_characters_synthesized` | Histogram | language, tenant, service_id | Characters per TTS request |
| `telemetry_obsv_nmt_characters_translated` | Histogram | source_language, target_language, tenant, service_id | Characters per translation request |
| `telemetry_obsv_asr_audio_seconds_processed` | Histogram | language, tenant, service_id | Audio duration per ASR request |
| `telemetry_obsv_ocr_characters_processed` | Histogram | tenant, service_id | Characters per OCR request |
| `telemetry_obsv_ocr_image_size_kb` | Histogram | tenant, service_id | Image payload size (KB) per OCR request |
| `telemetry_obsv_transliteration_characters_processed` | Histogram | source_language, target_language, tenant, service_id | Characters per transliteration request |
| `telemetry_obsv_language_detection_characters_processed` | Histogram | tenant, service_id | Characters per language detection request |
| `telemetry_obsv_audio_lang_detection_seconds_processed` | Histogram | tenant, service_id | Audio duration per audio language detection request |
| `telemetry_obsv_ner_tokens_processed` | Histogram | tenant, service_id | Tokens (words) per NER request |
| `telemetry_obsv_speaker_diarization_seconds_processed` | Histogram | tenant, service_id | Audio duration per speaker diarization request |
| `telemetry_obsv_language_diarization_seconds_processed` | Histogram | tenant, service_id | Audio duration per language diarization request |
| `telemetry_obsv_speaker_verification_seconds_processed` | Histogram | tenant, service_id | Audio duration per speaker verification request |

### 3.4 Data Processing and LLM Metrics

| Metric | Type | Labels | Description |
|---|---|---|---|
| `telemetry_obsv_data_processed_total` | Counter | organization, app, data_type, tenant | Total data volume processed |
| `telemetry_obsv_llm_tokens_processed_total` | Counter | organization, app, model, tenant | Total LLM tokens consumed |

### 3.5 Infrastructure Metrics (node-exporter)

| Metric | Type | Description |
|---|---|---|
| `node_cpu_seconds_total` | Counter | CPU time by mode (idle, user, system, iowait) |
| `node_memory_MemTotal_bytes` | Gauge | Total physical memory |
| `node_memory_MemAvailable_bytes` | Gauge | Available memory |
| `node_filesystem_size_bytes` | Gauge | Filesystem total size |
| `node_filesystem_avail_bytes` | Gauge | Filesystem available space |

### 3.6 Custom Metrics

Any metrics you create following the Custom Metrics Guide (prefix: `telemetry_custom_*`) are also available. See `docs/CUSTOM_METRICS_GUIDE.md`.

---

## 4. Creating a Dashboard via the Grafana UI

### Step 1: Create a new dashboard

1. Click **+** (plus icon) in the left sidebar > **New dashboard**
2. Click **Add visualization**
3. Select **Prometheus** as the data source

### Step 2: Add a panel

1. In the query editor, switch to **Code** mode (toggle at top-right of query editor)
2. Enter a PromQL expression (see Section 6 for examples)
3. Configure the panel:

| Setting | Where | What to set |
|---|---|---|
| Panel type | Top-right dropdown | `Stat`, `Gauge`, `Time series`, `Table`, `Bar chart`, `Pie chart` |
| Title | Panel options (right sidebar) > Title | Descriptive name |
| Description | Panel options > Description | Explain what the panel shows |
| Unit | Standard options > Unit | `seconds (s)`, `percent (0-100)`, `short`, `bytes`, etc. |
| Thresholds | Thresholds section | Set color bands (green/yellow/red) |

### Step 3: Add template variables (filters)

Template variables create dropdown filters at the top of the dashboard.

1. Go to **Dashboard settings** (gear icon) > **Variables** > **New variable**
2. Configure:

| Field | Value |
|---|---|
| Name | `tenant` |
| Type | Query |
| Data source | Prometheus |
| Query | `label_values(telemetry_obsv_requests_total, tenant)` |
| Multi-value | Enabled |
| Include All option | Enabled |
| All value | `.*` |

3. Use `$tenant` in your PromQL expressions: `...{tenant=~"$tenant"}...`

Common variables to create:

| Variable | Query | Purpose |
|---|---|---|
| `tenant` | `label_values(telemetry_obsv_requests_total, tenant)` | Filter by tenant |
| `organization` | `label_values(telemetry_obsv_requests_total, organization)` | Filter by organization |
| `service` | `label_values(telemetry_obsv_requests_total{job="ai4icore-enterprise"}, service)` | Filter by service |
| `endpoint` | `label_values(telemetry_obsv_requests_total{service=~"$service"}, endpoint)` | Filter by endpoint (cascaded from service) |
| `service_id` | `label_values(telemetry_obsv_requests_total, service_id)` | Filter by model/service ID |

### Step 4: Organize with row panels

Use row panels to group related panels into collapsible sections:

1. Click **Add** > **Row**
2. Click the row title to rename it (e.g., "Latency Metrics", "Error Rates")
3. Drag panels under the row
4. Click the row title to collapse/expand

### Step 5: Save the dashboard

1. Click **Save** (disk icon) or `Ctrl+S`
2. Enter a dashboard name and optional folder
3. Click **Save**

---

## 5. Visualization Types — When to Use What

| Panel Type | Best for | Example use case |
|---|---|---|
| **Stat** | Single number summary | Overall P99 latency, total request count |
| **Gauge** | Bounded percentage values | CPU usage, memory usage, disk usage |
| **Time series** | Trends over time | Latency trend, request rate over time |
| **Table** | Multi-dimensional comparisons | Per-service latency breakdown with multiple columns |
| **Bar chart** | Categorical comparisons | Requests per service, errors by status code |
| **Pie chart** | Proportional breakdowns | Traffic distribution by tenant, error type distribution |
| **Heatmap** | Distribution density over time | Latency distribution (from histogram buckets) |

### Stat panel configuration

Best for at-a-glance KPI values.

```
Options:
  Color mode: "value"         ← colors the number based on thresholds
  Graph mode: "area"          ← shows a mini sparkline
  Text mode: "auto"
  
Reduce options:
  Calculation: "Last *"       ← shows the most recent value
```

### Gauge panel configuration

Best for CPU/memory/disk where values are bounded 0-100%.

```
Field config:
  Unit: percent (0-100)
  Min: 0
  Max: 100
  
Thresholds:
  Green: base (null)
  Yellow: 70
  Red: 90
  
Options:
  Show threshold markers: true
```

### Time series panel configuration

Best for observing trends.

```
Field config:
  Unit: s (for latency), percent (for rates)
  
Custom:
  Draw style: Line
  Line width: 2
  Fill opacity: 10
  
Legend:
  Display mode: Table
  Placement: Bottom
  Calcs: Last *, Max
  
Tooltip:
  Mode: All
  Sort: Descending
```

---

## 6. PromQL Examples for Common Dashboard Panels

### Latency

```promql
# P50 latency across all inference services
histogram_quantile(0.50, sum by (le, endpoint, tenant) (
  rate(telemetry_obsv_request_duration_seconds_bucket{endpoint=~"/.*inference.*", tenant=~"$tenant"}[5m])
))

# P99 latency for a specific service
histogram_quantile(0.99, sum by (le, endpoint, tenant) (
  rate(telemetry_obsv_request_duration_seconds_bucket{service="nmt-service", tenant=~"$tenant"}[5m])
))

# Average latency by service
rate(telemetry_obsv_request_duration_seconds_sum{tenant=~"$tenant"}[5m])
/
rate(telemetry_obsv_request_duration_seconds_count{tenant=~"$tenant"}[5m])
```

### Error Rates

```promql
# Overall error rate (non-200/201 responses)
100 * (
  sum by (endpoint, tenant)(rate(telemetry_obsv_requests_total{status_code!~"200|201", endpoint=~"/.*inference.*", tenant=~"$tenant"}[5m]))
  /
  sum by (endpoint, tenant)(rate(telemetry_obsv_requests_total{endpoint=~"/.*inference.*", tenant=~"$tenant"}[5m]))
)

# 5xx error rate only
100 * (
  sum by (endpoint, tenant)(rate(telemetry_obsv_requests_total{status_code=~"5..", endpoint=~"/.*inference.*", tenant=~"$tenant"}[5m]))
  /
  sum by (endpoint, tenant)(rate(telemetry_obsv_requests_total{endpoint=~"/.*inference.*", tenant=~"$tenant"}[5m]))
)
```

### Request Throughput

```promql
# Requests per second by service
sum by (service) (rate(telemetry_obsv_requests_total{tenant=~"$tenant"}[5m]))

# Total request count (instant)
sum(telemetry_obsv_requests_total{tenant=~"$tenant"})
```

### Business Metrics

```promql
# NMT characters translated per second
sum by (service_id) (rate(telemetry_obsv_nmt_characters_translated_sum{tenant=~"$tenant"}[5m]))

# ASR audio hours processed (cumulative)
sum(telemetry_obsv_asr_audio_seconds_processed_sum{tenant=~"$tenant"}) / 3600

# P95 characters per TTS request
histogram_quantile(0.95, sum by (le) (
  rate(telemetry_obsv_tts_characters_synthesized_bucket{tenant=~"$tenant"}[5m])
))

# LLM tokens consumed per minute
sum(rate(telemetry_obsv_llm_tokens_processed_total{tenant=~"$tenant"}[5m])) * 60
```

### Infrastructure

```promql
# CPU usage (matches alert expression)
100 * (1 - (sum(rate(node_cpu_seconds_total{mode="idle"}[5m])) / sum(rate(node_cpu_seconds_total[5m]))))

# Memory usage
max(100 * (1 - (node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes)))

# Disk usage
max(100 * (1 - (node_filesystem_avail_bytes{fstype!~"tmpfs|ramfs|overlay", mountpoint="/"}
  / node_filesystem_size_bytes{fstype!~"tmpfs|ramfs|overlay", mountpoint="/"})))
```

---

## 7. Provisioning Dashboards as JSON (Code-Based)

Dashboards created in the UI are stored in Grafana's internal database. For version-controlled, reproducible dashboards, export them as JSON and provision them from files.

### Step 1: Design in the UI first

Build your dashboard in the Grafana UI. This is the fastest way to iterate on layout and queries.

### Step 2: Export as JSON

1. Open the dashboard
2. Click **Share** (arrow icon) > **Export** > **Save to file**
3. In the exported JSON, set:
   - `"id": null` (auto-assigned on import)
   - A unique `"uid"` (e.g., `"my-custom-dashboard"`)

### Step 3: Place in the provisioning directory

Save the JSON file to:

```
infrastructure/grafana/provisioning/dashboards/my-custom-dashboard.json
```

The existing provisioner (`dashboard.yaml`) auto-loads all JSON files from this directory every 10 seconds.

### Step 4: Standardize the datasource reference

Replace any auto-generated datasource UIDs with the provisioned name:

```json
"datasource": {
  "type": "prometheus",
  "uid": "prometheus"
}
```

If your exported JSON has a UID like `"uid": "kdjfS_R7c"`, replace all occurrences with `"prometheus"`.

### Dashboard JSON structure reference

```json
{
  "id": null,
  "uid": "my-custom-dashboard",
  "title": "My Custom Dashboard",
  "description": "Description of what this dashboard monitors.",
  "tags": ["custom", "ai4icore"],
  "editable": true,
  "schemaVersion": 42,
  "version": 1,
  "refresh": "30s",
  "time": { "from": "now-1h", "to": "now" },
  "timezone": "browser",
  "templating": {
    "list": [
      {
        "name": "tenant",
        "type": "query",
        "datasource": { "type": "prometheus", "uid": "prometheus" },
        "query": "label_values(telemetry_obsv_requests_total, tenant)",
        "includeAll": true,
        "allValue": ".*",
        "multi": true,
        "refresh": 1,
        "sort": 1
      }
    ]
  },
  "panels": []
}
```

### Panel JSON structure reference

```json
{
  "id": 1,
  "type": "stat",
  "title": "Panel Title",
  "description": "What this panel shows",
  "datasource": { "type": "prometheus", "uid": "prometheus" },
  "gridPos": { "h": 6, "w": 12, "x": 0, "y": 0 },
  "targets": [
    {
      "datasource": { "type": "prometheus", "uid": "prometheus" },
      "editorMode": "code",
      "expr": "your_promql_expression_here",
      "instant": true,
      "range": false,
      "legendFormat": "__auto",
      "refId": "A"
    }
  ],
  "fieldConfig": {
    "defaults": {
      "unit": "s",
      "thresholds": {
        "mode": "absolute",
        "steps": [
          { "color": "green", "value": null },
          { "color": "yellow", "value": 0.5 },
          { "color": "red", "value": 2.0 }
        ]
      }
    }
  },
  "options": {
    "colorMode": "value",
    "graphMode": "area",
    "reduceOptions": { "calcs": ["lastNotNull"] }
  }
}
```

### Grid layout system

Grafana uses a 24-column grid. Panel sizes are defined by `gridPos`:

```
gridPos: { h: height, w: width, x: column, y: row }
```

| Layout | gridPos values |
|---|---|
| 2 panels side-by-side | w=12 each; x=0 and x=12 |
| 3 panels in a row | w=8 each; x=0, x=8, x=16 |
| 4 panels in a row | w=6 each; x=0, x=6, x=12, x=18 |
| 6 panels in a row | w=4 each; x=0, x=4, x=8, x=12, x=16, x=20 |
| Full-width panel | w=24, x=0 |

Row panels (section headers) use `h=1, w=24`.

---

## 8. Dashboard Design Best Practices

### Layout and organization

- **Top row**: High-level summary stats (overall latency, error rate, throughput)
- **Middle sections**: Per-service or per-tenant breakdowns
- **Bottom**: Infrastructure/system resource panels
- Use **row panels** to create collapsible sections — set `collapsed: true` for per-service breakdowns to avoid overwhelming the viewer
- Include a **description** on every panel explaining what it shows and what thresholds mean

### Template variables

- Always add a `tenant` variable for multi-tenant filtering
- Add an `organization` variable if the dashboard is used across organizations
- Use cascading variables (e.g., `endpoint` filtered by `$service`) to reduce noise
- Set refresh to **1 (on dashboard load)** so variables pick up new label values

### Thresholds

| Metric type | Green | Yellow | Red |
|---|---|---|---|
| Latency (P50) | < 0.5s | 0.5 - 2.0s | > 2.0s |
| Latency (P99) | < 1.0s | 1.0 - 5.0s | > 5.0s |
| Error rate | < 1% | 1 - 5% | > 5% |
| CPU / Memory / Disk | < 70% | 70 - 90% | > 90% |

Adjust thresholds based on your SLA targets and service characteristics.

### Naming conventions

- Dashboard title: descriptive, include the scope (e.g., "NMT Service Performance", "Tenant Usage Overview")
- Dashboard UID: kebab-case, unique (e.g., `nmt-performance`, `tenant-usage`)
- Panel titles: short but specific (e.g., "P99 Latency" not "Latency", "5xx Error Rate" not "Errors")
- Tags: include `ai4icore` plus domain tags (e.g., `nmt`, `tenant`, `performance`)

---

## 9. Access and Permissions

### Grafana roles

| Role | Can view dashboards | Can edit dashboards | Can manage data sources |
|---|---|---|---|
| Viewer | Yes | No | No |
| Editor | Yes | Yes | No |
| Admin | Yes | Yes | Yes |

### Dashboard-level permissions

1. Open the dashboard
2. Click **Share** > **Permissions**
3. Add users, teams, or roles with specific access levels

### Folder-based organization

Group dashboards by team or domain using folders:

1. Go to **Dashboards** > **New folder**
2. Name it (e.g., "NMT Team", "Infrastructure")
3. Move dashboards into the folder
4. Set folder-level permissions — all dashboards inside inherit the folder's permissions

### Provisioned dashboards

Dashboards provisioned from JSON files (in `infrastructure/grafana/provisioning/dashboards/`) allow UI updates because `allowUiUpdates: true` is set in `dashboard.yaml`. Changes made in the UI will persist until the next container restart, which reloads from files.

To make UI changes permanent: export the modified dashboard JSON and update the file in the provisioning directory.

---

## 10. Example: Building an NMT Service Dashboard

Here is a walkthrough of creating a focused dashboard for the NMT (Neural Machine Translation) service.

### Template variables

| Name | Query |
|---|---|
| `tenant` | `label_values(telemetry_obsv_requests_total{service="nmt-service"}, tenant)` |
| `service_id` | `label_values(telemetry_obsv_requests_total{service="nmt-service"}, service_id)` |

### Panels

**Row: Overview**

| Panel | Type | PromQL | Unit |
|---|---|---|---|
| Request Rate | Stat | `sum(rate(telemetry_obsv_requests_total{service="nmt-service", tenant=~"$tenant"}[5m]))` | reqps |
| P99 Latency | Stat | `histogram_quantile(0.99, sum by (le) (rate(telemetry_obsv_request_duration_seconds_bucket{service="nmt-service", tenant=~"$tenant"}[5m])))` | s |
| Error Rate | Stat | `100 * (sum(rate(telemetry_obsv_requests_total{service="nmt-service", status_code!~"200\|201", tenant=~"$tenant"}[5m])) / sum(rate(telemetry_obsv_requests_total{service="nmt-service", tenant=~"$tenant"}[5m])))` | percent |

**Row: Translation Volume**

| Panel | Type | PromQL | Unit |
|---|---|---|---|
| Characters/sec | Stat | `sum(rate(telemetry_obsv_nmt_characters_translated_sum{tenant=~"$tenant"}[5m]))` | short |
| P95 chars per request | Stat | `histogram_quantile(0.95, sum by (le) (rate(telemetry_obsv_nmt_characters_translated_bucket{tenant=~"$tenant"}[5m])))` | short |
| Chars by language pair | Time series | `sum by (source_language, target_language) (rate(telemetry_obsv_nmt_characters_translated_sum{tenant=~"$tenant"}[5m]))` | short |

**Row: By Model (service_id)**

| Panel | Type | PromQL | Unit |
|---|---|---|---|
| Latency by model | Time series | `histogram_quantile(0.95, sum by (le, service_id) (rate(telemetry_obsv_request_duration_seconds_bucket{service="nmt-service", tenant=~"$tenant", service_id=~"$service_id"}[5m])))` | s |
| Throughput by model | Time series | `sum by (service_id) (rate(telemetry_obsv_requests_total{service="nmt-service", tenant=~"$tenant", service_id=~"$service_id"}[5m]))` | reqps |

---

## 11. Validation Checklist

Before sharing a custom dashboard with your team:

- [ ] Dashboard has a descriptive title and description
- [ ] A unique `uid` is set (for provisioned dashboards)
- [ ] Template variables are configured for tenant/organization filtering
- [ ] All panels have titles and descriptions
- [ ] Units are set correctly (seconds, percent, short, bytes)
- [ ] Thresholds are configured with meaningful values
- [ ] PromQL queries use `$tenant` / `$organization` variables where applicable
- [ ] Datasource is set to `{"type": "prometheus", "uid": "prometheus"}` (not a runtime UID)
- [ ] Panels load data without errors (no "No data" on active services)
- [ ] Dashboard is tagged for discoverability
- [ ] Folder permissions are set if the dashboard is team-specific

---

## 12. Troubleshooting

| Problem | Cause | Solution |
|---|---|---|
| Panel shows "No data" | Metric not being scraped, or wrong PromQL | Test query in Prometheus UI (`http://localhost:9090/graph`) first |
| Variable dropdown is empty | Metric has no data for that label | Verify the label exists: `curl http://localhost:9090/api/v1/label/<label>/values` |
| Dashboard resets after container restart | UI changes to provisioned dashboards are not saved to file | Export the JSON and update the file in `infrastructure/grafana/provisioning/dashboards/` |
| "Datasource not found" error | Datasource UID mismatch | Replace the UID in JSON with `"prometheus"` |
| Panels load slowly | Query scans too much data | Add label selectors to narrow scope; use shorter time ranges |
| Histogram quantile returns NaN | No observations in the time window | Normal for idle services; check that requests are flowing |

---

## 13. Related Files

| File | Purpose |
|---|---|
| `infrastructure/grafana/provisioning/datasources/prometheus.yaml` | Prometheus datasource configuration |
| `infrastructure/grafana/provisioning/dashboards/dashboard.yaml` | Dashboard provisioning config (auto-loads JSON files) |
| `infrastructure/grafana/provisioning/dashboards/*.json` | Provisioned dashboard definitions |
| `infrastructure/prometheus/prometheus.yml` | Prometheus scrape targets and intervals |
| `libs/ai4icore_observability/ai4icore_observability/metrics.py` | All metric definitions and labels |
| `docs/CUSTOM_METRICS_GUIDE.md` | Guide for creating custom metrics |
| `docs/SMR_LATENCY_METRICS_QUERY_GUIDE.md` | PromQL reference for latency queries |
