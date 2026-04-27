# How Alerting Works: End-to-End Flow

A complete, code-level walkthrough of how an alert moves from API call → database → Prometheus rule → Alertmanager → notification → history record.

There are two services and four distinct phases:

- **`alert-management-service`** — the REST API. Stores alert definitions, receivers, and routing rules in the database. Receives webhooks from Alertmanager.
- **`alert-config-sync-service`** — reads from the database, generates Prometheus rule files and Alertmanager config, writes them to disk, and hot-reloads both.

---

# The two services, in detail

## `alert-management-service`

**Role:** The REST API layer. Everything a user or frontend does with alerts goes through here.

**Port:** 8098

**Tables it writes to (in `alerting_db`):**
- `alert_definitions`
- `alert_annotations`
- `notification_receivers`
- `routing_rules`
- `alert_history` (populated from Alertmanager webhooks)
- `alert_config_audit_log` (populated on every CRUD operation)

**Responsibilities:**

| Area | What it handles |
|---|---|
| **Alert Definition CRUD** | `POST/GET/PUT/DELETE /alerts/definitions` — create, list, update, delete, toggle alert rules |
| **PromQL generation** | Translates user input (threshold, signal, operator, services) into Prometheus expressions. Handles both the structured pathway (`sub_category` + `signal` + `signal_metric` + `condition_operator`) and the legacy pathway (`alert_type`). Switches between backend metrics (`telemetry_obsv_requests_total`) and APISIX metrics (`apisix_http_status`) based on the environment. |
| **Notification Receiver CRUD** | `POST/GET/PUT/DELETE /alerts/receivers` — create receivers with email resolution via tenant, RBAC role, or explicit emails. Auto-creates a routing rule on receiver creation. |
| **Routing Rule CRUD** | `POST/GET/PUT/DELETE /alerts/routing-rules` — manage how alerts are routed to receivers, including `match_severity`, `match_category`, timing params (`group_wait`, `group_interval`, `repeat_interval`). Also has a bulk `PATCH /alerts/routing-rules/timing` endpoint. |
| **Alert History** | `GET /alerts/history` — paginated query of past alert events with filters (category, severity, date range, search). |
| **Webhook ingestion** | `POST /alerts/history/webhook` — unauthenticated endpoint called by Alertmanager. Parses Alertmanager v4 payload and inserts one row per alert into `alert_history`. |
| **Audit trail** | Every create/update/delete writes to `alert_config_audit_log` and to OpenSearch via the `ai4icore_logging` library, capturing actor, before/after values, and trace IDs. |
| **Auth & RBAC** | Uses JWT tokens via `ai4icore_auth`. Enforces role-based access: ADMIN can do everything, MODERATOR can create/update, USER/GUEST can only read. |
| **Trigger sync** | After every mutation, calls `POST http://alert-config-sync-service:8097/sync` to kick off the YAML generation pipeline. |

**What it does NOT do:** it never touches Prometheus or Alertmanager directly. It doesn't write YAML files, doesn't hot-reload anything. It just records intent to the database.

---

## `alert-config-sync-service`

**Role:** The YAML-generation and hot-reload worker. Converts database state into Prometheus rule files and Alertmanager config.

**Port:** 8097

**Tables it reads from:**
- `alerting_db.alert_definitions`, `alert_annotations`, `notification_receivers`, `routing_rules` (read-only)
- `auth_db.users`, `roles`, `user_roles` (read-only — for RBAC email resolution)
- `multi_tenant_db.tenants` (read-only — for tenant name → tenant_id mapping)

**Responsibilities:**

| Area | What it handles |
|---|---|
| **On-demand sync** | `POST /sync` endpoint called by alert-management-service after every CRUD mutation. Blocks up to 10s on an `asyncio.Lock` to serialize writes. |
| **Periodic sync** | Background task that runs every 60 seconds (configurable via `SYNC_INTERVAL`). Non-blocking — skips if a manual sync is already running. Ensures eventual consistency even if the on-demand sync call failed. |
| **Startup sync** | Runs one initial sync when the service boots, so configs are always current before the first request. |
| **Email resolution** | For each receiver, resolves the email recipient(s) by looking up the `rbac_role` in `auth_db` or the `tenant` in `multi_tenant_db` → `auth_db.users` (where `is_tenant=true`). |
| **Prometheus rule YAML generation** | For each enabled alert definition, generates a Prometheus alert rule YAML with labels, annotations, `for:` duration, and the PromQL expression. **Injects the `tenant` label** into every `sum by` clause so the firing alert carries it to Alertmanager for tenant-specific routing. Generates two files — one for `application` alerts, one for `infrastructure`. |
| **Alertmanager config YAML generation** | Builds the full `alertmanager.yml` including global SMTP settings, receivers (email + webhook), route tree (matching on severity, category, tenant, alertname), and inhibit rules. Uses two HTML email templates — a global one and a tenant-specific one. |
| **Atomic file writes** | Writes YAML to shared Docker volumes (`/etc/prometheus/rules/*.yml`, `/etc/alertmanager/alertmanager.yml`) using atomic rename for Prometheus rules and retry logic for Alertmanager config. |
| **Hot reload** | POSTs to `{PROMETHEUS_URL}/-/reload` and `{ALERTMANAGER_URL}/-/reload` so both pick up the new config without a container restart. |
| **Concurrency control** | `asyncio.Lock` prevents overlapping syncs. Manual syncs wait; periodic syncs skip. |

**What it does NOT do:** it never accepts user requests or modifies database rows. It doesn't know about JWTs, auth, or the REST contract. Its only job is transforming DB state into files and triggering reloads.

---

# Why two services?

The alerting pipeline needs to do two very different things:

| Concern | Nature | Service |
|---|---|---|
| CRUD API for alert definitions / receivers / routing rules | Synchronous, request/response, REST | **alert-management-service** |
| Translating DB state into Prometheus/Alertmanager YAML files + hot-reloading both | Asynchronous, periodic, file I/O + HTTP reload calls | **alert-config-sync-service** |

Keeping them separate means:

- **Clean responsibilities.** One owns the API surface and audit trail, the other owns the YAML generation and reload mechanics.
- **Decoupled deployment.** Restarting the sync service doesn't drop API availability.
- **Resilience.** If sync fails, the API call still succeeds; the next periodic sync (every 60s) picks up the changes. The user doesn't see an error.
- **Simpler locking.** The sync service uses an `asyncio.Lock` to serialize file writes without affecting API throughput.

**Trade-off:** there's a short window (seconds) between creating an alert in the API and it being live in Prometheus, since the sync is a separate step.

---

# The databases each service talks to

Both services share the same three databases. They only read and write the tables they own.

| DB | Tables | Used by alert-management | Used by alert-config-sync |
|---|---|---|---|
| **alerting_db** | `alert_definitions`, `alert_annotations`, `notification_receivers`, `routing_rules`, `alert_history`, `alert_config_audit_log` | Read + Write (CRUD + webhook inserts) | Read-only |
| **auth_db** | `users`, `roles`, `user_roles` | Read (RBAC email resolution for receiver creation) | Read (RBAC email resolution for Alertmanager receivers) |
| **multi_tenant_db** | `tenants` | Read (tenant → user_id lookup for tenant receivers) | Read (tenant name → tenant_id + user emails) |

---

# Phase 1: Alert creation (via API)

## Step 1 — Client calls the API

```http
POST /api/v1/alerts/definitions HTTP/1.1
Authorization: Bearer <jwt>
Content-Type: application/json

{
  "name": "High5xxErrorRate",
  "description": "5xx error rate exceeds 2%",
  "threshold_value": 2,
  "threshold_unit": "%",
  "category": "application",
  "severity": "critical",
  "urgency": "high",
  "sub_category": "availability",
  "signal": "error_rate",
  "signal_metric": "error_rate_5xx",
  "condition_operator": ">",
  "scope": "per_service",
  "service": ["nmt-service"],
  "evaluation_interval": "30s",
  "for_duration": "1m",
  "enabled": true
}
```

## Step 2 — FastAPI route dispatches to `create_alert_definition`

Request hits the router in `alert_management-service/routers/alert_definitions.py`, which calls `create_alert_definition()` at [alert_management.py:1147](../services/alert-management-service/alert_management.py#L1147).

## Step 3 — Build the PromQL expression

At [alert_management.py:1156-1169](../services/alert-management-service/alert_management.py#L1156-L1169):

```python
use_apisix = _should_use_apisix_error_rate(data.category, signal=data.signal, alert_type=data.alert_type)

if use_signal_config:
    promql_expr_with_org = build_promql_from_signal_config(
        category=data.category,
        sub_category=data.sub_category,
        signal=data.signal,
        signal_metric=data.signal_metric,
        condition_operator=data.condition_operator,
        threshold_value=data.threshold_value,
        threshold_unit=data.threshold_unit,
        organization=None,
        services=services_list if use_apisix else None,
    )
    if services_list and not use_apisix:
        promql_expr_with_org = inject_service_into_promql(promql_expr_with_org, services_list)
```

For our payload this produces (local env):
```promql
(sum by (endpoint, tenant)(rate(telemetry_obsv_requests_total{status_code=~"5..", endpoint=~"/.*inference.*", service="nmt-service"}[5m])) / sum by (endpoint, tenant)(rate(telemetry_obsv_requests_total{endpoint=~"/.*inference.*", service="nmt-service"}[5m]))) > 0.02
```

## Step 4 — Insert into `alerting_db.alert_definitions`

At [alert_management.py:1218-1237](../services/alert-management-service/alert_management.py#L1218-L1237):

```python
async with db_pool.acquire() as conn:
    row = await conn.fetchrow(
        """
        INSERT INTO alert_definitions (
            organization, name, description, promql_expr, threshold_value, threshold_unit,
            category, severity, urgency, alert_type, sub_category, signal, signal_metric, condition_operator,
            scope, service, evaluation_interval, for_duration,
            enabled, created_by
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $19, $20)
        RETURNING *
        """,
        organization, data.name, data.description, promql_expr_with_org,
        data.threshold_value, data.threshold_unit,
        data.category, data.severity, data.urgency, alert_type_display,
        sub_category_val, signal_val, signal_metric_val, condition_operator_val,
        data.scope,
        services_list if services_list else None,
        data.evaluation_interval, data.for_duration,
        data.enabled if data.enabled is not None else True,
        created_by
    )
    alert_id = row['id']
```

If annotations were provided, they're inserted into `alert_annotations` in the same transaction ([alert_management.py:1242-1252](../services/alert-management-service/alert_management.py#L1242-L1252)).

## Step 5 — Write audit log entry

The create is logged to `alert_config_audit_log` and OpenSearch (via `ai4icore_logging`) at [alert_management.py:1258-1265](../services/alert-management-service/alert_management.py#L1258-L1265).

## Step 6 — Trigger the sync service

The key handoff to the second service happens at [alert_management.py:2064](../services/alert-management-service/alert_management.py#L2064) (and every other CRUD operation):

```python
# Trigger configuration sync to update YAML files and reload Prometheus/Alertmanager
await trigger_config_sync(actor=created_by, request=request)
```

The `trigger_config_sync()` function at [alert_management.py:285-319](../services/alert-management-service/alert_management.py#L285-L319):

```python
async def trigger_config_sync(actor=None, request=None):
    if not SYNC_ENABLED:
        return
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(f"{SYNC_SERVICE_URL}/sync")
            # ... audit log on success ...
    except Exception as e:
        # Don't fail the main operation if sync fails
        # Sync will happen on next periodic run anyway
        logger.warning(f"Failed to trigger configuration sync: {e}")
```

This is **fire-and-forget with graceful fallback**: the API call returns success even if the sync service is temporarily down, because the periodic sync (every 60s) will pick up the change.

## Step 7 — Return response to client

The API returns the newly-created `AlertDefinitionResponse` with its generated `promql_expr`, timestamps, and annotations.

---

# Phase 2: Sync — DB state → YAML files → hot reload

This phase happens entirely in **alert-config-sync-service**, triggered either by Step 6 above or by the 60-second periodic timer.

## Step 8 — `sync_configuration()` acquires the lock

At [alert-config-sync-service/main.py:1199-1234](../services/alert-config-sync-service/main.py#L1199-L1234):

```python
async def sync_configuration(blocking: bool = True) -> None:
    global sync_in_progress
    if sync_in_progress:
        if blocking:
            await asyncio.sleep(0.5)
            if sync_in_progress:
                raise Exception("cannot perform operation: another operation is in progress")
        else:
            logger.debug("Sync already in progress, skipping periodic sync")
            return

    if blocking:
        await asyncio.wait_for(sync_lock.acquire(), timeout=10.0)
    else:
        await asyncio.wait_for(sync_lock.acquire(), timeout=0.1)
```

Manual sync waits up to 10s for the lock. Periodic sync skips immediately if another sync is running.

## Step 9 — Fetch everything from `alerting_db`

At [main.py:1250-1255](../services/alert-config-sync-service/main.py#L1250-L1255):

```python
alert_definitions = await fetch_alert_definitions()       # all enabled alerts + annotations
receivers = await fetch_notification_receivers()          # all enabled receivers
routing_rules = await fetch_routing_rules()               # all enabled rules, priority ASC
```

These are straight `SELECT ... WHERE enabled = true` queries against `alerting_db`.

## Step 10 — Resolve emails from `auth_db`

At [main.py:1264-1274](../services/alert-config-sync-service/main.py#L1264-L1274):

```python
# Resolve ADMIN emails for default receiver
default_admin_emails = await fetch_admin_emails()

# Build role -> [emails] for non-tenant receivers
roles_needed = set()
for r in receivers:
    if (r.get('rbac_role') or '').strip():
        roles_needed.add(r['rbac_role'].upper())
role_emails_map = {}
for role in roles_needed:
    role_emails_map[role] = await fetch_emails_by_role(role)
```

Each call does an `auth_db` JOIN across `users`, `user_roles`, and `roles` to pull emails.

## Step 11 — Resolve tenants from `multi_tenant_db`

At [main.py:1277-1293](../services/alert-config-sync-service/main.py#L1277-L1293):

```python
# Resolve tenant names to (tenant_id, emails) for receivers with tenant set
tenant_resolution_map = {}
unique_tenant_names = set()
for r in receivers:
    t = (r.get('tenant') or '').strip() or None
    if t:
        unique_tenant_names.add(t)
for tname in unique_tenant_names:
    resolved = await resolve_tenant_name_to_tenant_id_and_emails(tname)
    if resolved:
        tenant_resolution_map[tname] = resolved
```

For each tenant name, this:
1. Queries `multi_tenant_db.tenants` → `tenant_id`, `user_id`
2. Queries `auth_db.users` where `id = user_id AND is_tenant = true` → email

## Step 12 — Generate YAML

At [main.py:1295-1303](../services/alert-config-sync-service/main.py#L1295-L1303):

```python
application_alerts = generate_prometheus_alerts_yaml(alert_definitions, category='application')
infrastructure_alerts = generate_prometheus_alerts_yaml(alert_definitions, category='infrastructure')
alertmanager_config = generate_alertmanager_yaml(
    receivers, routing_rules,
    default_admin_emails=default_admin_emails,
    tenant_resolution_map=tenant_resolution_map,
    role_emails_map=role_emails_map,
)
```

The Prometheus rule generator also **injects the `tenant` label into every PromQL expression's `sum by` clause**, so that the firing alert carries the tenant label for routing downstream.

## Step 13 — Write files atomically

At [main.py:1305-1308](../services/alert-config-sync-service/main.py#L1305-L1308):

```python
await write_yaml_file(PROMETHEUS_APPLICATION_ALERTS_PATH, application_alerts)
await write_yaml_file(PROMETHEUS_INFRASTRUCTURE_ALERTS_PATH, infrastructure_alerts)
await write_yaml_file(ALERTMANAGER_CONFIG_PATH, alertmanager_config, validate=False)
```

Paths:
- `/etc/prometheus/rules/application-alerts.yml`
- `/etc/prometheus/rules/infrastructure-alerts.yml`
- `/etc/alertmanager/alertmanager.yml`

These directories are Docker volumes **shared with the Prometheus and Alertmanager containers**, so writes are visible to both immediately.

## Step 14 — Hot-reload Prometheus and Alertmanager

At [main.py:1310-1312](../services/alert-config-sync-service/main.py#L1310-L1312):

```python
prometheus_ok = await trigger_prometheus_reload()
alertmanager_ok = await trigger_alertmanager_reload()
```

Under the hood ([main.py:1154-1167](../services/alert-config-sync-service/main.py#L1154-L1167)):

```python
async def trigger_prometheus_reload() -> bool:
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(f"{PROMETHEUS_URL}/-/reload")
        if response.status_code == 200:
            logger.info("Prometheus configuration reloaded successfully")
            return True
```

And the same for Alertmanager at `{ALERTMANAGER_URL}/-/reload`. Both containers re-read their config files **in place, without restarting**.

After this step, the alert is live: Prometheus will start evaluating the rule every 5 seconds.

---

# Phase 3: Alert firing — Prometheus evaluates and sends to Alertmanager

## Step 15 — Prometheus evaluates rules every 5s

Every 5 seconds (the `evaluation_interval` in `prometheus.yml`), Prometheus runs each rule's PromQL. For our alert:

```promql
(sum by (endpoint, tenant)(rate(telemetry_obsv_requests_total{status_code=~"5..", endpoint=~"/.*inference.*", service="nmt-service"}[5m]))
  / sum by (endpoint, tenant)(rate(telemetry_obsv_requests_total{endpoint=~"/.*inference.*", service="nmt-service"}[5m]))) > 0.02
```

If the expression returns any series, the alert enters the **pending** state.

## Step 16 — `for_duration` must hold

Our alert has `for_duration: "1m"`. If the condition stays true for a full minute, Prometheus transitions the alert to **firing** and sends it to Alertmanager.

## Step 17 — Alertmanager groups, matches routes, sends

Alertmanager groups firing alerts by `[alertname, category, severity, tenant]` (10-second group wait). It then walks its route tree to find matching receivers:

```yaml
route:
  receiver: default-admin
  routes:
    - receiver: alert-history-webhook    # Always first — catches all alerts
      continue: true
    - match:
        severity: critical
        category: application
        tenant: cloudsphere-analytics-2-fe7854
      receiver: critical-application--tenant-CloudSphere-Analytics-2
      continue: true
```

For each matched receiver, Alertmanager:
- Sends an **email** via AWS SES with the rendered Go-template body
- Posts a **webhook** to receivers with `webhook_configs`

---

# Phase 4: History recording — webhook back to alert-management-service

## Step 18 — Alertmanager POSTs to `/alerts/history/webhook`

The `alert-history-webhook` receiver always runs (`continue: true`), sending an Alertmanager v4 payload to:

```
POST http://alert-management-service:8098/alerts/history/webhook
```

## Step 19 — `record_alert_history_from_webhook` inserts one row per alert

At [alert_management.py:2925-3000+](../services/alert-management-service/alert_management.py#L2925):

```python
async def record_alert_history_from_webhook(webhook_payload: Dict[str, Any]) -> int:
    alerts = webhook_payload.get("alerts") or webhook_payload.get("Alerts") or []
    receiver = webhook_payload.get("receiver") or "unknown"
    status = (webhook_payload.get("status") or "firing").lower()

    async with db_pool.acquire() as conn:
        for alert in alerts:
            labels = alert.get("labels") or {}
            alert_name = labels.get("alertname") or "Unknown"
            category = (labels.get("category") or "application").lower()
            severity = (labels.get("severity") or "warning").lower()
            triggered_at = alert.get("startsAt") or alert.get("StartsAt")
            ends_at = alert.get("endsAt") or alert.get("EndsAt")
            fingerprint = alert.get("fingerprint")
            tenant = labels.get("tenant")
            organization = labels.get("organization")
            notified = _notified_display(tenant)   # "Admin" or "Tenant Admin - {name}"

            # ...parse timestamps...

            await conn.execute(
                """
                INSERT INTO alert_history (
                    alert_name, category, severity, triggered_at, resolved_at, status,
                    receiver, notified_display, tenant, organization, labels, annotations, fingerprint
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11::jsonb, $12::jsonb, $13)
                """,
                alert_name, category, severity, ts, resolved_ts, status,
                receiver, notified, tenant, organization,
                json.dumps(labels), json.dumps(annotations), fingerprint,
            )
```

Every alert — firing or resolved — becomes a row. Users can query this via `GET /alerts/history`.

---

# Quick mental model

```
┌──────── Phase 1: CREATE (alert-management-service) ─────────┐
│                                                              │
│  Client ─POST /alerts/definitions─► alert-management-service │
│                                          │                   │
│                                          ▼                   │
│                                  build_promql(...)           │
│                                  INSERT alert_definitions    │
│                                  audit log                   │
│                                  trigger_config_sync()       │
│                                          │                   │
│                                          ▼                   │
│                                  Return 201 to client        │
│                                                              │
└──────────────────────────────────────────────────────────────┘
                               │
             POST /sync (fire-and-forget, 30s timeout)
                               │
                               ▼
┌──────── Phase 2: SYNC (alert-config-sync-service) ──────────┐
│                                                              │
│  sync_configuration()                                        │
│    1. acquire asyncio.Lock                                   │
│    2. fetch alert_definitions / receivers / rules            │
│                                  (alerting_db)               │
│    3. fetch admin + role emails  (auth_db)                   │
│    4. resolve tenant → emails    (multi_tenant_db + auth_db) │
│    5. generate_prometheus_alerts_yaml()                      │
│       generate_alertmanager_yaml()                           │
│    6. write_yaml_file(...)  → shared Docker volumes          │
│    7. POST /-/reload   to Prometheus                         │
│       POST /-/reload   to Alertmanager                       │
│                                                              │
└──────────────────────────────────────────────────────────────┘
                               │
                  (Prometheus now evaluates every 5s)
                               │
                               ▼
┌───── Phase 3: FIRE (Prometheus → Alertmanager) ─────────────┐
│                                                              │
│  Prometheus                                                  │
│    evaluates expr → condition true                           │
│    for_duration satisfied                                    │
│    ─► sends firing alert to Alertmanager:9093                │
│                                                              │
│  Alertmanager                                                │
│    groups by (alertname, category, severity, tenant)         │
│    matches routes                                            │
│    ├─► email via AWS SES                                     │
│    └─► webhook ── POST /alerts/history/webhook ─┐            │
│                                                 │            │
└─────────────────────────────────────────────────│────────────┘
                                                  │
                                                  ▼
┌──── Phase 4: RECORD (alert-management-service) ─────────────┐
│                                                              │
│  record_alert_history_from_webhook()                         │
│    for each alert in payload:                                │
│      extract labels, timestamps, fingerprint                 │
│      INSERT INTO alert_history                               │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

---

# Summary: what runs where

| What | Service | File |
|---|---|---|
| `POST /alerts/definitions` (and all CRUD) | alert-management-service | `alert_management.py`, `routers/` |
| Build PromQL from threshold/signal | alert-management-service | `build_promql_from_signal_config()` / `build_promql_from_threshold()` |
| Insert into `alert_definitions` | alert-management-service | `create_alert_definition()` @ line 1147 |
| Fire-and-forget `POST /sync` | alert-management-service | `trigger_config_sync()` @ line 285 |
| Periodic 60s sync timer | alert-config-sync-service | background task |
| Fetch all DB state | alert-config-sync-service | `fetch_alert_definitions()`, `fetch_notification_receivers()`, `fetch_routing_rules()` |
| Resolve emails (RBAC, tenant) | alert-config-sync-service | `fetch_emails_by_role()`, `resolve_tenant_name_to_tenant_id_and_emails()` |
| Generate Prometheus rule YAML | alert-config-sync-service | `generate_prometheus_alerts_yaml()` |
| Generate Alertmanager YAML | alert-config-sync-service | `generate_alertmanager_yaml()` |
| Write YAML to shared volumes | alert-config-sync-service | `write_yaml_file()` |
| Hot-reload Prometheus & Alertmanager | alert-config-sync-service | `trigger_prometheus_reload()`, `trigger_alertmanager_reload()` |
| Evaluate rules every 5s | Prometheus | — |
| Group, route, notify | Alertmanager | — |
| `POST /alerts/history/webhook` receiver | alert-management-service | `record_alert_history_from_webhook()` @ line 2925 |
| `GET /alerts/history` query | alert-management-service | `list_alert_history()` |

---

# Key things to remember

- **Two services, clean split.** alert-management owns the API and history. alert-config-sync owns the YAML pipeline.
- **Sync is fire-and-forget.** API writes to DB first, then tries to sync. If sync fails, the periodic 60s sync picks it up. The user never sees a sync failure.
- **Shared Docker volumes** (`/etc/prometheus/rules`, `/etc/alertmanager`) are how the sync service talks to Prometheus/Alertmanager without any network round-trip for file contents — only the reload calls are HTTP.
- **Tenant label propagation** is done at two points: (1) the sync service injects `tenant` into every `sum by` clause so the firing alert carries it, and (2) Alertmanager matches routes on the `tenant` label for tenant-specific notifications.
- **The webhook closes the loop.** Alertmanager sends every firing/resolved alert to alert-management-service so history is always complete, even if emails fail.
- **`for_duration` matters.** An alert won't fire until its condition has held true for the configured duration (e.g. `1m`) — this prevents notification noise from transient spikes.
