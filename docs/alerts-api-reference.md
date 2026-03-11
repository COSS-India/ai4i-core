# Alert Definitions, Notification Receivers & Alert History — API Reference

Technical reference for frontend integration with Alert Definition and Notification Receiver CRUD APIs, and the read-only Alert History API. All endpoints are on the **Alert Management Service** (direct), not via API Gateway.

**Base URL (local):** `http://localhost:8104`  
**Auth:** Send `Authorization: Bearer <JWT_TOKEN>` in request headers when calling the service directly.

---

## Signal path value constraints (Alert Definitions)

When using the **signal path** (i.e. when you provide `sub_category`, `signal`, `signal_metric`, and `condition_operator` instead of `alert_type`), values must follow the backend hierarchy below. Use these for dropdowns/cascading selects.

**Backend normalizes values:** spaces → underscores, lowercased (e.g. `"Latency P50"` → `latency_p50`). The **value** column is the canonical form to send in the API.

### 1. Category → Sub-category

| `category` | Allowed `sub_category` values | Display label |
|------------|-------------------------------|---------------|
| `application` | `performance` | Performance |
| `application` | `availability` | Availability |
| `infrastructure` | `compute` | Compute |
| `infrastructure` | `storage` | Storage |

### 2. Sub-category → Signal

| `sub_category` | Allowed `signal` values | Display label |
|----------------|-------------------------|---------------|
| `performance` | `latency` | Latency |
| `availability` | `error_rate` | Error rate |
| `compute` | `cpu_utilization` | CPU Utilization |
| `compute` | `memory_utilization` | Memory Utilization |
| `storage` | `disk_utilization` | Disk Utilization |

### 3. Signal → Signal metric

| `signal` | Allowed `signal_metric` values | Display label |
|----------|--------------------------------|---------------|
| `latency` | `latency_p50` | Latency P50 |
| `latency` | `latency_p99` | Latency P99 |
| `error_rate` | `error_rate_4xx` | 4xx error rate |
| `error_rate` | `error_rate_5xx` | 5xx error rate |
| `error_rate` | `error_rate_timeout` | Timeout error rate |
| `cpu_utilization` | `total_cpu_usage` | Total CPU Usage |
| `memory_utilization` | `total_memory_usage` | Total Memory Usage |
| `disk_utilization` | `total_disk_usage` | Total Disk Usage |

### 4. Condition operator

| `condition_operator` (exact values) |
|------------------------------------|
| `>` |
| `>=` |
| `<` |
| `<=` |

**Validation:** Backend rejects if `sub_category` is not valid for the given `category`, or `signal` is not in the sub_category’s signals, or `signal_metric` is not in the signal’s metrics.

---

## 1. Alert Definitions

### 1.1 Create Alert Definition

| | |
|---|---|
| **Method** | `POST` |
| **Path** | `/alerts/definitions` |
| **Auth** | Requires `alerts.create` |

**Query parameters**

| Parameter | Type | Required | Notes |
|-----------|------|----------|--------|
| `organization` | string | No (admin only) | If set and user is admin, create for that org; otherwise org derived from API key. |

**Request body: `AlertDefinitionCreate`**

| Field | Type | Required | Default | Allowed / Constraints | Notes |
|--------|------|----------|---------|----------------------|--------|
| `name` | string | Yes | – | Non-empty; globally unique (no duplicate alert names across organizations) | Display name of the alert. |
| `description` | string | No | `null` | – | Free text. |
| `threshold_value` | number | Yes | – | – | Numeric threshold used in generated PromQL. |
| `threshold_unit` | string | Yes | – | `"ms"`, `"s"`, `"%"` | For latency: `"ms"` or `"s"`. For error rate/CPU/Memory/Disk: `"%"`. |
| `category` | string | No | `"application"` | `"application"`, `"infrastructure"` | Drives which signals/metrics are valid. |
| `severity` | string | Yes | – | `"critical"`, `"warning"`, `"info"` | Used for routing and UI badge. |
| `urgency` | string | No | `"medium"` | `"high"`, `"medium"`, `"low"` | Informational. |
| `alert_type` | string | Conditional* | `null` | Application: `"Latency"`, `"Error Rate"`. Infrastructure: `"CPU"`, `"Memory"`, `"Disk"` | *Either `alert_type` **or** all four signal-path fields below. |
| `sub_category` | string | Conditional* | `null` | **Depends on `category`.** Application: `"performance"`, `"availability"`. Infrastructure: `"compute"`, `"storage"`. See §Signal path value constraints. | Must be one of the allowed sub-categories for the selected category. |
| `signal` | string | Conditional* | `null` | **Depends on `sub_category`.** e.g. `"latency"` (performance), `"error_rate"` (availability), `"cpu_utilization"` / `"memory_utilization"` (compute), `"disk_utilization"` (storage). See §Signal path value constraints. | Must be one of the signals for the selected sub_category. |
| `signal_metric` | string | Conditional* | `null` | **Depends on `signal`.** e.g. `"latency_p50"`, `"latency_p99"` (latency); `"error_rate_4xx"`, `"error_rate_5xx"`, `"error_rate_timeout"` (error_rate); `"total_cpu_usage"`, `"total_memory_usage"`, `"total_disk_usage"` (infra). See §Signal path value constraints. | Must be one of the metrics for the selected signal. |
| `condition_operator` | string | Conditional* | `null` | **Exactly:** `">"`, `">="`, `"<"`, `"<="` | Comparison in threshold expression. |
| `scope` | string | No | `null` | e.g. `"all_services"`, `"per_service"` | Affects service label in PromQL. |
| `service` | string[] | No | `null` | List of service names | Optional; adds service label (or regex) to PromQL. |
| `evaluation_interval` | string | No | `"30s"` | Prometheus duration (e.g. `"15s"`, `"1m"`) | How often rule is evaluated. |
| `for_duration` | string | No | `"5m"` | Prometheus duration (e.g. `"1m"`, `"10m"`) | How long condition must hold before firing. |
| `enabled` | boolean | No | `true` | – | Whether definition is active. |
| `annotations` | object[] | No | `[]` | Each item: `{ "key": string, "value": string }` | Keys e.g. `"summary"`, `"description"`, `"impact"`, `"action"`. |

**Validation rule:** Either provide `alert_type`, or provide all four: `sub_category`, `signal`, `signal_metric`, `condition_operator`. If neither is satisfied, backend returns `400`. When using the signal path, values must follow the **Signal path value constraints** tables above (category → sub_category → signal → signal_metric; condition_operator one of `>`, `>=`, `<`, `<=`).

**Response:** `AlertDefinitionResponse` (see §1.7). Status `201` on success.

---

### 1.2 List Alert Definitions

| | |
|---|---|
| **Method** | `GET` |
| **Path** | `/alerts/definitions` |
| **Auth** | Requires `alerts.read` |

**Query parameters**

| Parameter | Type | Required | Default | Notes |
|-----------|------|----------|---------|--------|
| `enabled_only` | boolean | No | `false` | If `true`, only returns definitions with `enabled = true`. |

**Org scoping:** Non-admin users see only their organization (from API key). Admins see all organizations.

**Response:** Array of `AlertDefinitionResponse`.

---

### 1.3 Get Alert Definition by ID

| | |
|---|---|
| **Method** | `GET` |
| **Path** | `/alerts/definitions/{alert_id}` |
| **Auth** | Requires `alerts.read` |

**Path parameters**

| Parameter | Type | Required |
|-----------|------|----------|
| `alert_id` | integer | Yes |

**Query parameters**

| Parameter | Type | Required | Notes |
|-----------|------|----------|--------|
| `organization` | string | No | Admin can pass to enforce org scope. |

**Response:** `AlertDefinitionResponse`. `404` if not found or org mismatch.

---

### 1.4 Update Alert Definition

| | |
|---|---|
| **Method** | `PUT` |
| **Path** | `/alerts/definitions/{alert_id}` |
| **Auth** | Requires `alerts.update` |

**Path parameters:** `alert_id` (integer).

**Query parameters:** `organization` (string, optional, admin only).

**Request body: `AlertDefinitionUpdate`** — all fields optional. Only send fields you want to change.

| Field | Type | Notes |
|--------|------|--------|
| `description` | string | |
| `threshold_value` | number | |
| `threshold_unit` | string | `"ms"`, `"s"`, `"%"`, etc. |
| `category` | string | `"application"` or `"infrastructure"` |
| `severity` | string | `"critical"`, `"warning"`, `"info"` |
| `urgency` | string | `"high"`, `"medium"`, `"low"` |
| `alert_type` | string | Same allowed values as create |
| `sub_category` | string | Same as create; depends on `category`. See §Signal path value constraints. |
| `signal` | string | Same as create; depends on `sub_category`. See §Signal path value constraints. |
| `signal_metric` | string | Same as create; depends on `signal`. See §Signal path value constraints. |
| `condition_operator` | string | `">"`, `">="`, `"<"`, `"<="` |
| `scope` | string | |
| `service` | string[] | |
| `evaluation_interval` | string | |
| `for_duration` | string | |
| `enabled` | boolean | (Alternatively use PATCH enabled endpoint.) |
| `annotations` | object[] | `{ "key": string, "value": string }` each |

**Response:** `AlertDefinitionResponse`.

---

### 1.5 Delete Alert Definition

| | |
|---|---|
| **Method** | `DELETE` |
| **Path** | `/alerts/definitions/{alert_id}` |
| **Auth** | Requires `alerts.delete` |

**Path parameters:** `alert_id` (integer).

**Query parameters:** `organization` (string, optional, admin only).

**Response:** `{ "message": "Alert definition deleted successfully" }`.

---

### 1.6 Enable / Disable Alert Definition

| | |
|---|---|
| **Method** | `PATCH` |
| **Path** | `/alerts/definitions/{alert_id}/enabled` |
| **Auth** | Requires `alerts.update` |

**Path parameters:** `alert_id` (integer).

**Query parameters:** `organization` (string, optional, admin only).

**Request body**

```json
{
  "enabled": true
}
```

| Field | Type | Required | Notes |
|--------|------|----------|--------|
| `enabled` | boolean | Yes | `true` = enable, `false` = disable. |

**Response:** `AlertDefinitionResponse` with updated `enabled` state.

---

### 1.7 Alert Definition Response Shape (`AlertDefinitionResponse`)

Returned by create, get, list, update, and toggle endpoints.

| Field | Type | Notes |
|--------|------|--------|
| `id` | integer | Primary key. |
| `organization` | string | Resolved from API key or admin `organization` query. |
| `name` | string | As stored. |
| `description` | string \| null | |
| `promql_expr` | string | **Generated** PromQL expression (read-only). |
| `threshold_value` | number \| null | |
| `threshold_unit` | string \| null | |
| `category` | string | `"application"` or `"infrastructure"` |
| `severity` | string | `"critical"`, `"warning"`, `"info"` |
| `urgency` | string | `"high"`, `"medium"`, `"low"` |
| `alert_type` | string \| null | |
| `sub_category` | string \| null | |
| `signal` | string \| null | |
| `signal_metric` | string \| null | |
| `condition_operator` | string \| null | |
| `scope` | string \| null | |
| `service` | string[] \| null | |
| `evaluation_interval` | string | e.g. `"30s"` |
| `for_duration` | string | e.g. `"5m"` |
| `enabled` | boolean | |
| `created_at` | string (ISO 8601) | |
| `updated_at` | string (ISO 8601) | |
| `created_by` | string \| null | |
| `annotations` | object[] | `{ "key": string, "value": string }` each |

---

## 2. Notification Receivers

Receivers define **who** gets notified (emails or RBAC role). Creating a receiver also auto-creates a routing rule.

### 2.1 Create Notification Receiver

| | |
|---|---|
| **Method** | `POST` |
| **Path** | `/alerts/receivers` |
| **Auth** | Requires `alerts.create` |

**Query parameters:** `organization` (string, optional, admin only).

**Request body: `NotificationReceiverCreate`**

| Field | Type | Required | Default | Allowed / Constraints | Notes |
|--------|------|----------|---------|------------------------|--------|
| `category` | string | Yes | – | `"application"`, `"infrastructure"` | Which alerts this receiver targets. |
| `severity` | string | Yes | – | `"critical"`, `"warning"`, `"info"` | Severity filter in routing. |
| `alert_type` | string | No | `null` | e.g. `"latency"`, `"error_rate"`, `"cpu"`, `"memory"`, `"disk"` | Optional filter. |
| `alert_names` | string[] | No | `null` | Alert definition names | If set, route only those alerts to this receiver. |
| `tenant` | string | No | `null` | Tenant name (matched to multi_tenant_db) | When set, routing uses tenant; emails resolved from tenant users in auth_db. |
| `rule_name` | string | No | `null` | Any non-empty string | Stored on receiver and used for auto-created routing rule name; if omitted, backend derives it. |
| `email_to` | string[] | Conditional* | `null` | At least 1 element if provided | Direct email list. **Mutually exclusive** with `rbac_role`. |
| `rbac_role` | string | Conditional* | `null` | `"ADMIN"`, `"MODERATOR"`, `"USER"`, `"GUEST"` | Emails resolved from users with this role. **Mutually exclusive** with `email_to`. |
| `email_subject_template` | string | No | `null` | Any text | Override default subject. |
| `email_body_template` | string | No | `null` | HTML/text | Override default body (Alertmanager Go template). |

**Constraint:** Exactly one of `email_to` or `rbac_role` must be provided; both cannot be set. Backend returns validation error otherwise.

**Response:** `NotificationReceiverResponse` (see §2.6). Status `201` on success.

---

### 2.2 List Notification Receivers

| | |
|---|---|
| **Method** | `GET` |
| **Path** | `/alerts/receivers` |
| **Auth** | Requires `alerts.read` |

**Query parameters**

| Parameter | Type | Required | Default | Notes |
|-----------|------|----------|---------|--------|
| `enabled_only` | boolean | No | `false` | If `true`, only enabled receivers. |

**Org scoping:** Non-admin sees only their organization; admin sees all.

**Response:** Array of `NotificationReceiverResponse`.

---

### 2.3 Get Notification Receiver by ID

| | |
|---|---|
| **Method** | `GET` |
| **Path** | `/alerts/receivers/{receiver_id}` |
| **Auth** | Requires `alerts.read` |

**Path parameters:** `receiver_id` (integer).

**Query parameters:** `organization` (string, optional, admin only).

**Response:** `NotificationReceiverResponse`. `404` if not found or org mismatch.

---

### 2.4 Update Notification Receiver

| | |
|---|---|
| **Method** | `PUT` |
| **Path** | `/alerts/receivers/{receiver_id}` |
| **Auth** | Requires `alerts.update` |

**Path parameters:** `receiver_id` (integer).

**Query parameters:** `organization` (string, optional, admin only).

**Request body: `NotificationReceiverUpdate`** — all fields optional.

| Field | Type | Notes |
|--------|------|--------|
| `receiver_name` | string | Must remain unique within org. |
| `rule_name` | string | |
| `alert_names` | string[] | Same semantics as create. |
| `tenant` | string | |
| `email_to` | string[] | If set, do **not** set `rbac_role` in same request. |
| `rbac_role` | string | `"ADMIN"`, `"MODERATOR"`, `"USER"`, `"GUEST"`; cannot set `email_to` in same request. |
| `email_subject_template` | string | |
| `email_body_template` | string | |
| `enabled` | boolean | |

**Response:** `NotificationReceiverResponse`.

---

### 2.5 Delete Notification Receiver

| | |
|---|---|
| **Method** | `DELETE` |
| **Path** | `/alerts/receivers/{receiver_id}` |
| **Auth** | Requires `alerts.delete` |

**Path parameters:** `receiver_id` (integer).

**Query parameters:** `organization` (string, optional, admin only).

**Response:** `{ "message": "Notification receiver deleted successfully" }`.

---

### 2.6 Notification Receiver Response Shape (`NotificationReceiverResponse`)

| Field | Type | Notes |
|--------|------|--------|
| `id` | integer | Primary key. |
| `organization` | string | |
| `receiver_name` | string | Auto-generated unique name. |
| `rule_name` | string \| null | Stored rule name. |
| `email_to` | string[] | **Resolved** list (from role or tenant if applicable). |
| `rbac_role` | string \| null | Stored role if any. |
| `alert_names` | string[] \| null | |
| `tenant` | string \| null | |
| `email_subject_template` | string \| null | |
| `email_body_template` | string \| null | |
| `enabled` | boolean | |
| `created_at` | string (ISO 8601) | |
| `updated_at` | string (ISO 8601) | |
| `created_by` | string \| null | |

---

## 3. Alert History

Alert history is a **read-only audit log** of triggered alerts. When Alertmanager fires or resolves an alert, it sends a webhook to the Alert Management Service, which records one row per alert. The list endpoint returns these records with optional filters and pagination.

### 3.1 List Alert History

| | |
|---|---|
| **Method** | `GET` |
| **Path** | `/alerts/history` |
| **Auth** | Requires `alerts.read` |

**Query parameters**

| Parameter | Type | Required | Default | Notes |
|-----------|------|----------|---------|--------|
| `category` | string | No | – | Filter by category: `"application"` or `"infrastructure"`. |
| `severity` | string | No | – | Filter by severity: `"critical"`, `"warning"`, or `"info"`. |
| `date_from` | string | No | – | Filter: `triggered_at >=` this value. ISO 8601 or `YYYY-MM-DD`. |
| `date_to` | string | No | – | Filter: `triggered_at <=` this value. ISO 8601 or `YYYY-MM-DD`. |
| `search` | string | No | – | Case-insensitive search in alert name and notified audience. |
| `limit` | integer | No | `50` | Page size; min 1, max 200. |
| `offset` | integer | No | `0` | Number of records to skip (for pagination). |

**Response**

Paginated list with total count. Results are ordered by `triggered_at` descending (newest first).

| Field | Type | Notes |
|--------|------|--------|
| `items` | object[] | Array of alert history items (see §3.2). |
| `total` | integer | Total number of records matching the filters (before pagination). |
| `limit` | integer | Page size used. |
| `offset` | integer | Offset used. |

**Example**

```http
GET /alerts/history?limit=50&offset=0&category=application&severity=warning
```

```json
{
  "items": [
    {
      "id": 1,
      "name": "FullSignalPathAlert2",
      "category": "application",
      "severity": "warning",
      "triggered_at": "2026-03-11 06:50:57",
      "resolved_at": null,
      "status": "firing",
      "receiver": "alert-history-webhook",
      "notified": "Admin",
      "tenant": "unknown",
      "organization": null,
      "created_at": "2026-03-11T06:51:24.227488+00:00"
    }
  ],
  "total": 1,
  "limit": 50,
  "offset": 0
}
```

---

### 3.2 Alert History Item Shape

Each element in `items` has the following fields.

| Field | Type | Notes |
|--------|------|--------|
| `id` | integer | Primary key of the history record. |
| `name` | string | Alert name (from Prometheus/Alertmanager labels). |
| `category` | string | `"application"` or `"infrastructure"`. |
| `severity` | string | `"critical"`, `"warning"`, or `"info"`. |
| `triggered_at` | string \| null | When the alert fired; format `"YYYY-MM-DD HH:MM:SS"`. |
| `resolved_at` | string \| null | When the alert resolved (if applicable); same format. |
| `status` | string | `"firing"` or `"resolved"`. |
| `receiver` | string | Alertmanager receiver that received the alert (e.g. `"alert-history-webhook"`). |
| `notified` | string | Human-readable audience: `"Admin"` (global admin) or `"Tenant Admin - <tenant_name>"`. |
| `tenant` | string \| null | Tenant from alert labels, if any. |
| `organization` | string \| null | Organization from alert labels, if any. |
| `created_at` | string \| null | ISO 8601 timestamp when the history row was created. |

---

### 3.3 Alert History Webhook (internal)

| | |
|---|---|
| **Method** | `POST` |
| **Path** | `/alerts/history/webhook` |
| **Auth** | None (called by Alertmanager; restrict access by network/firewall). |

This endpoint receives Alertmanager webhook payloads (v4 format) and inserts one row per alert into the alert history table. It is intended for use by Alertmanager only, not by frontends or API consumers. The sync service configures Alertmanager to POST to this URL so that all fired/resolved alerts are recorded automatically.

---

## 4. Frontend integration notes

- **Base URL:** `http://localhost:8104` (Alert Management Service direct); use env/config for other environments.
- **Auth:** Send `Authorization: Bearer <JWT_TOKEN>` when calling the service directly.
- **Organization:** Usually do **not** send `organization` query param; it is derived from the token/API key. Admins can optionally pass `organization` for cross-tenant management.
- **IDs:** Use `id` for update/delete/get; `alert_names` in receivers refer to alert definition **`name`** values, not IDs.
- **Validation:** Alert definitions require either `alert_type` or the full signal path (`sub_category`, `signal`, `signal_metric`, `condition_operator`). Receivers require exactly one of `email_to` or `rbac_role`.
- **Alert History:** Use `GET /alerts/history` with optional `category`, `severity`, `date_from`, `date_to`, `search`, `limit`, and `offset` to show a paginated audit log of triggered alerts. Requires `alerts.read`.
