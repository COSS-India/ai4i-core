# Alert Management API – Frontend Reference

**Base path (via API Gateway):** `GET/POST/PUT/PATCH/DELETE` → `/api/v1/alerts/...`  
**Auth:** Bearer token + API key (headers set by gateway).

---

## Organizations (allowed values)

Every resource is scoped to one organization. Use exactly one of:

| Value       |
|------------|
| `irctc`    |
| `kisanmitra` |
| `bashadaan` |
| `beml`     |

- **Regular users:** Organization comes from API key / `X-Organization` (no need to send in payload for create; for list/get/update/delete it’s implicit).
- **Admin users:** Can pass `?organization=<org>` on create/list/get/update/delete to act on that org (or omit to see all).

---

## 1. Alert Definitions

**Path prefix:** `/api/v1/alerts/definitions`

### List

- **GET** `/api/v1/alerts/definitions`
- **Query:** `enabled_only` (optional, boolean) – default `false`. If `true`, only enabled alerts.
- **Response:** Array of **Alert Definition** (see response shape below).

### Get one

- **GET** `/api/v1/alerts/definitions/{alert_id}`
- **Path:** `alert_id` (int).
- **Response:** Single **Alert Definition**.

### Create

- **POST** `/api/v1/alerts/definitions`
- **Body:** **AlertDefinitionCreate**

| Field                | Type   | Mandatory | Default     | Allowed values / notes |
|----------------------|--------|-----------|-------------|------------------------|
| `name`               | string | Yes       | —           | Any (e.g. `HighLatency`) |
| `description`        | string | No        | `null`      | Any |
| `promql_expr`        | string | Yes       | —           | Valid PromQL |
| `category`           | string | No        | `"application"` | `"application"` \| `"infrastructure"` |
| `severity`           | string | Yes       | —           | `"critical"` \| `"warning"` \| `"info"` |
| `urgency`            | string | No        | `"medium"`   | `"high"` \| `"medium"` \| `"low"` |
| `alert_type`        | string | No        | `null`      | e.g. `"latency"`, `"error_rate"` |
| `scope`             | string | No        | `null`      | e.g. `"all_services"`, `"per_service"` |
| `evaluation_interval` | string | No      | `"30s"`     | e.g. `"30s"`, `"1m"` |
| `for_duration`       | string | No        | `"5m"`      | e.g. `"5m"`, `"10m"` |
| `annotations`        | array  | No        | `[]`        | List of `{ "key": string, "value": string }` (e.g. summary, description, impact, action) |

**Response:** Created **Alert Definition** (201).

### Update

- **PUT** `/api/v1/alerts/definitions/{alert_id}`
- **Body:** **AlertDefinitionUpdate** – all fields optional; send only what you change.

| Field                | Type   | Mandatory | Notes |
|----------------------|--------|-----------|--------|
| `description`        | string | No        | |
| `promql_expr`        | string | No        | |
| `category`           | string | No        | `"application"` \| `"infrastructure"` |
| `severity`           | string | No        | `"critical"` \| `"warning"` \| `"info"` |
| `urgency`            | string | No        | `"high"` \| `"medium"` \| `"low"` |
| `alert_type`        | string | No        | |
| `scope`             | string | No        | |
| `evaluation_interval` | string | No      | |
| `for_duration`       | string | No        | |
| `enabled`            | boolean | No       | |
| `annotations`        | array  | No        | `[{ "key": string, "value": string }]` |

**Response:** Updated **Alert Definition**.

### Enable/Disable

- **PATCH** `/api/v1/alerts/definitions/{alert_id}/enabled`
- **Body:** `{ "enabled": true }` or `{ "enabled": false }` (boolean required).
- **Response:** Updated **Alert Definition**.

### Delete

- **DELETE** `/api/v1/alerts/definitions/{alert_id}`
- **Response:** `{ "message": "Alert definition deleted successfully" }`.

### Alert Definition (response shape)

```json
{
  "id": 1,
  "organization": "irctc",
  "name": "HighLatency",
  "description": "High latency alert",
  "promql_expr": "...",
  "category": "application",
  "severity": "warning",
  "urgency": "medium",
  "alert_type": "latency",
  "scope": null,
  "evaluation_interval": "30s",
  "for_duration": "5m",
  "enabled": true,
  "created_at": "2024-01-15T10:00:00Z",
  "updated_at": "2024-01-15T10:00:00Z",
  "created_by": "user@example.com",
  "annotations": [{"key": "summary", "value": "High latency"}]
}
```

---

## 2. Notification Receivers

**Path prefix:** `/api/v1/alerts/receivers`

### List

- **GET** `/api/v1/alerts/receivers`
- **Query:** `enabled_only` (optional, boolean) – default `false`.
- **Response:** Array of **Notification Receiver**.

### Get one

- **GET** `/api/v1/alerts/receivers/{receiver_id}`
- **Response:** Single **Notification Receiver**.

### Create

- **POST** `/api/v1/alerts/receivers`
- **Body:** **NotificationReceiverCreate**

| Field                    | Type   | Mandatory | Default | Allowed values / notes |
|--------------------------|--------|-----------|---------|------------------------|
| `category`               | string | Yes       | —       | `"application"` \| `"infrastructure"` |
| `severity`               | string | Yes       | —       | `"critical"` \| `"warning"` \| `"info"` |
| `alert_type`             | string | No        | `null`  | e.g. `"latency"`, `"error_rate"` |
| `email_to`               | array  | Conditional | —     | List of email strings. **Required if `rbac_role` is not set.** |
| `rbac_role`              | string | Conditional | —     | **Required if `email_to` is not set.** Must be exactly one of: `"ADMIN"`, `"MODERATOR"`, `"USER"`, `"GUEST"`. Cannot be sent together with `email_to`. |
| `email_subject_template`  | string | No        | `null`  | |
| `email_body_template`    | string | No        | `null`  | HTML allowed |

**Rules:** Provide **either** `email_to` **or** `rbac_role`, never both. Receiver name is auto-generated.

**Response:** Created **Notification Receiver** (201).

### Update

- **PUT** `/api/v1/alerts/receivers/{receiver_id}`
- **Body:** **NotificationReceiverUpdate** – all fields optional.

| Field                    | Type   | Mandatory | Allowed values / notes |
|--------------------------|--------|-----------|------------------------|
| `receiver_name`          | string | No        | |
| `email_to`               | array  | No        | List of emails. If set, do not set `rbac_role`. |
| `rbac_role`              | string | No        | `"ADMIN"` \| `"MODERATOR"` \| `"USER"` \| `"GUEST"`. If set, do not set `email_to`. |
| `email_subject_template` | string | No        | |
| `email_body_template`    | string | No        | |
| `enabled`                | boolean | No       | |

**Response:** Updated **Notification Receiver**.

### Delete

- **DELETE** `/api/v1/alerts/receivers/{receiver_id}`
- **Response:** `{ "message": "..." }`.

### Notification Receiver (response shape)

```json
{
  "id": 1,
  "organization": "irctc",
  "receiver_name": "receiver-...",
  "email_to": ["user@example.com"],
  "rbac_role": null,
  "email_subject_template": null,
  "email_body_template": null,
  "enabled": true,
  "created_at": "...",
  "updated_at": "...",
  "created_by": "user@example.com"
}
```

---

## 3. Routing Rules

**Path prefix:** `/api/v1/alerts/routing-rules`

### List

- **GET** `/api/v1/alerts/routing-rules`
- **Query:** `enabled_only` (optional, boolean) – default `false`.
- **Response:** Array of **Routing Rule**.

### Get one

- **GET** `/api/v1/alerts/routing-rules/{rule_id}`
- **Response:** Single **Routing Rule**.

### Create

- **POST** `/api/v1/alerts/routing-rules`
- **Body:** **RoutingRuleCreate**

| Field              | Type   | Mandatory | Default | Allowed values / notes |
|--------------------|--------|-----------|---------|------------------------|
| `rule_name`        | string | Yes       | —       | Unique per org |
| `receiver_id`      | int    | Yes       | —       | ID of an existing notification receiver (same org) |
| `match_severity`   | string | No        | `null`  | `"critical"` \| `"warning"` \| `"info"` \| `null` (match all) |
| `match_category`   | string | No        | `null`  | `"application"` \| `"infrastructure"` \| `null` (match all) |
| `match_alert_type` | string | No        | `null`  | e.g. `"latency"` \| `null` (match all) |
| `group_by`         | array  | No        | `["alertname", "category", "severity", "organization"]` | List of label names |
| `group_wait`       | string | No        | `"10s"` | e.g. `"10s"`, `"30s"` |
| `group_interval`   | string | No        | `"10s"` | |
| `repeat_interval`  | string | No        | `"12h"` | e.g. `"12h"`, `"24h"` |
| `continue_routing` | boolean | No      | `false` | If true, evaluation continues to next matching rule |
| `priority`         | int    | No        | `100`   | Lower value = higher priority |

**Response:** Created **Routing Rule** (201).

### Update

- **PUT** `/api/v1/alerts/routing-rules/{rule_id}`
- **Body:** **RoutingRuleUpdate** – all fields optional (same field names and types as create where applicable).

| Field              | Type   | Mandatory |
|--------------------|--------|-----------|
| `rule_name`        | string | No        |
| `receiver_id`      | int    | No        |
| `match_severity`   | string | No        |
| `match_category`   | string | No        |
| `match_alert_type` | string | No        |
| `group_by`         | array  | No        |
| `group_wait`       | string | No        |
| `group_interval`   | string | No        |
| `repeat_interval`  | string | No        |
| `continue_routing` | boolean | No      |
| `priority`         | int    | No        |
| `enabled`          | boolean | No       |

**Response:** Updated **Routing Rule**.

### Delete

- **DELETE** `/api/v1/alerts/routing-rules/{rule_id}`
- **Response:** `{ "message": "Routing rule deleted successfully" }`.

### Bulk update timing (PATCH timing)

- **PATCH** `/api/v1/alerts/routing-rules/timing`
- **Body:** **RoutingRuleTimingUpdate** – updates all rules matching category/severity (and optional filters).

| Field              | Type   | Mandatory | Default | Notes |
|--------------------|--------|-----------|---------|--------|
| `category`         | string | Yes       | —       | `"application"` \| `"infrastructure"` |
| `severity`         | string | Yes       | —       | `"critical"` \| `"warning"` \| `"info"` |
| `alert_type`       | string | No        | `null`  | Optional filter |
| `priority`         | int    | No        | `null`  | Optional filter (lower = higher priority) |
| `group_wait`       | string | No        | `null`  | e.g. `"10s"` |
| `group_interval`   | string | No        | `null`  | |
| `repeat_interval`  | string | No        | `null`  | |

**Response:** Object describing how many rules were updated.

### Routing Rule (response shape)

```json
{
  "id": 1,
  "organization": "irctc",
  "rule_name": "critical-to-team",
  "receiver_id": 1,
  "match_severity": "critical",
  "match_category": "application",
  "match_alert_type": null,
  "group_by": ["alertname", "category", "severity", "organization"],
  "group_wait": "10s",
  "group_interval": "10s",
  "repeat_interval": "12h",
  "continue_routing": false,
  "priority": 100,
  "enabled": true,
  "created_at": "...",
  "updated_at": "...",
  "created_by": "user@example.com"
}
```

---

## Quick reference – allowed values

| Field / concept   | Allowed values |
|-------------------|----------------|
| **Organization**   | `irctc`, `kisanmitra`, `bashadaan`, `beml` |
| **category**      | `application`, `infrastructure` |
| **severity**      | `critical`, `warning`, `info` |
| **urgency**       | `high`, `medium`, `low` |
| **rbac_role**     | `ADMIN`, `MODERATOR`, `USER`, `GUEST` |
| **match_severity** | `critical`, `warning`, `info`, or `null` (all) |
| **match_category** | `application`, `infrastructure`, or `null` (all) |

---

## HTTP status codes

- **200** – Success (GET, PUT, PATCH).
- **201** – Created (POST create).
- **400** – Bad request (validation: invalid enum, missing required field, or both `email_to` and `rbac_role` for receivers).
- **404** – Resource or organization not found (e.g. no users for given `rbac_role`).
- **401/403** – Unauthorized / Forbidden (handled by gateway).
