# platform-core-service — Alert APIs & Configuration (APISIX cutover reference)

Reference for the DevOps team. Lists every alert route now served by
`platform-core-service` (path, method, request body), the service-level API
configuration APISIX needs to know, and the full set of environment variables
the service reads.

The old `alert-management-service` is decommissioned for this scope; APISIX
should route `/api/v1/alerts/*` to `platform-core-service`.

---

## 1. API configuration

| Item | Value |
|---|---|
| Upstream service (Docker DNS) | `platform-core-service` |
| Container port | `8095` |
| Local dev published port | `8102` (host) → `8095` (container) |
| Global route prefix | `/api/v1` |
| OpenAPI / Swagger UI | `/docs` |
| OpenAPI JSON | `/openapi.json` |
| Health endpoint | `/api/v1/health` |
| Auth (gateway) | Enforce via existing `forward-auth` → `auth-service /api/v1/auth/validate`. Permissions are keyed on `METHOD:URI` in `auth-service/api_permissions.json` (already covers all alert paths below). |
| In-service auth | **None** — the service does not decode tokens or read identity headers. All authorization is the gateway's job. |
| Path rewriting | **None.** The service serves the full `/api/v1/alerts/...` path. The old `/api/v1/alerts/(.*) → /alerts/$1` rewrite must NOT be applied. |
| Webhook auth carve-out | `POST /api/v1/alerts/history/webhook` must be reachable **without auth** (Alertmanager posts to it). Equivalent of nginx `auth_request off;` for that one path. |

The existing APISIX `alerts-route` (uri `/api/v1/alerts/*`) wildcard already
matches every endpoint below; the per-endpoint listing is for the
`api_permissions.json` mapping that drives per-operation 403s.

---

## 2. Alert routes

All paths mounted under `/api/v1`. **Auth = Yes** → APISIX runs `forward-auth` against `auth-service /api/v1/auth/validate`. **Auth = No** → route must bypass `forward-auth` (only the Alertmanager webhook qualifies).

Enum value reference used in bodies below:
- `category` = application / infrastructure
- `severity` = critical / warning / info
- `urgency` = high / medium / low
- `alert_type` = Latency / Error Rate / CPU / Memory / Disk
- `sub_category` = performance / availability / compute / storage
- `signal` = latency / error_rate / cpu_utilization / memory_utilization / disk_utilization
- `signal_metric` = latency_p50 / latency_p99 / error_rate_4xx / error_rate_5xx / error_rate_timeout / total_cpu_usage / total_memory_usage / total_disk_usage
- `condition_operator` = > / >= / < / <=
- `service` (inference task names) = nmt / asr / ocr / ner / llm / language_detection / tts / transliteration / language_diarization / speaker_diarization / audio_language_detection / pii
- `rbac_role` = ADMIN / USER / GUEST / MODERATOR / TENANT ADMIN
- `threshold_unit` = ms / s / %

### 1. Create Alert Definition

| Field | Value |
|---|---|
| Method | POST |
| Path | /api/v1/alerts/definitions |
| Request Body | JSON — {"name": "string (required, unique)", "category": "application", "severity": "warning", "threshold_value": 500, "threshold_unit": "ms", "alert_type": "Latency" (OR use sub_category + signal + signal_metric + condition_operator tuple), "service": ["nmt"] (optional, inference task names), "urgency": "medium" (optional), "evaluation_interval": "30s" (optional), "for_duration": "5m" (optional), "description": "string" (optional), "annotations": [{"key": "summary", "value": "string"}] (optional)} |
| Auth | Yes |

### 2. List Alert Definitions

| Field | Value |
|---|---|
| Method | GET |
| Path | /api/v1/alerts/definitions |
| Query Params | enabled_only (bool, optional) |
| Request Body | None |
| Auth | Yes |

### 3. Get Alert Definition

| Field | Value |
|---|---|
| Method | GET |
| Path | /api/v1/alerts/definitions/{alert_id} |
| Request Body | None |
| Auth | Yes |

### 4. Update Alert Definition

| Field | Value |
|---|---|
| Method | PUT |
| Path | /api/v1/alerts/definitions/{alert_id} |
| Request Body | JSON — same fields as Create, every field optional (PATCH semantics) |
| Auth | Yes |

### 5. Delete Alert Definition

| Field | Value |
|---|---|
| Method | DELETE |
| Path | /api/v1/alerts/definitions/{alert_id} |
| Request Body | None |
| Auth | Yes |

### 6. Toggle Alert Definition Enabled

| Field | Value |
|---|---|
| Method | PATCH |
| Path | /api/v1/alerts/definitions/{alert_id}/enabled |
| Request Body | JSON — {"enabled": true} |
| Auth | Yes |

### 7. Create Notification Receiver

| Field | Value |
|---|---|
| Method | POST |
| Path | /api/v1/alerts/receivers |
| Request Body | JSON — {"category": "application", "severity": "warning", "email_to": ["a@b.com"] (XOR with rbac_role), "rbac_role": "ADMIN" (XOR with email_to), "tenant": "string" (optional), "alert_type": "string" (optional), "alert_names": ["string"] (optional), "rule_name": "string" (optional), "description": "string" (optional), "email_subject_template": "string" (optional), "email_body_template": "html string" (optional)} |
| Auth | Yes |
| Notes | Cannot supply both `email_to` and `rbac_role`. If neither (and no `tenant`) given, defaults to `rbac_role=ADMIN`. |

### 8. List Notification Receivers

| Field | Value |
|---|---|
| Method | GET |
| Path | /api/v1/alerts/receivers |
| Request Body | None |
| Auth | Yes |

### 9. Get Notification Receiver

| Field | Value |
|---|---|
| Method | GET |
| Path | /api/v1/alerts/receivers/{receiver_id} |
| Request Body | None |
| Auth | Yes |

### 10. Update Notification Receiver

| Field | Value |
|---|---|
| Method | PUT |
| Path | /api/v1/alerts/receivers/{receiver_id} |
| Request Body | JSON — same fields as Create (all optional), plus "receiver_name": "string" (optional), "enabled": true (optional) |
| Auth | Yes |

### 11. Delete Notification Receiver

| Field | Value |
|---|---|
| Method | DELETE |
| Path | /api/v1/alerts/receivers/{receiver_id} |
| Request Body | None |
| Auth | Yes |

### 12. Create Routing Rule

| Field | Value |
|---|---|
| Method | POST |
| Path | /api/v1/alerts/routing-rules |
| Request Body | JSON — {"rule_name": "string (required, unique)", "receiver_id": 1, "match_severity": "warning" or null, "match_category": "application" or null, "match_alert_type": "string" or null, "match_alert_names": ["string"] (optional), "match_tenant_id": "string" or null, "group_by": ["alertname","category","severity"] (optional), "group_wait": "10s" (optional), "group_interval": "10s" (optional), "repeat_interval": "12h" (optional), "continue_routing": false (optional), "priority": 100 (optional)} |
| Auth | Yes |

### 13. List Routing Rules

| Field | Value |
|---|---|
| Method | GET |
| Path | /api/v1/alerts/routing-rules |
| Request Body | None |
| Auth | Yes |

### 14. Bulk Update Routing Rule Timing

| Field | Value |
|---|---|
| Method | PATCH |
| Path | /api/v1/alerts/routing-rules/timing |
| Request Body | JSON — {"category": "application", "severity": "warning", "alert_type": "string" (optional), "priority": 100 (optional), "group_wait": "10s" (optional), "group_interval": "10s" (optional), "repeat_interval": "12h" (optional)} |
| Auth | Yes |
| Notes | Must be matched **before** `/api/v1/alerts/routing-rules/{rule_id}` in APISIX route ordering (otherwise the literal `timing` collides with the `{rule_id}` path param). |

### 15. Get Routing Rule

| Field | Value |
|---|---|
| Method | GET |
| Path | /api/v1/alerts/routing-rules/{rule_id} |
| Request Body | None |
| Auth | Yes |

### 16. Update Routing Rule

| Field | Value |
|---|---|
| Method | PUT |
| Path | /api/v1/alerts/routing-rules/{rule_id} |
| Request Body | JSON — same fields as Create (all optional), plus "enabled": true (optional) |
| Auth | Yes |

### 17. Delete Routing Rule

| Field | Value |
|---|---|
| Method | DELETE |
| Path | /api/v1/alerts/routing-rules/{rule_id} |
| Request Body | None |
| Auth | Yes |

### 18. Alertmanager History Webhook

| Field | Value |
|---|---|
| Method | POST |
| Path | /api/v1/alerts/history/webhook |
| Request Body | Alertmanager v4 webhook payload (opaque JSON; service extracts the `alerts[]` array) |
| Auth | **No** — bypass `forward-auth`. Alertmanager has no user token. |

### 19. List Alert History

| Field | Value |
|---|---|
| Method | GET |
| Path | /api/v1/alerts/history |
| Query Params | category, severity, date_from (ISO-8601), date_to (ISO-8601), search, limit (1–200, default 50), offset (default 0) |
| Request Body | None |
| Auth | Yes |

---

## 3. Environment variables (names only)

All env vars below are read by `platform-core-service/app/core/config.py`
(pydantic-settings, case-insensitive). Group headings reflect logical sections;
the var names are the literals to set.

### Service identity
- `SERVICE_NAME` *(required)*
- `SERVICE_VERSION` *(required)*
- `API_VERSION` *(required)*
- `DEBUG`
- `ENVIRONMENT`

### Primary database (`ai4iplatform_core`)
- `DATABASE_URL` *(full URL — if set, overrides the parts below)*
- `POSTGRES_USER`
- `POSTGRES_PASSWORD`
- `POSTGRES_HOST`
- `POSTGRES_PORT`
- `POSTGRES_DB`
- `APP_DB_USER`
- `APP_DB_PASSWORD`
- `APP_DB_HOST`
- `APP_DB_PORT`
- `APP_DB_NAME`
- `CORE_DB_NAME`
- `DB_POOL_SIZE`
- `DB_MAX_OVERFLOW`

### Secondary auth DB (`ai4iplatform_auth`, read-only — RBAC/tenant email resolution)
- `AUTH_DB_URL`
- `AUTH_DB_USER`
- `AUTH_DB_PASSWORD`
- `AUTH_DB_HOST`
- `AUTH_DB_PORT`
- `AUTH_DB_NAME`

### Redis
- `REDIS_HOST` *(required)*
- `REDIS_PORT` *(required)*
- `REDIS_PASSWORD`
- `REDIS_DB`
- `REDIS_TIMEOUT`
- `MODEL_CACHE_TTL_SECONDS`
- `SERVICE_CACHE_TTL_SECONDS`

### Alert config sync (Prometheus / Alertmanager reconciliation)
- `ALERT_SYNC_ENABLED`
- `SYNC_INTERVAL`
- `DEFAULT_RECEIVER_EMAILS`
- `PROMETHEUS_URL`
- `ALERTMANAGER_URL`
- `PROMETHEUS_APPLICATION_ALERTS_PATH`
- `PROMETHEUS_INFRASTRUCTURE_ALERTS_PATH`
- `ALERTMANAGER_CONFIG_PATH`
- `ALERT_HISTORY_WEBHOOK_URL`

### SMTP (Alertmanager email delivery — written into generated `alertmanager.yml` global block)
- `SMTP_SMARTHOST`
- `SMTP_FROM`
- `SMTP_AUTH_USERNAME`
- `SMTP_AUTH_PASSWORD`

### Model-management business rules
- `MAX_ACTIVE_VERSIONS_PER_MODEL`
- `ALLOW_DEPRECATED_MODEL_CHANGES`

### Endpoint validation
- `RUN_INFERENCE_TEST`
- `ENDPOINT_VALIDATION_TIMEOUT_SECONDS`
- `ENDPOINT_VALIDATION_MODE`
- `ENDPOINT_VALIDATION_SKIP_TLS_VERIFY`

### Logging / Observability
- `LOG_LEVEL`
- `JAEGER_ENDPOINT`
- `TELEMETRY_ENABLED`
