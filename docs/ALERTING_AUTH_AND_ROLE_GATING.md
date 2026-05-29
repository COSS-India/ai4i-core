# Alerting Authorization — how "admin-only" is actually enforced

A short reference on how the alert APIs ensure only permitted users (e.g. only
ADMIN can create/delete) can perform operations — both in the old
`alert-management-service` and after the move to `platform-core-service`.

## TL;DR

- **Real enforcement lives in auth-service, at the gateway hop — not in the
  alert service.** Every request through the gateway triggers a
  `forward-auth`/`auth_request` subrequest to `auth-service /api/v1/auth/validate`,
  which authorizes the caller against the endpoint's required permission and
  returns `403` if they lack it. The request never reaches the alert service.
- **The mapping is permission-based RBAC.** `api_permissions.json` maps each
  `METHOD:/api/v1/alerts/...` endpoint to a required permission id; the caller's
  JWT carries their `permission_ids`. ADMIN is seeded with **all** permissions,
  so "only ADMIN can create" falls out naturally.
- **The alert service's own `X-Roles` check is secondary.** The
  `require_alerts_*` dependencies are defense-in-depth and were always inert
  (nothing injects `X-Roles` — see §4), but that never mattered because the
  authoritative gate is upstream.
- **The migration preserves enforcement.** The endpoint paths
  (`/api/v1/alerts/*`) are unchanged and `api_permissions.json` already lists
  them, so once the gateway routes alerts to platform-core (done), admin-only
  enforcement keeps working with no extra wiring.

## 1. The real enforcement path (auth-service `/validate`)

The gateway runs an auth subrequest on every request, forwarding the caller's
token plus `X-Original-Method` and `X-Original-URI`. `auth-service /validate`
(`auth-service/app/routes/validation.py`) then:

1. Identifies the caller — anonymous, API key, or JWT — and validates the token.
2. Looks up the **permission required** for `METHOD:URI` via
   `PermissionChecker.get_required_permission(...)`
   (`auth-service/app/core/permission_checker.py:59`), which does an exact match
   then a path-template match (so `/alerts/definitions/123` matches the
   `{alert_id}` template).
3. Checks that permission id against the caller's `permission_ids` (from the JWT
   claims / API-key record). If missing → returns
   `403 INSUFFICIENT_PERMISSIONS` (`validation.py:154-155`).

The gateway propagates that `403` straight back to the client; the alert
service is never called. Endpoints with no required permission are treated as
public.

## 2. The alert permission map

`auth-service/api_permissions.json:110-127` defines the required permission per
alert endpoint. Summary:

| Operation | Endpoints | Permission id | Name |
|---|---|---|---|
| Read | `GET` definitions / receivers / routing-rules / history | `116` | `alerts.read` |
| Create | `POST` definitions / receivers / routing-rules | `117` | `alerts.create` |
| Update | `PUT` + `PATCH .../enabled`, `.../timing` | `118` | `alerts.update` |
| Delete | `DELETE` definitions / receivers / routing-rules | `119` | `alerts.delete` |

A user holds a permission if one of their roles grants it. **ADMIN is seeded
with every permission** (`permission_checker.py:100-102`), so ADMIN passes all
four; a role lacking `alerts.create` (117) gets `403` on any create. That is
how "only admin can create alerts" is — and was — enforced.

## 3. How `alert-management-service` did it (identical model)

The old service relied on the **same** centralized gate. It was deployed behind
the same gateway, its `/api/v1/alerts/*` endpoints were (and still are) listed
in `api_permissions.json`, and every request hit `auth-service /validate` first.
So admin-only creation was enforced upstream, exactly as above — not by the
service itself.

Its own `utils/auth_deps.py:12-63` *also* declared role checks
(`require_alerts_{create,read,update,delete}`, gating writes on
`ADMIN`/`MODERATOR`). But those read an `X-Roles` request header that, as §4
shows, nothing in the platform produces — so that in-service layer was
effectively a no-op. It didn't weaken anything because the authoritative
permission check already happened at the gateway.

## 4. Why the in-service `X-Roles` check is inert

A repo-wide search shows `X-Roles` is **only ever read, never written**: by the
old alert deps, telemetry
(`telemetry-service/routers/observability_router.py:145`), and policy-service
(`policy-service/app/core/auth.py:9`) — and set by **no** code path.
(platform-core's alert deps used to read it too but no longer do — see §5.)

- `auth-service /validate` returns `roles` only in its JSON **body**
  (`validation.py:163-170`), never as a response header; the service has zero
  `X-Roles` references. `auth_request` / `forward-auth` can only capture
  *headers*, so roles never become a forwardable header.
- nginx forwards only `X-User-Id` + `X-Tenant-Id` (`nginx.conf`).
- APISIX lists `X-Roles` in the `forward-auth` `upstream_headers` allowlist on a
  few routes (`apisix.yaml:1553/1752/1970`), but it's inert — `upstream_headers`
  can only forward what the auth response contains, and `/validate` never sets
  it. The alerts route doesn't list it at all.

This is why the service-level role gate can't be relied on — but again, it's
secondary to the auth-service permission check.

## 5. Migration impact and what changed

- **Enforcement is preserved.** Authorization keys on the original request URI
  (`X-Original-URI` = `/api/v1/alerts/...`, set before any internal rewrite) and
  the JWT's permissions. Both are unchanged by the move, and the alert paths are
  already in `api_permissions.json`. Once the gateway routes
  `/api/v1/alerts/*` to platform-core (now done in `nginx.conf` + `apisix.yaml`),
  admin-only enforcement continues to work with no extra config.
- **The in-service auth layer was removed entirely.** `app/dependencies/auth.py`
  (the `require_alerts_*` deps) is deleted, along with `X-Roles` and the
  redundant `ADMIN`/`MODERATOR` checks. This is safe: the real gate is upstream
  at auth-service, and direct/Swagger calls that bypass the gateway never had
  enforcement anyway (same as inference-service).
- **`X-User-ID` and actor attribution were dropped too.** `_actor()`, the
  `created_by`/`updated_by` plumbing, and the corresponding columns on
  `alert_definitions` / `notification_receivers` / `routing_rules` (and the
  response-schema fields) were removed — they were audit attribution, not used
  by alerting functionality. `alert_history` (the triggered-alert log behind
  `GET /alerts/history`) is unrelated and untouched.

## 6. If you want the in-service check to be real too

Optional defense-in-depth (not required for correctness, since the gateway
already enforces):

- **Inject `X-Roles` at the gateway** — make `auth-service /validate` emit an
  `X-Roles` response header, capture it in nginx
  (`auth_request_set $auth_roles $upstream_http_x_roles;` +
  `proxy_set_header X-Roles $auth_roles;`), and ensure the alerts route lists
  `X-Roles` in the APISIX `upstream_headers`.
- **Or resolve roles in-service from `auth_db`** — platform-core already
  connects to `auth_db`; look up the user's roles by `X-User-Id` instead of
  trusting a header.
