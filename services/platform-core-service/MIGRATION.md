# Platform-Core-Service Migration Document

**Date:** 2026-04-27  
**Author:** Platform Engineering  
**Source Service:** `services/model-management-service`  
**Target Service:** `services/platform-core-service`  
**Status:** Implementation complete — parallel operation during migration window

---

## 1. What Was Migrated

### 1.1 Model Management

| Feature | Source file(s) | Target file(s) |
|---|---|---|
| Model CRUD (list, get, create, update, delete) | `routers/router_models.py`, `db_operations.py` | `app/routes/model.py`, `app/services/model_service.py`, `app/repositories/model_repository.py` |
| Deterministic model-id generation (`sha256(name:version)[:32]`) | `db_operations.py::generate_model_id` | `app/utils/hashing.py::generate_model_id` |
| Max-active-version enforcement | `db_operations.py::save_model_to_db` | `app/services/model_service.py::ModelService.create_model` |
| Published-service immutability lock (update + delete) | `db_operations.py::update_model`, `delete_model_by_uuid` | `app/services/model_service.py::ModelService.update_model`, `delete_model` |
| Deprecated-version update gating | `db_operations.py::update_model` | `app/services/model_service.py::ModelService.update_model` |
| Cascade-delete of unpublished services on model delete | `db_operations.py::delete_model_by_uuid` | `app/services/model_service.py::ModelService.delete_model` |
| Task-type enum (11 values: nmt, tts, asr, llm, …) | `models/type_enum.py` | `app/schemas/enums.py::TaskTypeEnum` |
| License enum (30+ values) | `models/type_enum.py` | `app/schemas/enums.py::LicenseEnum` |
| Name format validation (alphanumeric + hyphen + slash) | `models/model_create.py` | `app/schemas/common.py::validate_entity_name` |
| License format validation (case-insensitive normalisation) | `models/model_create.py` | `app/schemas/common.py::validate_license` |
| ModelViewResponse (camelCase, legacy compat) | `models/model_view.py` | `app/schemas/model.py::ModelResponse` |

### 1.2 Service Management

| Feature | Source file(s) | Target file(s) |
|---|---|---|
| Service CRUD (list, get, create, update, delete) | `routers/router_services.py`, `db_operations.py` | `app/routes/service.py`, `app/services/service_service.py`, `app/repositories/service_repository.py` |
| Deterministic service-id generation (`sha256(name)[:32]`) | `db_operations.py::generate_service_id` | `app/utils/hashing.py::generate_service_id` |
| Endpoint validation (URL format + SSRF guard + live probe) | `validators/endpoint_validator.py`, `utils/endpoint_security.py`, `utils/probe_payloads.py` | `app/utils/endpoint_validator.py`, `app/utils/security.py`, `app/utils/probe_payloads.py` |
| Triton V2 probe payload builder | `utils/probe_payloads.py::build_triton_v2_payload` | `app/utils/probe_payloads.py::build_triton_v2_payload` |
| ULCA probe payload builder (all 11 task types) | `utils/probe_payloads.py::build_ulca_payload` | `app/utils/probe_payloads.py::build_ulca_payload` |
| Service publish/unpublish with `published_at`/`unpublished_at` | `db_operations.py::update_service` | `app/services/service_service.py::ServiceService.update_service` |
| Published-service delete protection | `db_operations.py::delete_service_by_uuid` | `app/services/service_service.py::ServiceService.delete_service` |
| Service health update (heartbeat) | `db_operations.py::update_service_health`, `routers/router_services.py` | `app/services/service_service.py::ServiceService.update_service_health` |
| Service policy CRUD with cross-field constraints | `db_operations.py::add_or_update_service_policy` | `app/services/service_service.py::ServiceService.upsert_policy`, `_validate_policy` |
| Policy constraints (tier_1 + sensitive/low-latency) | `db_operations.py::add_or_update_service_policy` | `app/services/service_service.py::_validate_policy` |
| Services-with-policies list (SMR use) | `db_operations.py::list_services_with_policies` | `app/services/service_service.py::ServiceService.list_policies` |
| Public try-it service list (NMT only) | `routers/router_services.py::list_services_try_it` | `app/routes/service.py::list_try_it_services` |
| Service inference-server type enum | `models/inference_server_type.py` | `app/schemas/enums.py::InferenceServerTypeEnum` |

### 1.3 Infrastructure

| Feature | Source | Target |
|---|---|---|
| Redis model/service cache (create, update, invalidate) | `db_operations.py` inline + `models/cache_models_services.py` | `app/services/cache_service.py::CacheService` |
| Request logging middleware | `middleware/request_logging.py` | `app/middleware/request_logging.py` (re-exports from `ai4icore_logging`) |
| Auth/permission middleware | `middleware/auth_provider.py` | `ai4icore_auth.AuthMiddleware` + `create_auth_providers()` |
| SSRF protection | `utils/endpoint_security.py` | `app/utils/security.py` |
| App settings | `ai4icore_env` (implicit) | `app/core/config.py::CoreSettings` |
| Health endpoints | `routers/router_health.py` | `app/routes/health.py` via `ai4icore_bootstrap.health.create_health_router` |

---

## 2. What Was Improved / Refactored

### 2.1 Architecture — Clean Layered Separation

The old service mixed all database access, business logic, validation, and HTTP handling in two monolithic files (`db_operations.py` ~3 127 lines, `routers/router_models.py`, `routers/router_services.py`). Platform-core-service enforces strict four-layer separation:

```
Route layer   →  app/routes/          (HTTP only, no business logic)
Service layer →  app/services/        (business rules, orchestration)
Repository    →  app/repositories/    (pure DB access, no rules)
ORM models    →  app/models/          (schema definition only)
```

### 2.2 Async-First Redis Caching

The old service used **redis-om HashModel** (a sync Redis client wrapped in thread-pool calls) tied to a schema-specific cache format. Platform-core-service uses the platform's shared **async Redis client** (`ai4icore_bootstrap.redis`) with plain JSON and explicit TTLs. This:
- Eliminates the sync/async impedance mismatch.
- Decouples cache format from Pydantic schema changes.
- Allows key-level TTL control per entity type.
- Supports graceful degradation (cache miss → DB fallback, no error).

### 2.3 DB Timestamps — DateTime Instead of BigInteger Epoch

The legacy schema stored `submitted_on`, `updated_on`, and `published_on` as BigInteger UNIX epoch values (lossy, no timezone). Platform-core-service uses `DateTime(timezone=True)` throughout with `server_default=func.now()` and `onupdate=func.now()`. API responses that previously exposed epoch integers now expose ISO-8601 strings — consumers should prefer the ISO form.

### 2.4 Consistent Exception Hierarchy

The old service raised bare `HTTPException` throughout. Platform-core-service raises typed exceptions from `ai4icore_exceptions` (e.g. `EntityNotFoundError`, `ValidationError`, `AppError` subclasses like `ImmutableModelVersionError`). A shared `register_exception_handlers` converts these to the platform's standard `{success, error: {code, message}}` envelope.

### 2.5 Single-Responsibility Configuration

All settings live in `app/core/config.py::CoreSettings` (pydantic-settings, env-file + OS env, case-insensitive). Backwards-compatible `PLATFORM_CORE_SERVICE_DB_*` or `APP_DB_*` env-var aliases ensure existing deployments need no changes to their `.env` files.

### 2.6 API Response Envelope Consistency

Every successful response is wrapped by `success_response(data=..., meta=...)` from `ai4icore_exceptions`. Every error is a typed exception converted to `error_response`. The old service returned bare strings, bare dicts, and raw Pydantic models inconsistently. Platform-core-service standardizes all responses.

### 2.7 DB Index Coverage

Platform-core-service ORM adds explicit named indexes missing from the legacy schema:
- `ix_models_name`, `ix_models_created_by`
- `ix_services_is_published`, `ix_services_created_by`

These speed up the most common query filters (`task_type`, `created_by`, `is_published`).

### 2.8 Explicit Named Constraints

All `UniqueConstraint` and `ForeignKeyConstraint` definitions now carry explicit `name=` arguments. This makes Alembic autogenerate diff-detection reliable and makes migrations easier to review.

### 2.9 Policy Validation Moved to Service Layer

In the old service, policy cross-field validation lived inside `db_operations.add_or_update_service_policy`. It is now a pure function `_validate_policy` in the service layer — testable independently of the database.

---

## 3. What Was Explicitly Excluded

### 3.1 A/B Testing / Experimentation

**All** A/B testing code is excluded from this migration. This includes:

| Component | Old location | Decision |
|---|---|---|
| `Experiment`, `ExperimentVariant`, `ExperimentMetrics` ORM models | `models/db_models.py` | Not migrated |
| `ExperimentStatus` enum | `models/db_models.py` | Not migrated |
| All experiment Pydantic schemas | `models/ab_testing.py` | Not migrated |
| `router_experiments.py` (both authenticated + public) | `routers/` | Not migrated |
| `create_experiment`, `get_experiment`, `list_experiments`, `update_experiment`, `update_experiment_status`, `delete_experiment`, `select_experiment_variant`, `track_experiment_metric` | `db_operations.py` | Not migrated |
| `_check_duplicate_running_experiment` | `db_operations.py` | Not migrated |
| `experiments`, `experiment_variants`, `experiment_metrics` DB tables | Schema | Not created in platform-core-service |
| Test files: `test_ab_testing_api.py`, `test_ab_testing_db_operations.py`, `test_ab_testing_models.py` | `tests/` | Not migrated |

**Reason:** A/B testing is a self-contained feature domain that is either being deprecated, extracted to a dedicated experimentation service, or deferred to a later migration phase. Mixing it into the initial platform-core-service migration would widen scope significantly and risk destabilising the core model/service CRUD path.

### 3.2 Auth DB Tables

The old service connected to **two** PostgreSQL databases: `model_management_db` (models, services, experiments) and `auth_db` (users, api_keys, sessions, roles, permissions). Platform-core-service connects to a **single** database (`core_db`) and delegates all auth concerns to `auth-service` via JWT. The auth DB tables are not replicated or accessed by platform-core-service.

### 3.3 Legacy Redis-Om Cache Models

`models/cache_models_services.py` (`ModelCache`, `ServiceCache` HashModel classes) are replaced entirely by the new async `CacheService`. The redis-om library is not added as a dependency of platform-core-service.

### 3.4 Sync Migration / Restore Scripts

The utility scripts `migrate_model_id_to_hash.py`, `migrate_service_id_to_hash.py`, `restore_from_backup.py`, `restore_from_backup_v2.py` are not migrated — they are one-time operational tools that should remain in the model-management-service repository for use during the data-migration phase.

### 3.5 Rate-Limiting Middleware

The custom Redis sliding-window rate limiter from `middleware/rate_limit_middleware.py` is not replicated locally. Rate limiting in the new architecture is enforced at the API gateway layer (APISIX). If per-service rate limiting is needed, it can be added via `ai4icore_bootstrap.rate_limit`.

---

## 4. Structural & Architectural Decisions

### 4.1 Single Database

Platform-core-service uses one PostgreSQL database (`core_db`) instead of the legacy two-database setup. This simplifies connection management, eliminates cross-DB join complexity, and reduces operational surface area.

### 4.2 Deterministic ID Contract Preserved

`model_id = sha256(lower(name):lower(version))[:32]` and `service_id = sha256(lower(name))[:32]` are preserved exactly. Existing gateway configurations, cached references, and consumer integrations that hold model/service IDs will continue to work without ID migration.

### 4.3 camelCase API Contract Preserved

The response schemas intentionally preserve the camelCase key names used by the legacy service (`modelId`, `serviceId`, `versionStatus`, `inferenceEndPoint`, etc.). This allows consumer-side cutover without schema changes. New endpoints added in the future will use snake_case.

### 4.4 Auth via Shared Library

Platform-core-service does not implement its own JWT verification or permission store. It uses:
- `ai4icore_auth.AuthMiddleware` for JWT context extraction
- `create_auth_providers()` for route-level permission enforcement (reads endpoint→permission map from Redis DB 0, populated by auth-service at startup)

### 4.5 Multi-Domain Extensibility

The directory structure is designed for easy addition of new feature domains without structural changes:

```
app/
  models/{domain}.py          ← new ORM model
  schemas/{domain}.py         ← new Pydantic schemas
  repositories/{domain}_repository.py
  services/{domain}_service.py
  routes/{domain}.py
```

Just register the new router in `app/routes/__init__.py` and add a DI factory in `app/dependencies/services.py`.

### 4.6 DateTime Over Epoch for Timestamps

Published/unpublished timestamps are now `DateTime(timezone=True)` columns rather than BigInteger epoch. The serializer (`app/services/serializers.py`) emits ISO-8601 strings in API responses for maximum interoperability. Backward-compat aliases (`submittedOn`, `publishedAt`) compute epoch/ISO from `created_at`/`published_at` in platform-core-service.

### 4.7 Cache Invalidation Strategy

- **On create**: warm cache immediately (model + service entries).
- **On update**: invalidate all versions for the entity, re-warm from the freshly committed DB row.
- **On delete**: invalidate the entity + any cascade-deleted related entities.
- **Cache miss**: transparent DB fallback; no error surfaced to the caller.
- **TTL**: configurable via env (`MODEL_CACHE_TTL_SECONDS`, `SERVICE_CACHE_TTL_SECONDS`), default 1 hour.

---

## 5. Deprecated Code / Endpoints in Model-Management-Service

The following is now deprecated in `model-management-service` in favour of platform-core-service equivalents:

| Deprecated endpoint | Replacement |
|---|---|
| `GET /api/v1/model-management/models` | `GET /api/v1/models` |
| `GET /api/v1/model-management/models/{model_id}` | `GET /api/v1/models/{model_id}` |
| `POST /api/v1/model-management/models/{model_id}` | `POST /api/v1/models/{model_id}` |
| `POST /api/v1/model-management/models` | `POST /api/v1/models` |
| `PATCH /api/v1/model-management/models` | `PATCH /api/v1/models` |
| `DELETE /api/v1/model-management/models/{model_id}` | `DELETE /api/v1/models/{model_id}` |
| `GET /api/v1/model-management/services` | `GET /api/v1/services` |
| `GET /api/v1/model-management/services/try-it-service-list` | `GET /api/v1/services/try-it-service-list` |
| `GET /api/v1/model-management/services/policies` | `GET /api/v1/services/policies` |
| `POST /api/v1/model-management/services/{service_id}` | `POST /api/v1/services/{service_id}` |
| `POST /api/v1/model-management/services` | `POST /api/v1/services` |
| `PATCH /api/v1/model-management/services` | `PATCH /api/v1/services` |
| `DELETE /api/v1/model-management/services/{service_id}` | `DELETE /api/v1/services/{service_id}` |
| `PATCH /api/v1/model-management/services/{service_id}/health` | `PATCH /api/v1/services/{service_id}/health` |
| `POST /api/v1/model-management/services/{service_id}/policy` | `POST /api/v1/services/{service_id}/policy` |

**A/B testing endpoints** (`/experiments/*`) have no replacement in platform-core-service and should remain in model-management-service until a dedicated experimentation service is built or the feature is removed.

---

## 6. Migration Cutover Plan

1. **Phase 1 (current):** Deploy platform-core-service alongside model-management-service. Both share the same Redis. platform-core-service uses a new `core_db` PostgreSQL database. platform-core-service is reachable at host port **8102** (container port 8095; 8095 is occupied by speaker-diarization-service).
2. **Phase 2:** Run data migration script to copy existing models/services rows from `model_management_db.models` / `model_management_db.services` → `core_db.models` / `core_db.services`. IDs are preserved (deterministic hashes).
3. **Phase 3:** Update API gateway routes to point `/models` and `/services` paths to `platform-core-service:8095` instead of `model-management-service:8094`.
4. **Phase 4:** Validate all consumers (frontends, other services) against platform-core-service. Run traffic shadow comparison.
5. **Phase 5:** Decommission model-management-service (remove from `docker-compose.yml`, archive the codebase).

---

## 7. File Inventory

```
services/platform-core-service/
├── app/
│   ├── main.py                           FastAPI app factory + lifespan
│   ├── core/
│   │   ├── config.py                     CoreSettings (pydantic-settings)
│   │   ├── database.py                   Re-export ai4icore_bootstrap.database
│   │   ├── exceptions.py                 Re-export ai4icore_exceptions
│   │   ├── redis.py                      Re-export ai4icore_bootstrap.redis
│   │   └── responses.py                  Re-export success_response / error_response
│   ├── models/
│   │   ├── __init__.py                   Base + Model + Service exports
│   │   ├── model.py                      Model ORM + VersionStatus enum
│   │   └── service.py                    Service ORM
│   ├── schemas/
│   │   ├── base.py                       Re-export BaseSchema
│   │   ├── enums.py                      TaskTypeEnum, LicenseEnum, InferenceServerTypeEnum, policy enums
│   │   ├── common.py                     Shared sub-schemas (InferenceEndPoint, Submitter, etc.)
│   │   ├── model.py                      ModelCreateRequest, ModelUpdateRequest, ModelResponse
│   │   └── service.py                    ServiceCreateRequest, ServiceUpdateRequest, ServiceResponse, etc.
│   ├── repositories/
│   │   ├── __init__.py
│   │   ├── model_repository.py           ModelRepository (async CRUD + filters)
│   │   └── service_repository.py         ServiceRepository (async CRUD + filters)
│   ├── services/
│   │   ├── __init__.py
│   │   ├── cache_service.py              Async Redis JSON cache for models/services
│   │   ├── model_service.py              ModelService (business logic)
│   │   ├── service_service.py            ServiceService (business logic)
│   │   └── serializers.py               ORM → API response dict conversion
│   ├── routes/
│   │   ├── __init__.py                   APIVersioning aggregation
│   │   ├── health.py                     /health + /ready (shared bootstrap)
│   │   ├── model.py                      /models CRUD routes
│   │   └── service.py                    /services CRUD + policy + health routes
│   ├── dependencies/
│   │   ├── __init__.py
│   │   ├── auth.py                       AuthProvider, OptionalAuthProvider, get_user_id
│   │   └── services.py                   DI factories for ModelService, ServiceService, CacheService
│   ├── middleware/
│   │   ├── __init__.py
│   │   └── request_logging.py            RequestLoggingMiddleware (shared lib re-export)
│   └── utils/
│       ├── __init__.py
│       ├── hashing.py                    generate_model_id, generate_service_id
│       ├── security.py                   SSRF protection, URL/log sanitization
│       ├── probe_payloads.py             Triton V2 + ULCA probe payload builders
│       └── endpoint_validator.py         Two-level endpoint validation orchestrator
├── tests/
├── api_permissions.json                  Endpoint → permission mapping
├── Dockerfile                            Python 3.12, multi-lib install, uvicorn
├── env.template                          All supported env vars with defaults
├── requirements.txt                      Python dependencies
└── MIGRATION.md                          This document
```
