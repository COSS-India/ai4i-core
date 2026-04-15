# Alerting System — Technical Architecture and Design

## 1. Overview

The AI4I alerting system is a multi-service pipeline that enables users to define alert rules via API, automatically generates Prometheus and Alertmanager configuration from those definitions, evaluates metrics in real-time, routes notifications to the correct recipients (including tenant-specific routing), and records a full alert history.

### Components involved

| Service | Port | Role |
|---|---|---|
| **alert-management-service** | 8098 | CRUD API for alert definitions, receivers, routing rules. Receives Alertmanager webhooks and stores alert history. |
| **alert-config-sync-service** | 8097 | Reads alert config from DB, generates Prometheus rule YAML and Alertmanager YAML, writes files, triggers hot reload. |
| **Prometheus** | 9090 | Scrapes metrics from all services. Evaluates alert rules. Sends firing alerts to Alertmanager. |
| **Alertmanager** | 9093 | Receives firing alerts from Prometheus. Groups, deduplicates, and routes them. Sends email notifications and webhooks. |

### Data stores

| Store | Used by | Purpose |
|---|---|---|
| **alerting_db** (PostgreSQL) | alert-management-service, alert-config-sync-service | Alert definitions, receivers, routing rules, alert history, audit log |
| **auth_db** (PostgreSQL) | alert-management-service, alert-config-sync-service | RBAC role-based email resolution (ADMIN, MODERATOR, etc.) |
| **multi_tenant_db** (PostgreSQL) | alert-management-service, alert-config-sync-service | Tenant name → tenant_id → tenant user email resolution |

---

## 2. End-to-End Data Flow

```
                    ┌─────────────────────────────┐
                    │   User / API Client          │
                    │   (Create alert definition)  │
                    └──────────┬──────────────────┘
                               │ POST /alerts/definitions
                               ▼
                    ┌──────────────────────────────┐
                    │  alert-management-service     │
                    │  (8098)                       │
                    │                               │
                    │  1. Validate input             │
                    │  2. Build PromQL expression    │
                    │  3. Store in alerting_db       │
                    │  4. Trigger config sync        │
                    └──────────┬──────────────────┘
                               │ POST /sync
                               ▼
                    ┌──────────────────────────────┐
                    │  alert-config-sync-service    │
                    │  (8097)                       │
                    │                               │
                    │  1. Fetch definitions from DB  │
                    │  2. Fetch receivers + rules    │
                    │  3. Resolve emails (auth_db)   │
                    │  4. Resolve tenants            │
                    │  5. Generate Prometheus YAML   │
                    │  6. Generate Alertmanager YAML │
                    │  7. Write files                │
                    │  8. Hot-reload Prometheus      │
                    │  9. Hot-reload Alertmanager    │
                    └──────────┬──────────────────┘
                               │ writes to filesystem
                               ▼
              ┌────────────────────────────────────────┐
              │                                        │
    ┌─────────▼──────────┐              ┌──────────────▼──────┐
    │  Prometheus (9090)  │              │  Alertmanager (9093) │
    │                     │   fires      │                      │
    │  Evaluates rules    │─────────────►│  Groups & routes     │
    │  every 5s           │   alerts     │  alerts              │
    │                     │              │                      │
    └─────────────────────┘              └───────┬──────┬──────┘
                                                 │      │
                                          email  │      │ webhook
                                                 │      │
                                                 ▼      ▼
                                          ┌──────────────────┐
                                   SMTP   │  alert-management │
                                  (SES)   │  -service (8098)  │
                                          │                   │
                                          │ POST /alerts/     │
                                          │   history/webhook │
                                          │                   │
                                          │ Stores in         │
                                          │ alert_history     │
                                          └──────────────────┘
```

### Flow summary

1. **Define**: User creates an alert definition via alert-management-service API.
2. **Build PromQL**: The service generates a PromQL expression from the threshold, signal type, and category.
3. **Store**: Definition is persisted to `alerting_db`.
4. **Sync**: alert-management-service calls alert-config-sync-service's `/sync` endpoint.
5. **Generate**: Sync service reads all enabled definitions, receivers, and routing rules from the DB. It generates two Prometheus rule files (application + infrastructure) and one Alertmanager config file.
6. **Reload**: Sync service writes the YAML files and triggers hot-reload via HTTP POST to Prometheus and Alertmanager's `/-/reload` endpoints.
7. **Evaluate**: Prometheus evaluates the alert rules every 5 seconds. When a rule's PromQL expression is true for the `for` duration, it fires the alert.
8. **Route**: Alertmanager receives the firing alert, groups it by `[alertname, category, severity, tenant]`, matches it against routing rules, and sends notifications.
9. **Notify**: Alertmanager sends emails via SMTP (AWS SES) and posts a webhook to alert-management-service.
10. **Record**: alert-management-service receives the webhook and stores the alert event in `alert_history`.

---

## 3. alert-management-service — Detailed Design

### 3.1 API surface

**Alert Definitions** (`/alerts/definitions`)

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| POST | `/` | ADMIN, MODERATOR | Create alert definition |
| GET | `/` | Any authenticated | List definitions (optional: `enabled_only`, `organization`) |
| GET | `/{id}` | Any authenticated | Get definition by ID |
| PUT | `/{id}` | ADMIN, MODERATOR | Update definition |
| DELETE | `/{id}` | ADMIN only | Delete definition |
| PATCH | `/{id}/enabled` | ADMIN, MODERATOR | Toggle enabled/disabled |

**Notification Receivers** (`/alerts/receivers`)

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| POST | `/` | ADMIN, MODERATOR | Create receiver (auto-creates a routing rule) |
| GET | `/` | Any authenticated | List receivers |
| GET | `/{id}` | Any authenticated | Get receiver by ID |
| PUT | `/{id}` | ADMIN, MODERATOR | Update receiver |
| DELETE | `/{id}` | ADMIN only | Delete receiver (cascades to routing rules) |

**Routing Rules** (`/alerts/routing-rules`)

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| POST | `/` | ADMIN, MODERATOR | Create routing rule |
| GET | `/` | Any authenticated | List rules (ordered by priority ASC) |
| GET | `/{id}` | Any authenticated | Get rule by ID |
| PUT | `/{id}` | ADMIN, MODERATOR | Update rule |
| DELETE | `/{id}` | ADMIN only | Delete rule |
| PATCH | `/timing` | ADMIN, MODERATOR | Bulk-update timing params for matching rules |

**Alert History** (`/alerts/history`)

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| GET | `/` | Any authenticated | Query alert history (filters: category, severity, date range, search) |
| POST | `/webhook` | None (internal) | Alertmanager webhook receiver (v4 payload format) |

### 3.2 PromQL generation

The service generates PromQL expressions from user-provided parameters (`sub_category` + `signal` + `signal_metric` + `condition_operator` + `threshold_value`).

Supported signal metrics:

| sub_category | signal | signal_metric | Quantile / Filter |
|---|---|---|---|
| performance | latency | latency_p50 | 0.5 |
| performance | latency | latency_p99 | 0.99 |
| availability | error_rate | error_rate_4xx | `status_code=~"4.."` |
| availability | error_rate | error_rate_5xx | `status_code=~"5.."` |
| availability | error_rate | error_rate_timeout | `status_code=~"408\|504"` |
| compute | cpu_utilization | total_cpu_usage | Same as infra/CPU |
| compute | memory_utilization | total_memory_usage | Same as infra/Memory |
| storage | disk_utilization | total_disk_usage | Same as infra/Disk |

**Service injection**: If the alert definition specifies `service` (e.g., `["asr-service", "nmt-service"]`), the service labels are injected into the PromQL selectors:
- Single service: `service="asr-service"`
- Multiple services: `service=~"asr-service|nmt-service"`

**Threshold unit conversion**:
- Latency: if unit is "ms", converts to seconds (÷ 1000)
- Error rate: if unit is "%", converts to ratio (÷ 100)

### 3.3 Notification receiver email resolution

When a receiver is created, the service resolves who should receive the emails:

| Priority | Field | Resolution |
|---|---|---|
| 1 | `tenant` | Queries `multi_tenant_db.tenants` for `organization_name` → gets `user_id` → queries `auth_db.users` where `is_tenant=true` → returns that user's email |
| 2 | `rbac_role` | Queries `auth_db` for all active users with the specified role (ADMIN, MODERATOR, USER, GUEST) → returns their emails |
| 3 | `email_to` | Uses the provided email list as-is |
| 4 | (fallback) | Queries `auth_db` for all ADMIN users → returns their emails |

### 3.4 Webhook processing

Alertmanager posts to `POST /alerts/history/webhook` with its v4 webhook payload. The service extracts:

- `alert_name` from `labels.alertname`
- `category`, `severity`, `tenant`, `organization` from labels
- `triggered_at` from `startsAt`
- `resolved_at` from `endsAt` (if not the zero timestamp)
- `status` from the payload (firing/resolved)
- Full `labels` and `annotations` as JSONB
- `fingerprint` for deduplication

Each alert in the payload is inserted as a row in `alert_history`.

### 3.5 Config sync trigger

After every CRUD operation (create, update, delete, toggle), the service calls:

```
POST http://alert-config-sync-service:8097/sync
```

This is a fire-and-forget call with a 30-second timeout. If the sync service is unavailable, the operation still succeeds (the next periodic sync will pick up the changes).

Controlled by `ALERT_SYNC_ENABLED=true` environment variable.

---

## 4. alert-config-sync-service — Detailed Design

### 4.1 Responsibilities

1. Read all enabled alert definitions, receivers, and routing rules from `alerting_db`
2. Resolve email recipients from `auth_db` (RBAC roles) and `multi_tenant_db` (tenant users)
3. Generate Prometheus alert rule YAML files (one per category: application, infrastructure)
4. Generate the full Alertmanager configuration YAML (receivers, routes, email templates)
5. Write files to the shared volumes
6. Trigger hot-reload on Prometheus and Alertmanager

### 4.2 Sync trigger mechanisms

| Trigger | Behavior |
|---|---|
| **On-demand** (`POST /sync`) | Called by alert-management-service after CRUD operations. Acquires lock (waits up to 10s). Returns 409 if another sync is in progress. |
| **Periodic** (every 60s) | Background async task started on service startup. Non-blocking — skips if a manual sync is already running. Interval configurable via `SYNC_INTERVAL`. |
| **Startup** | Initial blocking sync runs immediately on service start to ensure configs are current. |

Concurrency is managed with an `asyncio.Lock` to prevent simultaneous syncs from corrupting YAML files.

### 4.3 Prometheus rule YAML generation

For each enabled alert definition, the sync service generates a Prometheus alert rule:

```yaml
groups:
  - name: application-alerts
    interval: 30s
    rules:
      - alert: MyLatencyAlert
        expr: |
          histogram_quantile(0.99, sum by (le, endpoint, tenant) (
            rate(telemetry_obsv_request_duration_seconds_bucket{
              endpoint=~"/.*inference.*",
              service=~"asr-service|nmt-service"
            }[5m])
          )) > 0.5
        for: 5m
        labels:
          severity: critical
          urgency: medium
          category: application
          alert_type: latency
        annotations:
          summary: MyLatencyAlert
          description: "..."
          signal_display: "Latency - P99"
          service_type_full: "ASR (Automatic Speech Recognition)"
          category_display: "Service Performance"
          current_value: "{{ $value }}"
          threshold_display: "0.5s"
          condition_display: "Latency - P99 > 0.5s sustained for 5m"
          sustained_for: "5m"
```

**Key transformations applied**:

- **Tenant injection**: The `sum by` clause in PromQL is modified to include `tenant` so that the tenant label propagates through to Alertmanager. For example:
  - `sum by (le, endpoint)` → `sum by (le, endpoint, tenant)`
  - `sum by (endpoint)` → `sum by (endpoint, tenant)`
  - Already-injected expressions are skipped (idempotent)

- **Service regex sanitization**: Escaped hyphens (`\-`) in service regex matchers are normalized to plain hyphens (`-`)

- **Annotation enrichment**: Display-friendly annotations are derived from the alert definition fields:
  - `signal_display`: e.g., "Latency - P99", "Error Rate - 4XX"
  - `threshold_display`: e.g., "0.5s" (latency), "0.05ratio" (error rate), "90%" (infrastructure)
  - `condition_display`: Full human-readable condition string
  - `service_type_full`: Resolved from a hardcoded `SERVICE_TYPE_MAP` or templated from the endpoint label for multi-service alerts

- **Category grouping**: Alerts are split into two YAML files:
  - `application-alerts.yml` — latency, error rate alerts
  - `infrastructure-alerts.yml` — CPU, memory, disk alerts

### 4.4 Alertmanager YAML generation

The sync service generates the complete `alertmanager.yml` including global config, receivers, routes, and inhibit rules.

**Global section**:
```yaml
global:
  resolve_timeout: 5m
  smtp_smarthost: email-smtp.ap-south-1.amazonaws.com:587
  smtp_from: alerts@ai4inclusion.org
  smtp_auth_username: <from env>
  smtp_auth_password: <from env>
  smtp_require_tls: true
```

SMTP credentials are sourced from environment variables (`SMTP_SMARTHOST`, `SMTP_FROM`, `SMTP_AUTH_USERNAME`, `SMTP_AUTH_PASSWORD`).

**Receivers generated**:

| Receiver | Source | Purpose |
|---|---|---|
| `alert-history-webhook` | Hardcoded | Posts to `alert-management-service:8098/alerts/history/webhook` for all alerts |
| `default-admin` | ADMIN role users from auth_db | Fallback receiver — all alerts route here if no specific match |
| `{severity}-{category}` | DB receivers without `--` in name | Legacy merged receivers (one per severity+category combo) |
| `{receiver_name}` | DB receivers with `--` in name | Unique receivers (tenant-specific or alert-name-specific) |

**Email templates**: Each receiver gets an HTML email template injected into the Alertmanager config. Templates use Alertmanager Go-template syntax:

```
Subject: [CRITICAL] {{ .GroupLabels.alertname }} — Production - Service Impacted
Body:
  Alert Name: {{ .GroupLabels.alertname }}
  Category: {{ index (index .Alerts 0).Annotations "category_display" }}
  Signal: {{ index (index .Alerts 0).Annotations "signal_display" }}
  Service Type: {{ index (index .Alerts 0).Annotations "service_type_full" }}
  Tenant: Global (All Tenants)  |  OR  |  {tenant_name}
  Current Value: {{ index (index .Alerts 0).Annotations "current_value" }}
  Threshold: {{ index (index .Alerts 0).Annotations "threshold_display" }}
  Condition: {{ index (index .Alerts 0).Annotations "condition_display" }}
  Triggered At: {{ (index .Alerts 0).StartsAt }}
```

Global receivers show "Global (All Tenants)". Tenant-specific receivers show the tenant name.

**Route tree**:

```yaml
route:
  receiver: default-admin
  group_by: [alertname, category, severity, tenant]
  group_wait: 10s
  group_interval: 10s
  repeat_interval: 12h
  routes:
    - receiver: alert-history-webhook    # Always first — captures all alerts
      continue: true                      # continue=true so other routes also fire

    - match:                              # Specific route for a tenant
        severity: critical
        category: application
        tenant: cloudsphere-analytics-2-fe7854
      receiver: critical-application--tenant-CloudSphere-Analytics-2
      continue: true

    - match:                              # Generic severity+category route
        severity: warning
        category: infrastructure
      receiver: warning-infrastructure
      continue: true
```

Routes are ordered by priority (lower value first). Routes with tenant or alert_name specificity come before generic routes. All routes use `continue: true` so multiple receivers can fire for the same alert.

**Inhibit rules**:

```yaml
inhibit_rules:
  - source_match:
      severity: critical
    target_match:
      severity: warning
    equal: [alertname, category]
```

Critical alerts suppress warning alerts for the same alertname and category.

### 4.5 File writing and reload

| Target | Path | Method |
|---|---|---|
| Application alert rules | `/etc/prometheus/rules/application-alerts.yml` | Atomic write (write to `.tmp`, then rename) |
| Infrastructure alert rules | `/etc/prometheus/rules/infrastructure-alerts.yml` | Atomic write |
| Alertmanager config | `/etc/alertmanager/alertmanager.yml` | Direct write with retry (3 attempts, exponential backoff) |

**Hot reload**:
- Prometheus: `POST http://prometheus:9090/-/reload` (enabled via `--web.enable-lifecycle` flag)
- Alertmanager: `POST http://alertmanager:9093/-/reload`

Both calls are fire-and-forget with warning logs on failure.

---

## 5. Prometheus Configuration

### Scrape configuration

Prometheus scrapes metrics from all services every 5 seconds across two jobs:

| Job | Path | Services |
|---|---|---|
| `ai4i-services` | `/metrics` | 17 services (standard Prometheus client metrics) |
| `ai4icore-enterprise` | `/enterprise/metrics` | 19 services (AI4I platform metrics: `telemetry_obsv_*`) |

A `service` label is derived from each target's hostname via relabeling (e.g., `nmt-service:8089` → `service="nmt-service"`).

### Alert evaluation

```yaml
global:
  evaluation_interval: 5s

alerting:
  alertmanagers:
    - static_configs:
        - targets: ["alertmanager:9093"]

rule_files:
  - '/etc/prometheus/rules/*.yml'
```

Prometheus loads all `*.yml` files from the rules directory, evaluates them every 5 seconds, and forwards firing alerts to Alertmanager.

### Data retention

Storage retention is set to **30 days** (`--storage.tsdb.retention.time=30d`).

---

## 6. Alertmanager Configuration

### Startup behavior

The Alertmanager container uses a custom entrypoint that checks if `alertmanager.yml` exists. If not, it copies `alertmanager.default.yml` (a minimal bootstrap config with just the webhook receiver and default-admin receiver). This ensures the container starts cleanly on a fresh deployment before the sync service has run.

### Grouping and deduplication

- **Group by**: `[alertname, category, severity, tenant]`
- **Group wait**: 10s (waits for more alerts in the same group before sending)
- **Group interval**: 10s (minimum interval between notifications for the same group)
- **Repeat interval**: 12h (resends if alert is still firing after 12 hours)

### Notification channels

| Channel | Configuration |
|---|---|
| **Email (SMTP)** | AWS SES (`email-smtp.ap-south-1.amazonaws.com:587`) with TLS |
| **Webhook** | `http://alert-management-service:8098/alerts/history/webhook` |

Emails are sent with `send_resolved: false` (no resolution notifications).

---

## 7. Database Schema

### Entity relationship

```
alert_definitions ──1:N──► alert_annotations
                               (CASCADE delete)

notification_receivers ──1:N──► routing_rules
                                  (CASCADE delete)

alert_history (standalone — populated by webhook)

alert_config_audit_log (standalone — populated on every CRUD operation)
```

### Table: alert_definitions

| Column | Type | Notes |
|---|---|---|
| id | Integer PK | Auto-increment |
| name | String(255) | **Globally unique** |
| organization | String(100) | Scoping (not used in PromQL) |
| category | String(50) | `application` or `infrastructure` |
| sub_category | String(100) | `performance`, `availability`, `compute`, `storage` |
| signal | String(100) | `latency`, `error_rate`, `cpu_utilization`, etc. |
| signal_metric | String(100) | `latency_p50`, `latency_p99`, `error_rate_4xx`, etc. |
| condition_operator | String(10) | `>`, `>=`, `<`, `<=` |
| alert_type | String(50) | Legacy: `Latency`, `Error Rate`, `CPU`, `Memory`, `Disk` |
| promql_expr | Text | Generated PromQL expression |
| threshold_value | Float | Numeric threshold |
| threshold_unit | String(50) | `ms`, `s`, `%` |
| severity | String(20) | `critical`, `warning`, `info` |
| urgency | String(20) | `high`, `medium`, `low` |
| service | Text[] | Optional array of service names |
| for_duration | String(20) | e.g., `5m` — how long condition must hold before firing |
| evaluation_interval | String(20) | e.g., `30s` |
| scope | String(50) | `global`, `per_service` |
| enabled | Boolean | Only enabled alerts are synced |

### Table: notification_receivers

| Column | Type | Notes |
|---|---|---|
| id | Integer PK | |
| receiver_name | String(255) | Unique per organization |
| rule_name | String(255) | Associated routing rule name |
| organization | String(100) | |
| category | String(50) | Alert category to match |
| severity | String(20) | Alert severity to match |
| email_to | Text[] | Explicit email addresses |
| rbac_role | String(50) | Role name for email resolution |
| tenant | String(255) | Tenant name for email resolution |
| alert_names | Text[] | Specific alert names to match |
| email_subject_template | Text | Custom Alertmanager Go-template subject |
| email_body_template | Text | Custom Alertmanager Go-template body |
| enabled | Boolean | |

### Table: routing_rules

| Column | Type | Notes |
|---|---|---|
| id | Integer PK | |
| rule_name | String(255) | Unique per organization |
| receiver_id | Integer FK | References `notification_receivers.id` (CASCADE) |
| match_severity | String(20) | Route match criteria |
| match_category | String(50) | Route match criteria |
| match_alert_type | String(50) | Route match criteria |
| match_alert_names | Text[] | Route match criteria (regex) |
| match_tenant_id | String(255) | |
| group_by | Text[] | Default: `[alertname, category, severity]` |
| group_wait | String(20) | Default: `10s` |
| group_interval | String(20) | Default: `10s` |
| repeat_interval | String(20) | Default: `12h` |
| priority | Integer | Lower = higher priority. Default: 100 |
| enabled | Boolean | |

### Table: alert_history

| Column | Type | Notes |
|---|---|---|
| id | BigInteger PK | |
| alert_name | String(255) | From `labels.alertname` |
| category | String(50) | From `labels.category` |
| severity | String(20) | From `labels.severity` |
| tenant | String(255) | From `labels.tenant` |
| triggered_at | DateTime | From `startsAt` |
| resolved_at | DateTime | From `endsAt` (null if still firing) |
| status | String(20) | `firing` or `resolved` |
| receiver | String(255) | Alertmanager receiver name |
| notified_display | String(500) | Human-readable: "Admin" or "Tenant Admin - {name}" |
| labels | JSONB | Full Prometheus labels |
| annotations | JSONB | Full Prometheus annotations |
| fingerprint | String(64) | Alert fingerprint for deduplication |

### Table: alert_config_audit_log

| Column | Type | Notes |
|---|---|---|
| id | Integer PK | |
| table_name | String | Which table was modified |
| record_id | Integer | ID of the modified record |
| operation | String | CREATE, UPDATE, DELETE, ENABLE, DISABLE, SYNC |
| changed_by | String | Username from JWT |
| before_values | JSONB | State before change |
| after_values | JSONB | State after change |
| change_description | String | Human-readable description |

---

## 8. Multi-Tenant Alert Routing

The system supports routing alerts to specific tenants. Here is how the tenant label flows through the entire pipeline:

### Step 1: Metric collection (middleware)

The observability middleware extracts `tenant` from the JWT token or `X-Customer-ID` header and attaches it as a Prometheus label on all `telemetry_obsv_*` metrics.

### Step 2: PromQL tenant preservation (sync service)

When generating Prometheus rule YAML, the sync service injects `tenant` into the `sum by` clause:

```
Before: sum by (le, endpoint) (rate(...))
After:  sum by (le, endpoint, tenant) (rate(...))
```

This ensures the `tenant` label survives the aggregation and is present on the firing alert.

### Step 3: Alertmanager routing (sync service)

When a receiver has a `tenant` field, the sync service:
1. Resolves `tenant_name` → `tenant_id` via `multi_tenant_db`
2. Resolves `tenant_id` → `user_id` → tenant user email via `auth_db`
3. Adds a route with `match: { tenant: <tenant_id> }` in the Alertmanager config
4. Creates a dedicated receiver with the tenant user's email

### Step 4: Alert delivery

When Prometheus fires an alert with `tenant="cloudsphere-analytics-2-fe7854"`, Alertmanager matches it to the tenant-specific route and sends the email to the tenant's registered email address.

---

## 9. Authentication and Authorization

| Role | Create/Update alerts | Delete alerts | View alerts |
|---|---|---|---|
| ADMIN | Yes | Yes | Yes |
| MODERATOR | Yes | No | Yes |
| USER | No | No | Yes |
| GUEST | No | No | Yes |

Authentication uses JWT tokens verified by the `ai4icore_auth` library. The middleware extracts `username`, `user_id`, `roles`, and `is_admin` from the token and sets them on `request.state`.

The webhook endpoint (`POST /alerts/history/webhook`) has no authentication as it is called internally by Alertmanager.

---

## 10. Audit Trail

Every CRUD operation on alert definitions, receivers, and routing rules is logged to both:

1. **`alert_config_audit_log` table** — persistent database record
2. **OpenSearch** (via `ai4icore_logging` + Kafka) — structured JSON logs with trace IDs

Logged fields: operation type, resource type, resource ID, organization, actor (username), before/after values, change description, Jaeger trace ID.

---

## 11. Infrastructure Configuration

### Docker Compose services

```yaml
prometheus:
  image: prom/prometheus:latest
  ports: 9090:9090
  command:
    - --storage.tsdb.retention.time=30d
    - --web.enable-lifecycle              # enables /-/reload
  volumes:
    - ./infrastructure/prometheus/prometheus.yml:/etc/prometheus/prometheus.yml:ro
    - ./infrastructure/prometheus/rules:/etc/prometheus/rules    # RW — sync service writes here

alertmanager:
  image: prom/alertmanager:v0.27.0
  ports: 9095:9093
  volumes:
    - ./infrastructure/alertmanager:/etc/alertmanager            # RW — sync service writes here

alert-management-service:
  build: ./services/alert-management-service
  ports: 8104:8098
  environment:
    - ALERT_CONFIG_SYNC_SERVICE_URL=http://alert-config-sync-service:8097
    - ALERT_SYNC_ENABLED=true

alert-config-sync-service:
  build: ./services/alert-config-sync-service
  ports: 8101:8097
  environment:
    - PROMETHEUS_URL=http://prometheus:9090
    - ALERTMANAGER_URL=http://alertmanager:9093
    - PROMETHEUS_APPLICATION_ALERTS_PATH=/etc/prometheus/rules/application-alerts.yml
    - PROMETHEUS_INFRASTRUCTURE_ALERTS_PATH=/etc/prometheus/rules/infrastructure-alerts.yml
    - ALERTMANAGER_CONFIG_PATH=/etc/alertmanager/alertmanager.yml
    - SYNC_INTERVAL=60
  volumes:
    - ./infrastructure/prometheus/rules:/etc/prometheus/rules    # shared with Prometheus
    - ./infrastructure/alertmanager:/etc/alertmanager            # shared with Alertmanager
  depends_on: [postgres, prometheus, alertmanager]
```

The sync service shares filesystem volumes with Prometheus and Alertmanager. This is how it writes rule files and config that those services can read.

### File paths (inside containers)

| File | Written by | Read by |
|---|---|---|
| `/etc/prometheus/rules/application-alerts.yml` | alert-config-sync-service | Prometheus |
| `/etc/prometheus/rules/infrastructure-alerts.yml` | alert-config-sync-service | Prometheus |
| `/etc/alertmanager/alertmanager.yml` | alert-config-sync-service | Alertmanager |

---

## 12. Sequence Diagram — Alert Definition Lifecycle

```
User                    alert-mgmt-svc           alerting_db          sync-svc            Prometheus      Alertmanager
  │                          │                       │                    │                    │                │
  │  POST /alerts/definitions│                       │                    │                    │                │
  │─────────────────────────►│                       │                    │                    │                │
  │                          │  validate + build     │                    │                    │                │
  │                          │  PromQL               │                    │                    │                │
  │                          │                       │                    │                    │                │
  │                          │  INSERT alert_def     │                    │                    │                │
  │                          │──────────────────────►│                    │                    │                │
  │                          │                       │                    │                    │                │
  │                          │  POST /sync           │                    │                    │                │
  │                          │──────────────────────────────────────────►│                    │                │
  │                          │                       │                    │                    │                │
  │                          │                       │  SELECT all defs   │                    │                │
  │                          │                       │◄───────────────────│                    │                │
  │                          │                       │                    │                    │                │
  │                          │                       │                    │  write YAML files  │                │
  │                          │                       │                    │───────────────────►│                │
  │                          │                       │                    │                    │                │
  │                          │                       │                    │  POST /-/reload    │                │
  │                          │                       │                    │───────────────────►│                │
  │                          │                       │                    │                    │                │
  │                          │                       │                    │  POST /-/reload    │                │
  │                          │                       │                    │──────────────────────────────────►│
  │                          │                       │                    │                    │                │
  │  201 Created             │                       │                    │                    │                │
  │◄─────────────────────────│                       │                    │                    │                │
  │                          │                       │                    │                    │                │
  │                          │                       │                    │  (later, every 5s) │                │
  │                          │                       │                    │    evaluates rule   │                │
  │                          │                       │                    │    condition met    │                │
  │                          │                       │                    │    for `for` dur.   │                │
  │                          │                       │                    │                    │  ALERT fires   │
  │                          │                       │                    │                    │───────────────►│
  │                          │                       │                    │                    │                │
  │                          │                       │                    │                    │  groups, routes │
  │                          │                       │                    │                    │  sends email   │
  │                          │                       │                    │                    │                │
  │                          │  POST /alerts/history/webhook             │                    │                │
  │                          │◄──────────────────────────────────────────────────────────────────────────────│
  │                          │                       │                    │                    │                │
  │                          │  INSERT alert_history  │                    │                    │                │
  │                          │──────────────────────►│                    │                    │                │
```

---

## 13. Related Files

| File | Purpose |
|---|---|
| `services/alert-management-service/alert_management.py` | Core business logic: CRUD, PromQL generation, webhook processing |
| `services/alert-management-service/main.py` | FastAPI app, router registration, DB init |
| `services/alert-management-service/models.py` | SQLAlchemy models (6 tables) |
| `services/alert-management-service/routers/` | API route handlers |
| `services/alert-management-service/utils/auth_deps.py` | JWT auth dependencies |
| `services/alert-management-service/utils/audit_logger.py` | Audit trail logging |
| `services/alert-config-sync-service/main.py` | Sync logic: YAML generation, file writing, hot reload |
| `infrastructure/prometheus/prometheus.yml` | Prometheus scrape config and alertmanager target |
| `infrastructure/prometheus/rules/application-alerts.yml` | Application alert rules (generated) |
| `infrastructure/prometheus/rules/infrastructure-alerts.yml` | Infrastructure alert rules (generated) |
| `infrastructure/alertmanager/alertmanager.yml` | Alertmanager config (generated) |
| `infrastructure/alertmanager/alertmanager.default.yml` | Bootstrap fallback config |
| `infrastructure/databases/migrations/postgres/alembic/versions/alerting_db/` | DB migration |
