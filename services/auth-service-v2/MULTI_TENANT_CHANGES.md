## Multi-Tenant Changes (Auth Service v2)

This document summarizes the multi-tenant related updates implemented in `auth-service-v2`, including tenant lifecycle enforcement, tenant-scoped admin authorization, request-time validation, and the caching strategy.

### Key behavior changes

1. `auth-service-v2` can optionally connect to the shared multi-tenant database via `MULTI_TENANT_DB_URL` to resolve `tenant_id` and tenant lifecycle status.
2. Login and refresh are blocked when a tenant (tenant admin) or tenant user is suspended/deactivated. Tenant admins are blocked using `Tenant.status`, and tenant users are blocked using both `Tenant.status` and `TenantUser.status`.
3. Tenant lifecycle status is enforced on every token validation call (`/auth/validate`) to cut off suspended/deactivated accounts on the next request.
4. Tenant admin routes are restricted so an admin can only act on users within their own tenant.
5. Session revocation is supported for tenant suspension/deactivation by exposing an admin endpoint that invalidates sessions for all users inside a tenant.

### Configuration

`services/auth-service-v2/env.template` adds:
- `MULTI_TENANT_DB_URL`: async SQLAlchemy URL for the multi-tenant DB (used for tenant resolution/status lookups).

Startup wiring:
- `services/auth-service-v2/app/main.py` checks `settings.multi_tenant_db_url`.
- If set, it creates an async engine + `app.state.multi_tenant_session_factory`.
- If not set (or connectivity fails), it disables tenant resolution/status checks and logs that tenant enforcement is disabled.

Settings definition:
- `services/auth-service-v2/app/core/config.py` introduces `multi_tenant_db_url`, `multi_tenant_db_pool_size`, and `multi_tenant_db_max_overflow`.

Runtime dependency:
- `services/auth-service-v2/Dockerfile` installs/copies `libs/ai4icore_multi_tenant` so `TenantService` can import `ai4icore_multi_tenant` at runtime.

### Tenant status resolution (TenantService)

Implemented in `services/auth-service-v2/app/services/tenant_service.py`.

Highlights:
- Uses ORM models from `ai4icore_multi_tenant` (`Tenant`, `TenantUser`) and avoids HTTP/raw SQL calls.
- Queries are protected with a timeout (`_TENANT_QUERY_TIMEOUT`) so auth is not blocked by multi-tenant DB slowness.
- If the multi-tenant library import fails (or the DB session factory is missing), tenant checks gracefully return `None` (meaning “do not block” during login/token validation).

Important methods:
- `resolve_and_cache_tenant_id(user_id, is_tenant)`: resolves tenant_id from the multi-tenant DB and returns it for caching on the auth user row.
- `get_tenant_status(tenant_id)`: returns `Tenant.status` for the given tenant_id.
- `get_tenant_status_by_user_id(user_id, is_tenant)`: fallback to resolve `Tenant.status` directly by mapping tenant admin/tenant user rows to an auth `user_id`.
- `get_tenant_user_status(tenant_id, user_id)`: returns `TenantUser.status` for tenant users.
- `debug_tenant_mappings(...)`: extra observability if tenant status lookups unexpectedly return `None`.

### Caching (Redis)

Implemented in `services/auth-service-v2/app/services/cache_service.py` and used by `TenantService`.

Cache keys:
- `auth:tenant_status:<tenant_id>`
- `auth:tenant_user_status:<tenant_id>:<user_id>`

Design notes:
- Short TTL caching is used for the validate/login hot paths (`_TENANT_STATUS_CACHE_TTL_SECONDS = 60` inside `TenantService`).
- `CacheService.delete_tenant_status(tenant_id)` is used after session revocation operations so future requests pick up fresh lifecycle state.

### User tenant fields (caching inputs)

Multi-tenant checks rely on fields stored on the auth `User` model:
- `services/auth-service-v2/app/models/user.py` adds `is_tenant` (True for tenant admins, False for tenant users) and `tenant_id_cached` (tenant identifier cached on the user row).
- `services/auth-service-v2/app/schemas/auth.py` (`RegisterRequest`) accepts `tenant_id` and `is_tenant` so the multi-tenant service can cache tenant context on user creation/association.

### Login blocking (AuthService)

Implemented in `services/auth-service-v2/app/services/auth_service.py`.

Flow:
1. `AuthService.login` / `refresh_token` resolves `tenant_id` (only if missing on the auth user row) using `TenantService.resolve_and_cache_tenant_id(...)`.
2. Calls `_enforce_login_tenant_status(user)` before issuing tokens.
3. Enforcement rules: If `Tenant.status` is `SUSPENDED` or `DEACTIVATED`, login is blocked with error code `TENANT_INACTIVE`. If the user is a tenant user (`user.is_tenant is False`) and `TenantUser.status` is `SUSPENDED` or `DEACTIVATED`, login is blocked with error code `TENANT_USER_INACTIVE`.
4. Fallback behavior: If `Tenant.status` cannot be resolved (returns `None`), auth attempts one retry by re-resolving tenant_id and also tries `get_tenant_status_by_user_id(...)`. If tenant status still cannot be resolved, login is not blocked (it logs structured debug info and continues).

`TenantUser.status` interpretation:
- Implemented by `is_suspended_or_deactivated(...)` in `tenant_service.py`, which treats `SUSPENDED`/`DEACTIVATED` (case-insensitive, enum-safe) as inactive states.

### Permissions surface: `multi_tenant`

`services/auth-service-v2/api_permissions.json` includes a `multi_tenant` permission resource.

`services/auth-service-v2/app/services/role_service.py` excludes `multi_tenant` from platform-level inference permission assignment lists (to avoid automatically inferring `multi_tenant` onto admin/guest surfaces).

### Request validation enforcement (/auth/validate)

Implemented in `services/auth-service-v2/app/routes/validation.py`.

What happens:
- APISIX calls `GET/POST /auth/validate` for each request.
- `auth-service-v2` verifies the JWT using the shared `ai4icore_auth` JWT verifier.
- If multi-tenant session factory is available and `user_id` is present, it resolves `tenant_id` from `user.tenant_id_cached` or `claims.tenant_id`, then checks cached/DB tenant lifecycle states and returns `401` with `TENANT_INACTIVE` or `TENANT_USER_INACTIVE` as appropriate.

Role-specific enforcement:
- Tenant admins check only `Tenant.status`, while tenant users check both `Tenant.status` and `TenantUser.status`.

### Protected-route dependency enforcement

Implemented in `services/auth-service-v2/app/dependencies/auth.py` (`get_current_user`).

Behavior:
- For non-validate endpoints, it also enforces tenant lifecycle status using `TenantService` (fast-path cache-first).
- It intentionally treats `/auth/validate` as the stronger source-of-truth recheck path.

### Tenant admin scoping for routes

Implemented in `services/auth-service-v2/app/dependencies/tenant_scope.py`.

Role-based rule:
- `TENANT ADMIN` can only operate on users within their own tenant.
- The check is enforced via `enforce_tenant_scope(...)` from `ai4icore_multi_tenant` using `target.tenant_id_cached` for the target user and caller tenant id from `request.state.tenant_id` (JWT) or `current_user.tenant_id_cached`.

### Session revocation endpoint (used by multi-tenant service)

Implemented in `services/auth-service-v2/app/routes/auth.py`.

Endpoint:
- `POST /auth/sessions/revoke-by-tenant/{tenant_id}`

Usage:
- The multi-tenant service calls this endpoint when a tenant is suspended/deactivated.
- Auth will: Resolve all auth `user_id`s belonging to the tenant via `TenantService.get_tenant_user_ids(tenant_id)`, invalidate sessions for those users (`SessionService.invalidate_all_for_users`), and clear cached tenant status for that tenant (`cache.delete_tenant_status(tenant_id)`).

### Multi-tenant DB migration dependency (suspension tagging)

Linked migration:
- `infrastructure/databases/migrations/postgres/alembic/versions/multi_tenant_db/9f2b1d4a6c77_add_suspension_tag_to_tenant_users.py`

What it changes:
- Adds nullable column `tenant_users.suspension_tag` of enum `tenantusersuspensiontag` with values `ADMIN_SUSPENDED` and `TENANT_SUSPENDED`.

Why auth-service-v2 cares:
- `auth-service-v2` itself blocks login based on `TenantUser.status` and `Tenant.status`.
- The `suspension_tag` column is used by `multi-tenant-feature` to preserve/track *why* a tenant-user is suspended, and to ensure correct status transitions during tenant suspension/deactivation reactivation.

Relevant code link (how tag drives status):
- `services/multi-tenant-feature/services/tenant_service.py` sets `tenant_user.status = SUSPENDED` and assigns `tenant_user.suspension_tag = ADMIN_SUSPENDED` for admin-driven tenant deactivation, or `tenant_user.suspension_tag = TENANT_SUSPENDED` for tenant-level lifecycle suspension/deactivation.

### Files changed/introduced (multi-tenant related)

- `services/auth-service-v2/env.template`
- `services/auth-service-v2/app/main.py`
- `services/auth-service-v2/app/services/tenant_service.py`
- `services/auth-service-v2/app/services/auth_service.py`
- `services/auth-service-v2/app/services/cache_service.py`
- `services/auth-service-v2/app/services/role_service.py`
- `services/auth-service-v2/app/core/config.py`
- `services/auth-service-v2/app/models/user.py`
- `services/auth-service-v2/app/schemas/auth.py`
- `services/auth-service-v2/app/routes/validation.py`
- `services/auth-service-v2/app/dependencies/auth.py`
- `services/auth-service-v2/app/dependencies/tenant_scope.py`
- `services/auth-service-v2/app/routes/auth.py`
- `services/auth-service-v2/api_permissions.json`
- `infrastructure/databases/migrations/postgres/alembic/versions/multi_tenant_db/9f2b1d4a6c77_add_suspension_tag_to_tenant_users.py`
- `services/auth-service-v2/Dockerfile`

