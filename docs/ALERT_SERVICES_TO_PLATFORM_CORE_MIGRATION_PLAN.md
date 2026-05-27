# Migration Plan: Merge `alert-management-service` + `alert-config-sync-service` into `platform-core-service`

> **Status:** Plan only — no code changes yet. Implementation to follow.
> **Goal:** Per management decision, both alert services merge into `platform-core-service` and the standalone directories go away.
> **Hard constraint:** Anything that lands under `services/platform-core-service/app/services/` must live in a NEW subfolder named `alert-management/`. Existing files in `app/services/` stay at the top level.

---

## 1. What each alert service actually does

### `alert-management-service` (port 8098)

**HTTP surface (4 routers, all under `/alerts/*`):**

- `POST/GET/PUT/DELETE/PATCH /alerts/definitions[/{id}][/enabled]` — CRUD + enable-toggle for Prometheus alert rules. PromQL is generated server-side from either `(alert_type + threshold)` or `(sub_category + signal + signal_metric + condition_operator + threshold)`.
- `POST/GET/PUT/DELETE /alerts/receivers[/{id}]` — Notification receiver CRUD; auto-creates a paired routing rule and resolves `rbac_role`/`tenant` to email lists via `auth_db`.
- `POST/GET/PUT/DELETE/PATCH /alerts/routing-rules[/{id}|/timing]` — Routing rule CRUD plus a bulk timing patch.
- `POST /alerts/history/webhook` (no auth, called by Alertmanager) and `GET /alerts/history` — append + read of firing-alert audit log.

**Domain models / tables (DB = `alerting_db`):** `alert_definitions`, `alert_annotations`, `notification_receivers`, `routing_rules`, `alert_history`, `alert_config_audit_log` (see `services/alert-management-service/models.py` lines 31–256). Cross-DB reads against `auth_db` (`users`, `user_roles`/`user_role`, `roles`, `tenants`) for RBAC/tenant email resolution.

**Background jobs:** none directly. On every write it does a fire-and-forget HTTP `POST` to `alert-config-sync-service:/sync` (`trigger_config_sync`, `alert_management.py` lines 248–282).

**External integrations:** sync service (via HTTP), Alertmanager (incoming webhook for history). Logging via `ai4icore_logging` to OpenSearch; tracing via `ai4icore_telemetry` → Jaeger.

**Auth:** Gateway-validated headers (`X-User-ID`, `X-Roles`, `X-Username`). Local `utils/auth_deps.py` defines `require_alerts_{create,read,update,delete}` that check `ADMIN`/`MODERATOR`/`ADMIN`-only based on operation. Also an org-extraction layer that maps API key hash → one of `["irctc", "kisanmitra", "bashadaan", "beml"]` (hardcoded constant `VALID_ORGANIZATIONS` in `alert_management.py:33`).

### `alert-config-sync-service` (port 8097)

**HTTP surface:**

- `POST /sync` — synchronous trigger that regenerates YAML and reloads.
- `GET /health`.

**Background:** an `asyncio.Task` started in the FastAPI `lifespan()` calls `run_periodic_sync()` every `SYNC_INTERVAL` seconds (default 60). The same `sync_lock` mutex is shared between manual and periodic runs (`main.py` 1294–1363).

**What it does:** reads `alert_definitions + alert_annotations + notification_receivers + routing_rules` from `alerting_db`; reads ADMIN/role/tenant emails from `auth_db`; renders three YAML files (`/etc/prometheus/rules/application-alerts.yml`, `/etc/prometheus/rules/infrastructure-alerts.yml`, `/etc/alertmanager/alertmanager.yml`); then POSTs `/-/reload` to Prometheus and Alertmanager.

**External integrations:** Prometheus (`PROMETHEUS_URL`), Alertmanager (`ALERTMANAGER_URL`), `alerting_db`, `auth_db`. No Slack/Twilio used despite env keys (those flow to Alertmanager via SMTP).

**Auth:** none. Currently relies on the network boundary; in compose it's only reachable from sibling containers.

These two services are tightly coupled: the management service does writes and pokes the sync service, the sync service polls + reacts. Merging them is correct.

---

## 2. DRY overlap map (reuse / extend / drop)

| Concern | What the alert services do today | What platform-core already provides | Recommended action |
|---|---|---|---|
| Settings loading | Both pull from `ai4icore_env.app_env` (global mutable singleton). Hardcoded `DB_NAME = "alerting_db"`. | `app/core/config.py` → `CoreSettings` (pydantic-settings); fields like `postgres_host`, `postgres_port`, etc. | **Extend** `CoreSettings` with the alert-specific fields listed in §5. **Drop** direct `app_env` access in the alert code. |
| DB engine / session | Both manage their own `asyncpg.Pool` (`db_pool`, `auth_db_pool`) with manual `init_db_pool`/`close_db_pool`. | `app/core/database.py` → `init_database`/`close_database`/`get_db` (SQLAlchemy async). | **Reuse** platform-core's single SQLAlchemy session for ALL alert tables — they now live in `ai4iplatform_core` (see §5 Database). Either (a) convert all alert queries to SQLAlchemy Core/ORM, or (b) keep raw SQL but run it through `session.execute(text(...))` so it shares the engine pool. The separate `auth_db` connection becomes a second engine (configured via new `AUTH_DB_URL`) — also wired through `app/core/database.py`. So **two engines total**: primary `ai4iplatform_core` (alert + model-management tables), secondary `auth_db` (read-only RBAC/tenant lookup). |
| Redis client | Not used today by either alert service. | `app/core/redis.py` re-exports `init_redis`/`get_redis`. | **Reuse** when we add caching of e.g. role→email lookups; not required for parity. |
| Exception classes | `alert_management.py` raises `HTTPException` directly everywhere. `auth_deps.py` uses `ai4icore_exceptions.InsufficientPermissionsError`. | `app/core/exceptions.py` re-exports `EntityNotFoundError`, `DuplicateEntityError`, `ValidationError`, `ServiceError`, `register_exception_handlers`. | **Extend** — replace 404 `HTTPException`s with `EntityNotFoundError`, 409s with `DuplicateEntityError`, 400s with `ValidationError`. Keep `InsufficientPermissionsError` (already in shared lib). Register handlers once in `app/main.py` — already done. |
| Response envelope | Alert routers return raw Pydantic objects (no envelope). | `app/core/responses.py` → `success_response`, `error_response`. | **Extend** alert routers to use `success_response` so the merged service has a uniform response shape. Keep request/response Pydantic models for body parsing/validation. |
| Auth deps | `utils/auth_deps.py` reads `X-User-ID`/`X-Roles` and gates on ADMIN/MODERATOR. | Routes today read `request.headers.get("X-User-Id")` ad-hoc in `routes/model.py:114`. No central dep yet. | **Move** alert `auth_deps.py` into `app/dependencies/auth.py` (new) and rename functions to a generic shape — see §3. Existing model/service routes can keep their current behavior (this is additive). |
| Audit logging | 450-line `utils/audit_logger.py` (alert-mgmt-service) — JSON-formatted writes via `ai4icore_logging` to OpenSearch. | None today in platform-core. | **DROP entirely.** Audit logging is being removed from alerting per latest decision. The standard request logger (`RequestMiddleware` already in platform-core) covers what's needed. |
| Middleware / request context | `main.py` clears uvicorn access logger, registers exception handlers, registers logging plugin, sets up Jaeger tracing + `FastAPIInstrumentor`. | `app/main.py` already does `configure_logging`, `register_exception_handlers`, `RequestMiddleware`. **No tracing** — `app/main.py:2` explicitly says "No tracing or observability — logging only". | **Drop** the alert-service lifecycle setup entirely; reuse platform-core's. **Decision needed:** add Jaeger/`FastAPIInstrumentor` to platform-core, or stop tracing alerts on merge. (See §7 risks.) |
| Health checks | Both services have own `/health` returning service-name JSON. | `app/routes/health.py` already returns `{"status": "healthy", "service": settings.service_name}` and is mounted at `/api/v1/platform-core/health`. | **Drop** alert-service health routes. Reuse platform-core's. The `/ready` endpoint in `ai4icore_core.bootstrap.health` could be adopted too (checks DB+Redis), but platform-core currently doesn't include it. |
| Versioning / router setup | Alert routers use prefixes like `/alerts/definitions`, no `/api/v1` prefix (gateway rewrites). | platform-core mounts everything under `/api/v1` via `app/routes/__init__.py`. | **Extend** — add the consolidated `app/routes/alert.py` router to `v1_router` in `app/routes/__init__.py`; **remove** the `proxy-rewrite` strip rule in apisix/nginx. Alert callers will now hit `/api/v1/alerts/...` directly without the `/alerts/...` rewrite. |
| Requirements | alert-mgmt: `asyncpg`, `httpx`, `pydantic-settings`, `opentelemetry-*`. sync: `asyncpg`, `pyyaml`, `httpx`. | platform-core already has `asyncpg`, `httpx`, `pydantic-settings`, `sqlalchemy`, `alembic`, `redis`, `opentelemetry-*`. | **Add** only `pyyaml>=6.0` to platform-core's requirements. Everything else already present. |
| Dockerfile | Both alert services build with separate Dockerfiles, mount libs, expose 8097/8098. | platform-core's Dockerfile already installs everything and exposes 8095. | **Drop** both alert Dockerfiles. The merged service ships from platform-core's existing Dockerfile. The sync loop's filesystem dependencies (`/etc/prometheus/rules`, `/etc/alertmanager`) must be mounted on the platform-core container — see §5. |
| Alembic migrations | `infrastructure/databases/migrations/postgres/alembic/migration_registry.py:164` loads `services/alert-management-service/models.py` as the metadata for `alerting_db`. | `migration_registry.py:179` loads `services/platform-core-service/app/models/__init__.py` for `ai4iplatform_core`. | **Delete** the `_load_alerting_metadata()` registration and the `alerting_db` chain. **Add a new revision** in the `ai4iplatform_core` chain that CREATEs the alert tables (definitions, annotations, notification_receivers, routing_rules, alert_history) — same schema, new home. Existing `alerting_db` Alembic revision (`d7df939ec69b`) is no longer needed once data is migrated; see §5 Database for the deprecation path. |
| Org-extraction (hash-based mapping to "irctc","kisanmitra","bashadaan","beml") | Hardcoded `VALID_ORGANIZATIONS` list and `_get_organization_from_api_key` MD5 hash mapping in `alert_management.py:33,285`. | None — platform-core is org-agnostic. | **DROP entirely.** All organization-related logic is being removed from alerting. Any call sites that branch on `organization` get unwound (use `tenant` where a multi-tenant distinction is genuinely needed; otherwise delete the branch). |

---

## 3. Target file/folder layout

### Naming convention (per user)

| Folder | Layout | Rule |
|---|---|---|
| `services/` | Two domain subfolders + common at top | `services/alert-management/`, `services/model-management/`, common files (`cache_service.py`) at top. *Hyphen kept from earlier user constraint.* |
| `models/` | Two domain subfolders (underscores), no file prefixes | `models/model_management/`, `models/alert_management/`. Files use bare resource names (e.g. `model.py`, `alert_definition.py`). |
| `repositories/` | Two domain subfolders (underscores), no file prefixes | `repositories/model_management/`, `repositories/alert_management/`. |
| `schemas/` | Three subfolders + common at top | `schemas/enums/` (with `model_management.py` + `alert_management.py`), `schemas/model_management/`, `schemas/alert_management/`. Common files (`base.py`, `common.py`) stay at top. |
| `routes/` | Flat, three domain files + `health.py` | `routes/model.py` + `routes/service.py` (existing — no rename), `routes/alert.py` (NEW — **all** alert routes consolidated into this single file), `routes/health.py` (common). |
| `utils/` | Flat, no prefixes, original filenames | `promql_builder.py`, `email_templates.py`, `config_renderer.py` (new). Existing utils (`hashing.py`, `security.py`, `probe_payloads.py`, `endpoint_validator.py`) keep their names. |

**Underscore vs hyphen.** All NEW subfolders under `models/`, `repositories/`, `schemas/` use underscores — valid Python package names, no import workarounds. Only `services/alert-management/` and `services/model-management/` keep the hyphenated form (from the earlier hard rule), which forces `importlib` workarounds wherever those modules are imported. Worth re-confirming whether `services/alert_management/` + `services/model_management/` (underscores) is acceptable — flagged in §7.

**Design principle (carried over):** `services/` holds only files that touch the DB or coordinate domain workflows. Pure helpers (string builders, template strings, YAML rendering, HTTP reload clients) live in `utils/`.

### Common-vs-domain classification of existing platform-core files

No file renames in this round — files MOVE into the new domain subfolders but keep their existing names. The only exception is `schemas/enums.py` which is consumed by the new `schemas/enums/` sub-package layout. Verify the table before coding (especially anything marked *verify*):

| File | Verdict | Action |
|---|---|---|
| `core/config.py`, `core/database.py`, `core/redis.py`, `core/exceptions.py`, `core/responses.py` | **Common** | no change (extend `config.py` with alert env keys per §5) |
| `dependencies/services.py` | **Common** (DI factory used by everything) | extend with new alert-service factories |
| `routes/health.py` | **Common** | no change |
| `routes/model.py`, `routes/service.py` | model-management | **no change** — keep at top of `routes/` |
| `models/model.py` | model-management | move to `models/model_management/model.py` |
| `models/service.py` | model-management | move to `models/model_management/service.py` |
| `repositories/model_repository.py` | model-management | move to `repositories/model_management/model_repository.py` |
| `repositories/service_repository.py` | model-management | move to `repositories/model_management/service_repository.py` |
| `schemas/base.py`, `schemas/common.py` | **Common** | no change |
| `schemas/enums.py` | model-management *(verify — if it contains only Triton/inference enums)* | **relocate** to `schemas/enums/model_management.py` (joins the new enums sub-package alongside `schemas/enums/alert_management.py`) |
| `schemas/model.py` | model-management | move to `schemas/model_management/model.py` |
| `schemas/service.py` | model-management | move to `schemas/model_management/service.py` |
| `services/cache_service.py` | **Common** (generic Redis cache) | no change |
| `services/model_service.py` | model-management | move to `services/model-management/model_service.py` |
| `services/service_service.py` | model-management | move to `services/model-management/service_service.py` |
| `services/serializers.py` | model-management *(verify — likely serializes Model/Service entities)* | move to `services/model-management/serializers.py` |
| `utils/hashing.py`, `utils/security.py` | **Common** | no change |
| `utils/probe_payloads.py` | model-management *(Triton probe payloads)* | **no change** — stays in `utils/` (no prefix per user rule) |
| `utils/endpoint_validator.py` | model-management *(validates Triton endpoints)* | **no change** — stays in `utils/` |

### Target layout

```
services/platform-core-service/app/
├── core/                                          (unchanged — all common infrastructure)
│   ├── config.py                                  (extend with alert fields — §5)
│   ├── database.py
│   ├── redis.py
│   ├── exceptions.py
│   └── responses.py
├── dependencies/                                  (flat; no domain split)
│   ├── services.py                                (extend with factories for new alert services)
│   └── auth.py                                    (NEW — moved from alert-mgmt utils/auth_deps.py)
├── models/                                        (TWO subfolders — no file prefixes)
│   ├── __init__.py                                (extend — register all models with Base)
│   ├── model_management/
│   │   ├── __init__.py
│   │   ├── model.py                               (moved from models/model.py — no rename)
│   │   └── service.py                             (moved from models/service.py — no rename)
│   └── alert_management/
│       ├── __init__.py
│       ├── alert_definition.py                    (NEW — combined AlertDefinition + AlertAnnotation)
│       ├── notification_receiver.py               (NEW)
│       ├── routing_rule.py                        (NEW)
│       └── alert_history.py                       (NEW)
├── repositories/                                  (TWO subfolders — no file prefixes)
│   ├── model_management/
│   │   ├── __init__.py
│   │   ├── model_repository.py                    (moved — no rename)
│   │   └── service_repository.py                  (moved — no rename)
│   └── alert_management/
│       ├── __init__.py
│       ├── alert_definition_repository.py         (NEW)
│       ├── notification_receiver_repository.py    (NEW)
│       ├── routing_rule_repository.py             (NEW)
│       └── alert_history_repository.py            (NEW)
├── routes/                                        (FLAT — 4 files total)
│   ├── __init__.py                                (extend — include routes/alert.py in v1_router)
│   ├── health.py                                  (COMMON — no change)
│   ├── model.py                                   (existing — no change)
│   ├── service.py                                 (existing — no change)
│   └── alert.py                                   (NEW — ALL alert routes consolidated into one file; use multiple APIRouter instances per resource and aggregate via a module-level `router = APIRouter(); router.include_router(definitions_router); router.include_router(receivers_router); ...` pattern)
├── schemas/                                       (THREE subfolders + common at top)
│   ├── base.py                                    (COMMON — no change)
│   ├── common.py                                  (COMMON — no change)
│   ├── enums/
│   │   ├── __init__.py
│   │   ├── model_management.py                    (was schemas/enums.py — relocated)
│   │   └── alert_management.py                    (NEW — severity / category / urgency / rbac_role)
│   ├── model_management/
│   │   ├── __init__.py
│   │   ├── model.py                               (moved from schemas/model.py — no rename)
│   │   └── service.py                             (moved from schemas/service.py — no rename)
│   └── alert_management/
│       ├── __init__.py
│       ├── alert_definition.py                    (AlertDefinitionCreate/Update/Response, AlertAnnotation)
│       ├── receiver.py
│       ├── routing_rule.py
│       └── history.py
├── services/                                      (TWO subfolders + common at top — hyphenated per earlier user constraint)
│   ├── cache_service.py                           (COMMON — stays at top level)
│   ├── alert-management/                          (REQUIRED hyphenated folder name)
│   │   ├── __init__.py
│   │   ├── definition_service.py                  (CRUD + enable-toggle; uses utils/promql_builder)
│   │   ├── receiver_service.py                    (CRUD + tenant/RBAC email resolution against auth_db)
│   │   ├── routing_rule_service.py                (CRUD + bulk timing-update)
│   │   ├── history_service.py                     (record_alert_history_from_webhook + list_alert_history)
│   │   └── sync_service.py                        (orchestration: read repos → utils/config_renderer → reload; owns periodic loop + sync_lock mutex)
│   └── model-management/                          (existing platform-core services moved in)
│       ├── __init__.py
│       ├── model_service.py                       (moved from services/model_service.py)
│       ├── service_service.py                     (moved from services/service_service.py)
│       └── serializers.py                         (moved from services/serializers.py — verify it's not common)
└── utils/                                         (FLAT — no prefix; original filenames)
    ├── hashing.py                                 (COMMON — no change)
    ├── security.py                                (COMMON — no change)
    ├── probe_payloads.py                          (existing — no rename)
    ├── endpoint_validator.py                      (existing — no rename)
    ├── promql_builder.py                          (NEW — build_promql_from_threshold, signal/threshold builders, SIGNAL_*_CONFIG dicts; was alert_management.py:638-1012)
    ├── email_templates.py                         (NEW — GLOBAL_/TENANT_EMAIL_SUBJECT/BODY_TEMPLATE + _format_environment_title; deduplicates copies from both source services)
    └── config_renderer.py                         (NEW — generate_prometheus_alerts_yaml, generate_alertmanager_yaml, html_literal_representer, write_yaml_file, trigger_prometheus_reload, trigger_alertmanager_reload; was alert-config-sync-service/main.py:18-1180)
```

**File-count summary**

| Folder | Alert-specific (new) | Model-management (moved in) | Common (unchanged) |
|---|---|---|---|
| `services/alert-management/` | 5 | — | — |
| `services/model-management/` | — | 3 | — |
| `services/` (top) | — | — | 1 (`cache_service.py`) |
| `models/alert_management/` | 4 | — | — |
| `models/model_management/` | — | 2 | — |
| `repositories/alert_management/` | 4 | — | — |
| `repositories/model_management/` | — | 2 | — |
| `routes/` | 1 (`alert.py`) | 2 (`model.py`, `service.py`) | 1 (`health.py`) |
| `schemas/alert_management/` | 4 | — | — |
| `schemas/model_management/` | — | 2 | — |
| `schemas/enums/` | 1 (`alert_management.py`) | 1 (`model_management.py`, relocated) | — |
| `schemas/` (top) | — | — | 2 (`base.py`, `common.py`) |
| `utils/` | 3 | — | 4 (`hashing.py`, `security.py`, `probe_payloads.py`, `endpoint_validator.py`) |

**Why these placements:**

- **`routes/alert.py` is one consolidated file** — per user. Internal structure uses one `APIRouter` per resource (definitions, receivers, routing-rules, history), aggregated into a single module-level `router` that gets included in `v1_router`. Keeps every alert HTTP path in one place; line count will be moderate (~500–800 lines after splitting handlers from services).
- **Domain split on `services/`, `models/`, `repositories/`, `schemas/`** — clear boundary between model-management and alert-management. Imports inside each domain are short (e.g., `from app.models.alert_management.alert_definition import AlertDefinition`).
- **`schemas/enums/` is its own sub-package** — per user. Domain-grouped enum files (`model_management.py`, `alert_management.py`) keep each set of enums together; cross-domain code imports `from app.schemas.enums.alert_management import Severity, Category, ...`.
- **Pure helpers in `utils/` with original filenames (no prefix)** — per user. `promql_builder.py`, `email_templates.py`, `config_renderer.py` sit alongside the existing platform-core utilities. No domain prefix needed since each filename is already descriptive.
- **`sync_service.py` is one file, not a sub-package** — it does three things (read from repos, hand data to `utils/config_renderer`, run the periodic loop). The big YAML-rendering code (~1000 lines) lives in `utils/config_renderer.py`.
- **`alert_management.py` (2956 lines) MUST be split.** It currently mixes Pydantic schemas, PromQL string-builders, DB CRUD, email-template strings, sync-trigger HTTP client, and org-mapping (org-mapping now dropped).
- **`routes/health.py`, `schemas/base.py`, `schemas/common.py`, `utils/hashing.py`, `utils/security.py`, `services/cache_service.py` stay common.** Both domains use them; don't fork.

---

## 4. File-by-file migration mapping

### `alert-management-service` → platform-core

| Source file | → | Destination | Notes |
|---|---|---|---|
| `main.py` | → | DROP (merge into `app/main.py`) | Logging/tracing/lifespan all replaced by platform-core's. Keep only the **lifespan delta**: trigger alert sync task — see §5. |
| `alert_management.py` (2956 lines) | → | **SPLIT 6 ways** | See below. Do not migrate as a single file. |
| ├ Pydantic models (lines 380–635) | → | `app/schemas/alert_management/{alert_definition,receiver,routing_rule}.py` + `app/schemas/enums/alert_management.py` | Replace `BaseModel` with platform-core's `BaseSchema` re-export (`app/schemas/base.py`). Severity/Category/Urgency/Rbac enums go into the enums file. |
| ├ PromQL builders + config dicts (lines 638–1012) | → | `app/utils/promql_builder.py` | Pure functions, no DB. Replace `HTTPException(400, ...)` with `ValidationError(...)`. |
| ├ `init_db_pool` / `close_db_pool` / `ensure_db_pool` (lines 55–105) | → | DROP | Use platform-core's `init_database`/`get_db` instead. If keeping raw SQL: get a second SQLAlchemy engine for `auth_db` (`AUTH_DB_URL`). |
| ├ `get_users_by_role` / `resolve_tenant_name_to_emails` / `_receiver_row_to_response` (lines 107–245) | → | `app/services/alert-management/receiver_service.py` (helpers section) | These query `auth_db`. Wire via the new `auth_db` engine. |
| ├ `trigger_config_sync` (lines 248–282) | → | DROP | After merge there's no separate sync service to call; replace with a direct in-process call to `sync_service.sync_configuration(blocking=True)` (or push onto an asyncio queue). |
| ├ `extract_organization` / `_get_organization_from_api_key` / `validate_organization` / `get_organization_for_audit_from_request` (lines 285–377) | → | **DROP entirely** | All organization logic is removed from alerting. Audit any call site that branched on org and either delete the branch or replace with `tenant` if multi-tenancy is genuinely needed at that point. |
| ├ Email template strings + `_format_environment_title` (lines 1629–1734) | → | `app/utils/email_templates.py` | Identical strings exist in sync's `main.py:540–700` — **deduplicate**: both `sync_service.py` and any other consumer import from this single module. |
| ├ Alert-definition CRUD (lines 1014–1621) | → | `app/services/alert-management/definition_service.py` | Convert raw asyncpg to SQLAlchemy session per request. |
| ├ Receiver CRUD (lines 1736–2351) | → | `app/services/alert-management/receiver_service.py` | Same. |
| ├ Routing-rule CRUD + timing-update (lines 1956–2745) | → | `app/services/alert-management/routing_rule_service.py` | Same. |
| ├ Alert-history (lines 2782–end) | → | `app/services/alert-management/history_service.py` | Same. |
| `models.py` (256 lines, 6 ORM classes) | → | `app/models/alert_management/{alert_definition,notification_receiver,routing_rule,alert_history}.py` | Replace `declarative_base()` with `from app.models import Base`. Keep table names identical so existing alembic revision `d7df939ec69b` continues to apply. Combine `AlertDefinition` + `AlertAnnotation` into `alert_definition.py` since they're foreign-keyed. **Drop the `audit_log` table** along with the audit logger feature. |
| `routers/alert_definitions.py` + `routers/alert_history.py` + `routers/receivers.py` + `routers/routing_rules.py` | → | **`app/routes/alert.py` (one consolidated file)** | All four routers become `APIRouter` instances within `alert.py`, aggregated under a single module-level `router` that gets included in `v1_router`. Prefixes preserved (`/alerts/definitions`, `/alerts/receivers`, etc.). Replace direct service calls with `svc.create(...)` through `Depends(get_*_service)`. Wrap responses in `success_response`. Note: `POST /alerts/history/webhook` must remain auth-free (called by Alertmanager) — handle via a per-route APISIX/nginx auth-skip. |
| `utils/auth_deps.py` | → | `app/dependencies/auth.py` | Rename to e.g. `require_alerts_*` kept as-is, or generalise into `require_roles(*roles)` factory. Already uses shared `InsufficientPermissionsError`. |
| `utils/audit_logger.py` | → | **DROP entirely** | Audit logging feature removed. The standard request logger covers what's needed. |
| `Dockerfile` | → | DROP | Use platform-core's Dockerfile (`services/platform-core-service/Dockerfile`). |
| `requirements.txt` | → | DROP | Verify all deps present in platform-core; add nothing (asyncpg, httpx, pydantic-settings, opentelemetry already there). |
| `env.template`, `.env` | → | Merge keys into `services/platform-core-service/env.template` | See §5. |

### `alert-config-sync-service` → platform-core

| Source file | → | Destination | Notes |
|---|---|---|---|
| `main.py` (1420 lines) | → | **SPLIT 5 ways** | See below. |
| ├ DB-pool init / close (lines 88–141) | → | DROP | Reuse `app/core/database.py`. Second engine for `auth_db` is set up once for both alert mgmt and sync. |
| ├ `resolve_tenant_name_to_tenant_id_and_emails`, `fetch_admin_emails`, `fetch_emails_by_role`, `fetch_alert_definitions`, `fetch_notification_receivers`, `fetch_routing_rules` (lines 143–282) | → | Mostly **DROP** — these queries are duplicated against `alert-management-service`'s tenant/role helpers and the new repository layer | Wire sync to `AlertDefinitionRepository.list_enabled()`, `NotificationReceiverRepository.list_enabled()`, `RoutingRuleRepository.list_enabled()`, and the `auth_db` helpers from `receiver_service.py`. **This is the biggest DRY win.** |
| ├ `inject_tenant_into_promql`, `sanitize_promql_service_regex`, `_normalize_service_for_display`, `SERVICE_TYPE_MAP`, `_signal_display_from_alert`, `_threshold_display_from_alert` (lines 283–406) | → | `app/utils/config_renderer.py` | Pure helpers, packaged with the renderer that uses them. |
| ├ `generate_prometheus_alerts_yaml`, `generate_alertmanager_yaml`, custom YAML representer (lines 18–30, 408–1180) | → | `app/utils/config_renderer.py` | Bulk of the rendering logic. |
| ├ Email templates `GLOBAL_/TENANT_EMAIL_SUBJECT/BODY_TEMPLATE` (lines 540–700) | → | DROP — import from `app/utils/email_templates.py` | **Deduplicates** identical strings now living in `alert_management.py:1643–1730`. |
| ├ `write_yaml_file`, `trigger_prometheus_reload`, `trigger_alertmanager_reload` (search file for these) | → | `app/utils/config_renderer.py` | Thin httpx wrappers, kept alongside the YAML generators since they're always called together. |
| ├ `sync_configuration`, `sync_lock`, `sync_in_progress`, `periodic_sync`, `run_periodic_sync` (lines 1190–1335) | → | `app/services/alert-management/sync_service.py` | Class-ify (DI'd via `dependencies/services.py`). The periodic loop lives here too — no need for a separate `scheduler.py`. Started from platform-core's `lifespan()` — see §5. |
| ├ `POST /sync`, `GET /health`, FastAPI app, lifespan (lines 1337–1419) | → | **DROP `/sync` endpoint entirely** (no longer needed — alert-mgmt CRUD calls `sync_service.sync_configuration()` directly in-process), DROP `/health` (use platform-core's), DROP lifespan (extend platform-core's). | The whole point of merging is that the HTTP hop disappears. |
| `Dockerfile` | → | DROP | platform-core's Dockerfile + new volume mounts. |
| `requirements.txt` | → | Add `pyyaml>=6.0` to platform-core's `requirements.txt`. | |
| `.env` (434 lines — actually a global master env) | → | Diff against platform-core's `.env`/`env.template` | Only the alert-specific keys matter (§5). |

---

## 5. Cross-cutting concerns to resolve before implementation

### Database

- **All alert tables move into `ai4iplatform_core`** (per latest decision). `alerting_db` is decommissioned. The alert ORM models in `app/models/alert_management/` register against platform-core's existing `Base`, alongside model-management's `Model` and `Service` tables. No second engine is needed for alerting.
- `auth_db` remains a separate, read-only engine (RBAC + tenant email lookup). So platform-core ends up with **two engines total**: primary `ai4iplatform_core` (model-management + alert tables) and secondary `auth_db`.
- `app/core/database.py` currently re-exports a single `init_database`/`get_db`. Extend it (or wrap `ai4icore_core.bootstrap.database` locally) to register a second engine and produce a `get_auth_db` dependency. **Confirm with the user**: add the multi-engine helper to `ai4icore_core`, or wrap locally?
- **Data migration from `alerting_db` → `ai4iplatform_core` is required** if any environment has live alerting data. Two viable approaches: (a) a one-off `pg_dump` + restore into the new DB, run after the new schema migration but before the cut-over; (b) a logical sync (Foreign Data Wrapper or COPY-based) for zero-downtime. Pick before step 9. If no environment has meaningful alerting data yet, the migration step can be skipped — confirm per-environment.
- `alerting_db` itself can be dropped after the cut-over once data is verified in the new home. Until then, keep it readable but stop writing to it (the merged service writes only to `ai4iplatform_core`).

### Alembic / migration scripts

- **Delete** the `_load_alerting_metadata()` entry from `infrastructure/databases/migrations/postgres/alembic/migration_registry.py:164–169` along with any `alerting_db` chain registration. Alert tables now live in `ai4iplatform_core` and are picked up by the existing `_load_core_service_metadata` loader at line 179 — just make sure `app/models/__init__.py` imports every file under `app/models/alert_management/` so they register with platform-core's `Base`.
- **Add a new Alembic revision** in the `ai4iplatform_core` chain that creates the alert tables: `alert_definitions`, `alert_annotations`, `notification_receivers`, `routing_rules`, `alert_history`. Schema is identical to today's `alerting_db` (copy from revision `d7df939ec69b`); the only change is *which DB* the tables live in. Run `alembic revision --autogenerate -m "add alert tables"` after step 3 of §6 to generate it; review the auto-output and edit if it drops anything unexpected.
- The pre-existing `alerting_db` revision chain (`d7df939ec69b_auto_20260416_155237`) becomes orphaned — keep it on disk until the `alerting_db` is decommissioned, then delete the chain along with the registry entry.
- **Per-environment data migration** (if any data is worth saving):
  - Quick path: `pg_dump --data-only --table=alert_definitions ... alerting_db | psql ai4iplatform_core` for each table. Schedule during a short maintenance window after the new schema migration runs but before traffic is cut over.
  - Foreign-key order matters: `notification_receivers` and `alert_definitions` before `routing_rules` (which references both); `alert_definitions` before `alert_annotations`; `alert_history` last.

### Dockerfile / compose

- Files to update:
  - `docker-compose-local.yml` lines 1263–1364: **delete** both `alert-management-service` and `alert-config-sync-service` service blocks.
  - Find platform-core's service block and add the env vars + volume mounts that sync needs:
    - Volumes: `./infrastructure/prometheus/rules:/etc/prometheus/rules`, `./infrastructure/alertmanager:/etc/alertmanager`.
    - Depends-on: `prometheus`, `alertmanager`.
    - Env: `PROMETHEUS_URL`, `ALERTMANAGER_URL`, `PROMETHEUS_APPLICATION_ALERTS_PATH`, `PROMETHEUS_INFRASTRUCTURE_ALERTS_PATH`, `ALERTMANAGER_CONFIG_PATH`, `SYNC_INTERVAL`, `ALERT_SYNC_ENABLED`, `DEFAULT_RECEIVER_EMAILS`, `AUTH_DB_NAME`.
- API gateway updates:
  - `services/api-gateway-service/gateways/nginx/nginx.conf:118,158–161` — change `set $upstream_alert_mgmt http://alert-management-service:8098;` to `http://platform-core-service:8095;`, and change the rewrite rule from `^/api/v1/alerts/(.*) /alerts/$1` to a straight pass-through `proxy_pass $upstream_alert_mgmt;` (since the merged service will mount alert routes under `/api/v1/alerts/...` natively).
  - `services/api-gateway-service/gateways/apisix/apisix.yaml:61,103,114` — same change: upstream node → `platform-core-service:8095`, drop the regex rewrite that strips `/api/v1`, update `X-Service` header to `platform-core-service`.

### Env vars — full list to add to platform-core

Net-new (not already in platform-core's `env.template`):

```
AUTH_DB_NAME=auth_db
PROMETHEUS_URL=http://prometheus:9090
ALERTMANAGER_URL=http://alertmanager:9093
PROMETHEUS_APPLICATION_ALERTS_PATH=/etc/prometheus/rules/application-alerts.yml
PROMETHEUS_INFRASTRUCTURE_ALERTS_PATH=/etc/prometheus/rules/infrastructure-alerts.yml
ALERTMANAGER_CONFIG_PATH=/etc/alertmanager/alertmanager.yml
SYNC_INTERVAL=60
ALERT_SYNC_ENABLED=true
DEFAULT_RECEIVER_EMAILS=
ENVIRONMENT=development
```

And add new fields to `CoreSettings`: `auth_db_name` (for the secondary auth_db engine), plus all the sync-related fields above as `Optional[str]` so platform-core can still boot if alerts feature is disabled. Alert tables share the existing primary DB connection (`ai4iplatform_core`); no new DB-name field needed for alerting itself.

**Conflicts to watch:** `SERVICE_NAME` — alert services' `.env` has `SERVICE_NAME=alert-management-service`; that file (`services/alert-config-sync-service/.env`) is actually the **repo-wide master `.env`** copy and will continue to be loaded. After the merge, the merged service should run as `SERVICE_NAME=platform-core-service`. `PORT` collision: alert-mgmt uses 8098, sync uses 8097, platform-core uses 8095 — keep 8095, drop the others.

### Background task lifecycle

- platform-core's current `lifespan()` (`app/main.py:27–46`) calls `init_database` + `init_redis`. Extend it to:
  1. **After** `init_database`, spawn the periodic-sync task only if `settings.alert_sync_enabled` is true: `app.state.sync_task = asyncio.create_task(run_periodic_sync())`.
  2. On shutdown, cancel/await as in `alert-config-sync-service/main.py:1344–1362`.
- The sync function should accept a session factory (DI'd from platform-core's database module), not import a global `db_pool`.
- Manual sync trigger (currently `POST /sync` in sync service) becomes a direct function call inside the alert-mgmt service methods after every CRUD write — search for `trigger_config_sync` calls in `alert_management.py` and replace with `await sync_service.sync_configuration(blocking=False)` (or push a one-shot event). Recommend non-blocking to keep API latency low.

### Cross-service URL references

Searched the repo for `alert-management-service` / `alert-config-sync-service` / `ALERT_MANAGEMENT_SERVICE_URL` / `ALERT_CONFIG_SYNC_SERVICE_URL`. The only callers outside the two services themselves are:

- `docker-compose-local.yml` (already covered).
- `services/api-gateway-service/gateways/nginx/nginx.conf:118,158–161` (already covered).
- `services/api-gateway-service/gateways/apisix/apisix.yaml:61,103,114` (already covered).
- `infrastructure/alertmanager/alertmanager.default.yml` (Alertmanager → alert-management webhook for history). Update that webhook target from `http://alert-management-service:8098/alerts/history/webhook` to `http://platform-core-service:8095/api/v1/alerts/history/webhook`. **(Check this file.)**
- `infrastructure/databases/migrations/postgres/alembic/migration_registry.py:164` (already covered).
- `docs/ALERTING_ARCHITECTURE.md` and `.github/analysis/DRY_PRINCIPLE_ANALYSIS.md` (docs only — update after code is stable).

No other service code calls these endpoints. Safe to retarget.

---

## 6. Migration step order (each step leaves repo buildable)

0. **Relocate existing platform-core files into the new subfolders.** Dedicated PR before any alert work. Mechanical move + import updates, no renames:
   - `models/model.py` → `models/model_management/model.py` (same for `service.py`)
   - `repositories/model_repository.py` → `repositories/model_management/model_repository.py` (same for `service_repository.py`)
   - `schemas/model.py` → `schemas/model_management/model.py` (same for `service.py`)
   - `schemas/enums.py` → `schemas/enums/model_management.py` (relocate into new `enums/` sub-package)
   - `services/model_service.py` → `services/model-management/model_service.py` (same for `service_service.py`, `serializers.py`)
   - `routes/`, `utils/`, `core/`, `dependencies/` — unchanged
   - Update every import inside `app/` and search the rest of the repo for callers (other services may import platform-core schemas/utils directly).
1. **Add `pyyaml>=6.0`** to `services/platform-core-service/requirements.txt`. Add new env keys (sync-related + `AUTH_DB_NAME`) to `env.template` + `CoreSettings` (all `Optional[...]` so nothing breaks). Add a secondary `auth_db` engine + `get_auth_db` dep wired through `app/core/database.py` (decide approach with user first — see §7 risk). Alert tables share the primary `ai4iplatform_core` engine — no separate alerting engine. Repo still builds; alert services untouched.
2. **Schemas first.** Create the new alert sub-package: `app/schemas/alert_management/` with `alert_definition.py`, `receiver.py`, `routing_rule.py`, `history.py`. Also add `app/schemas/enums/alert_management.py` (severity, category, urgency, rbac_role). Lift Pydantic models verbatim from `alert_management.py:380–635`. No routes wire to them yet — buildable.
3. **Models.** Create `app/models/alert_management/` with `alert_definition.py`, `notification_receiver.py`, `routing_rule.py`, `alert_history.py`. Register them in `app/models/__init__.py`. Until `migration_registry.py` is repointed they're metadata-only inside platform-core's Base — verify `alembic check` doesn't try to drop them. (May need to keep them detached or under a separate Base if they live in a different DB.) **Important decision** — see Risks (§7).
4. **Repositories.** Create 4 thin repos under `app/repositories/alert_management/`. No callers yet.
5. **Utils first, then services.** Create `app/utils/promql_builder.py`, `app/utils/email_templates.py`, `app/utils/config_renderer.py` (pure helpers, no DB, no prefix). Then create `app/services/alert-management/` with the 5 domain services (`definition_service.py`, `receiver_service.py`, `routing_rule_service.py`, `history_service.py`, `sync_service.py`). The services depend on the repositories from step 4, the schemas from step 2, and the utils from this step.
6. **Dependencies factory.** Add `get_definition_service`, `get_receiver_service`, `get_routing_rule_service`, `get_history_service`, `get_sync_service` to `app/dependencies/services.py`. Hyphenated `services/alert-management/` and `services/model-management/` folder names mean these factories will need `importlib.import_module(...)` — see §7. Add `app/dependencies/auth.py` (moved `auth_deps`).
7. **Routes.** Create the single consolidated `app/routes/alert.py` aggregating the four resource routers (definitions, receivers, routing_rules, history) as `APIRouter` instances under one module-level `router`. Update `app/routes/__init__.py` to include `router` in `v1_router`. At this point hitting the merged service at `/api/v1/alerts/...` should work, but the old alert-mgmt is still up. Run side-by-side; smoke test.
8. **Wire sync into lifespan.** Extend `app/main.py:lifespan` to spawn `run_periodic_sync()` and cancel on shutdown. Set `ALERT_SYNC_ENABLED=false` initially in the platform-core env to avoid double-writes against `/etc/prometheus/rules/`.
9. **Alembic — create alert tables in `ai4iplatform_core`.** Generate a new revision (`alembic revision --autogenerate -m "add alert tables"`) on platform-core's chain after the alert ORM models from step 3 are registered with `Base`. Review the auto-generated revision, fix anything dropped unexpectedly, then `alembic upgrade head` on `ai4iplatform_core`. If any environment has live data in `alerting_db`, run the per-environment data migration described in §5 Database (table-by-table `pg_dump --data-only` → `psql`, respecting FK order: `notification_receivers` + `alert_definitions` → `routing_rules` + `alert_annotations` → `alert_history`). Delete the `_load_alerting_metadata()` registration from `migration_registry.py`. The `alerting_db` chain stays on disk until cut-over completes; drop the DB itself afterwards.
10. **Cut over the gateway.** Update `nginx.conf` + `apisix.yaml` to send `/api/v1/alerts/*` to `platform-core-service:8095` without the rewrite. Update `infrastructure/alertmanager/alertmanager.default.yml` webhook target. Update `docker-compose-local.yml`: add the sync volume mounts + Prometheus/Alertmanager `depends_on` to platform-core, set `ALERT_SYNC_ENABLED=true`. Stop and remove the two standalone services.
11. **Delete the old directories.** `git rm -r services/alert-management-service services/alert-config-sync-service`.
12. **Docs.** Update `docs/ALERTING_ARCHITECTURE.md`, `README.md`, `.github/analysis/DRY_PRINCIPLE_ANALYSIS.md`.

Each step is a separate PR-sized change; steps 2–6 are pure adds and don't risk regressing prod.

---

## 7. Risks and open questions

- **Step 0 is a mechanical move of existing platform-core files into subfolders — no renames.** Files keep their existing names; only their import paths change (e.g., `app.models.model` → `app.models.model_management.model`). Every existing import inside platform-core AND every external caller in other services needs updating. **Action item before coding:** grep the entire repo for these import paths: `from services.platform_core_service.app.models.model`, `from app.models.model`, `from app.services.model_service`, `from app.schemas.enums`, etc. Itemise the call sites so step 0 has a checklist. Lower risk than a rename because the file content doesn't change — but the import-path churn is still wide.
- **Hyphenated `services/alert-management/` and `services/model-management/` still break Python imports.** `from app.services.alert-management.definition_service import DefinitionService` is a parse error — every reference to those two folders will need `importlib.import_module("app.services.alert-management.definition_service")`. The other new subfolders (`models/alert_management/`, `repositories/model_management/`, `schemas/alert_management/`, `schemas/enums/`, …) use underscores and import cleanly. **Strongly recommend** confirming with management whether the literal hyphen is still required for `services/`, or whether `services/alert_management/` + `services/model_management/` (underscores) is acceptable — that makes the imports trivial and matches the convention used everywhere else. The doc keeps hyphens for `services/` to match the literal user constraint; this is the single biggest avoidable pain point left.
- **Common-vs-domain classification needs verification.** The table in §3 is my best guess based on filenames. Before step 0, **open each file and confirm**: does `schemas/enums.py` only contain model-management enums, or are some used elsewhere? Is `services/serializers.py` truly model-management-only? A common file accidentally moved into a domain subfolder is a worse outcome than a domain file left at the top level.
- **All organization-related logic is being dropped.** `VALID_ORGANIZATIONS`, the MD5 hash mapping, and every call site that branches on `organization` must be removed during the migration. **Action item before coding:** grep the entire alert-mgmt codebase for `organization` and `org_id` and decide per call site whether to delete the logic or replace with `tenant` semantics. Quick scan needed: schema columns, PromQL injection (`inject_organization_into_promql`), audit-log fields (irrelevant since audit is dropped too), routing-rule matchers.
- **Audit logging is being dropped.** Drop `utils/audit_logger.py` (the 450-line module), drop the `audit_log` table from the alert models, remove every `audit_logger.log_*` call site in `alert_management.py`, and delete the corresponding Alembic columns/tables. **Action item before coding:** check whether any external consumer (dashboard, reporting tool) reads the `alert_config_audit_log` table — if so, the deletion has to coordinate with them.
- **Data migration from `alerting_db` → `ai4iplatform_core`.** Decision is settled (one DB), but the migration mechanics still need a plan per environment. **Action items before step 9:** (1) inventory which environments have non-trivial data in `alerting_db` — local dev usually doesn't, staging and prod do; (2) confirm the maintenance window with stakeholders; (3) decide between offline `pg_dump`/`psql` (simpler, ~minutes of downtime) and a logical-replication / FDW-based sync (no downtime, more setup). Verify row counts post-migration before deleting `alerting_db`.
- **Tracing / Jaeger.** alert-management-service uses `ai4icore_telemetry` + `FastAPIInstrumentor`. platform-core's `main.py` explicitly says "No tracing or observability — logging only". Either add tracing to the merged service (recommended — keep alert observability) or drop tracing from alerts on merge.
- **Hyphen in `services/alert-management/`** is a valid folder name but not a valid Python package — `import app.services.alert-management.foo` will not work. All imports from that folder must go through `importlib.import_module("app.services.alert-management.foo")` or use sys.path tricks. **Strongly recommend** discussing with user whether the literal `alert-management/` is intended or if `alert_management/` (underscore) is OK; if literal hyphen, the service-class wiring in `dependencies/services.py` will need importlib. Same caveat applies to `routes/alert/`, `models/alert/`, `schemas/alert/` (these are named with no hyphen — confirm).
- **Webhook auth.** `POST /alerts/history/webhook` is currently auth-free, relying on container-network isolation. After the merge it sits behind the same gateway as authenticated routes — the APISIX/nginx route for that one path needs `auth_request off;` carved out, or Alertmanager needs to send a service-to-service token.
- **Periodic sync writing to disk under a multi-worker uvicorn.** platform-core's Dockerfile runs `uvicorn --workers 4` — that's 4 processes, and the sync task would be spawned in each, racing to write the same YAML files. Either (a) gate sync to worker 0 only via env-var trick, (b) drop `--workers 4`, or (c) move the background task to a sidecar/cron. Decide before coding.
- **Alert ORM models must register with platform-core's existing `Base`** — not a local `declarative_base()`. Since alert tables now live in `ai4iplatform_core`, they need to share the same metadata as `Model` / `Service` so Alembic's autogenerate sees them. Verify `app/models/alert_management/*.py` does `from app.models import Base` (not its own `declarative_base()` call), and that `app/models/__init__.py` imports every alert model so they actually register.

---

## Critical files for implementation

- `services/alert-management-service/alert_management.py`
- `services/alert-config-sync-service/main.py`
- `services/platform-core-service/app/main.py`
- `services/platform-core-service/app/core/config.py`
- `services/platform-core-service/app/routes/__init__.py`
- `infrastructure/databases/migrations/postgres/alembic/migration_registry.py`
- `docker-compose-local.yml`
