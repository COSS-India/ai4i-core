"""
Token validation endpoint — called by APISIX via forward-auth on every
request through the gateway.

Two-step flow:
  1. Identify the caller (anonymous / hex API key / JWT) and validate the
     token if one is presented.
  2. Authorize: check the caller's permission_ids against the permission
     required by X-Original-Method:X-Original-URI.
"""

import base64
import binascii
import json
import logging
from functools import lru_cache
from urllib.parse import quote

from ai4i_core.ppu import get_inference_types
from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

from app.core.jwt_verifier import JWTExpiredError, JWTVerificationError
from app.core.permission_checker import endpoint_permission_map_loaded, permission_checker
from app.core.redis import get_redis
from app.core.exceptions import AuthenticationRequiredError, InvalidAPIKeyError
from app.dependencies.auth import check_token_revocation, get_jwt_verifier
from app.schemas.api_key import ValidateAPIKeyErrorResponse, ValidateAPIKeyResponse
from app.schemas.token import TokenValidationResponse
from app.services.api_key_service import APIKeyService
from app.services.cache_service import CacheService
from app.services.tenant_name_cache import tenant_name_cache


@lru_cache(maxsize=1)
def _service_by_path() -> dict[str, dict]:
    """Concrete request path → inference-type entry, built once from the yaml.

    The gateway serves a fixed, known path set, so resolution is a single
    exact lookup — no prefix scanning. Every path an entry serves comes from
    the yaml itself: endpoint_pattern plus any endpoint_aliases. Unknown paths
    (unified /api/v1/inference, try-it, audio passthrough) resolve to None.
    """
    table: dict[str, dict] = {}
    for entry in get_inference_types():
        table[entry["endpoint_pattern"]] = entry
        for alias in entry.get("endpoint_aliases", []):
            table[alias] = entry
    return table


def _resolve_service(uri: str) -> dict | None:
    """Map X-Original-URI to its inference type — one dict lookup."""
    return _service_by_path().get(uri.split("?", 1)[0].rstrip("/"))


router = APIRouter(prefix="/auth", tags=["Validation"])


def is_jwt_strict(token: str) -> bool:
    """Return True only when token is a 3-part JWT with alg=RS256 in the header."""
    parts = token.split(".")
    if len(parts) != 3:
        return False
    try:
        padding = (4 - len(parts[0]) % 4) % 4
        header = json.loads(base64.urlsafe_b64decode(parts[0] + "=" * padding))
        return header.get("alg") == "RS256"
    except (binascii.Error, json.JSONDecodeError, UnicodeDecodeError, AttributeError) as exc:
        logger.debug("JWT header validation failed: %s", exc.__class__.__name__)
        return False


def _required_endpoint_permission(request: Request) -> tuple[bool, int | None]:
    """Look up the permission required for X-Original-Method:X-Original-URI.

    Returns:
      (False, None) — gateway didn't set X-Original-* (direct call) OR the
                      permission checker isn't loaded yet. Caller decides.
      (True,  None) — endpoint is public (no permission required).
      (True,  <id>) — endpoint requires this permission.
    """
    method = request.headers.get("X-Original-Method")
    uri = request.headers.get("X-Original-URI")
    if not (method and uri):
        return False, None
    # Fail closed while the endpoint→permission map hasn't loaded: "couldn't
    # look up" (False) — NOT "public" (True, None) — so anonymous access stays
    # denied if startup failed to load api_permissions.json.
    if not endpoint_permission_map_loaded():
        return False, None
    return True, permission_checker.get_required_permission(method, uri.split("?", 1)[0])


def _check_endpoint_permission(request: Request, permission_ids: list[int]) -> bool:
    """Authorize a caller's permission_ids against the endpoint's required perm.

    Allow when: gateway didn't signal an endpoint (direct call), OR the
    endpoint is public, OR the caller holds the required permission.
    """
    looked_up, required = _required_endpoint_permission(request)
    if not looked_up:
        return True
    return required is None or required in permission_ids


def _set_tenant_headers(response: Response, tenant_id: object) -> None:
    """Set X-Tenant-ID (numeric id) and X-Tenant-Name (organisation) on the response.

    X-Tenant-Name is what the observability middleware uses as the Prometheus
    ``tenant`` label value; it's resolved from the in-memory tenant_name_cache
    (no DB round trip on this hot path — see tenant_name_cache.py). Falls back
    to the id itself on a cache miss (e.g. a tenant created moments before this
    worker's next refresh) so the label is never empty for a real tenant.

    Starlette encodes header values as latin-1, but organisation names accept
    any Unicode letter (see _check_org_chars in schemas/tenant.py) — a name
    with e.g. Devanagari or Tamil characters would raise UnicodeEncodeError
    here and 500 the whole /validate call. Percent-encode it when it isn't
    latin-1 encodable; the observability middleware decodes it back.
    """
    response.headers["X-Tenant-ID"] = str(tenant_id)
    name = None
    try:
        name = tenant_name_cache.get_name(int(tenant_id))
    except (TypeError, ValueError):
        pass
    name = name or str(tenant_id)
    try:
        name.encode("latin-1")
    except UnicodeEncodeError:
        name = quote(name, safe="")
    response.headers["X-Tenant-Name"] = name


def _extract_token(request: Request) -> str:
    """Pull the bearer token from the Authorization header, or empty string."""
    raw = request.headers.get("Authorization", "").strip()
    if raw.lower().startswith("bearer "):
        return raw[7:].strip()
    return raw


# ── Per-token-type validators ─────────────────────────────────────────────


def _validate_anonymous(request: Request) -> Response:
    """No token: allow only when X-Original-* point at a public endpoint."""
    looked_up, required = _required_endpoint_permission(request)
    if looked_up and required is None:
        resp = JSONResponse(
            content=TokenValidationResponse(valid=True).model_dump(),
            headers={"X-User-ID": "", "X-Tenant-ID": ""}
        )
        return resp
    raise AuthenticationRequiredError()


async def _validate_api_key(
    token: str,
    request: Request,
    response: Response,
    api_key_svc: APIKeyService,
) -> Response:
    """Hex API key path — Redis-only validation, then endpoint authz."""
    try:
        result = await api_key_svc.validate_api_key(token)
    except InvalidAPIKeyError:
        return JSONResponse(
            status_code=401,
            content=ValidateAPIKeyErrorResponse(error="API key not found or revoked.", message="API key not found or has been revoked.").model_dump(),
        )

    permission_ids = result.get("permissions") or result.get("permission_ids") or []
    if not _check_endpoint_permission(request, permission_ids):
        return JSONResponse(status_code=403, content={"valid": False, "error": "INSUFFICIENT_PERMISSIONS", "message": "You do not have permission to access this endpoint."})

    user_id = result.get("user_id")
    tenant_id = result.get("tenant_id")

    # ── PPU enforcement — decided HERE, not in APISIX ──────────────────────
    # APISIX only forward-auths (and rate-limits); a 429 from this endpoint
    # flows through the gateway to the client unchanged. The exhaustion flags
    # are written onto the API-key record by the billing consumer.
    exhausted_services = sorted(
        k[len("quota-"):]
        for k, v in result.items()
        if k.startswith("quota-") and v == "1"
    )
    quota_header = {"X-Quota-Exhausted-Services": ",".join(exhausted_services)}

    if result.get("budget-exhausted") == "1":
        return JSONResponse(
            status_code=429,
            content={
                "valid": False,
                "error": "BUDGET_EXHAUSTED",
                "message": "Tenant budget is exhausted for the current billing period.",
            },
            headers=quota_header,
        )

    service = _resolve_service(request.headers.get("X-Original-URI", ""))
    if service and service["name"] in exhausted_services:
        return JSONResponse(
            status_code=429,
            content={
                "valid": False,
                "error": "QUOTA_EXCEEDED",
                "message": f"Quota exhausted for service '{service['name']}' in the current billing period.",
                "service": service["name"],
            },
            headers=quota_header,
        )

    if user_id:
        response.headers["X-User-ID"] = str(user_id)
    # No X-User-Plan header: the plan is fully derivable from X-Auth-Type
    # (api_key ⇒ P2, jwt ⇒ P1) and nothing consumes it.
    response.headers["X-Tier-ID"] = result.get("tier_id") or ""
    # Informational — always set, unconditionally (empty when nothing is exhausted).
    response.headers["X-Quota-Exhausted-Services"] = ",".join(exhausted_services)

    response.headers["X-Auth-Type"] = "api_key"
    response.headers["X-Permission-IDS"] = "[" + ",".join(str(p) for p in permission_ids) + "]"
    if tenant_id:
        _set_tenant_headers(response, tenant_id)
    return ValidateAPIKeyResponse(valid=True, user_id=user_id, permission_ids=permission_ids)


async def _validate_jwt(
    token: str,
    request: Request,
    response: Response,
    cache_svc: CacheService,
) -> Response:
    """JWT path — verify signature, check revocation, then endpoint authz."""
    try:
        claims = await get_jwt_verifier().verify(token)
    except JWTExpiredError:
        return JSONResponse(status_code=401, content={"valid": False, "error": "TOKEN_EXPIRED", "message": "Token has expired."})
    except JWTVerificationError:
        return JSONResponse(status_code=401, content={"valid": False, "error": "TOKEN_INVALID", "message": "Token is invalid."})

    # Not gated on claims.token_id: access tokens carry `jti`, not `token_id`
    # (only api_key tokens set token_id) — the global-logout check below keys
    # off user_id/issued_at instead, so it must run for access tokens too.
    if await check_token_revocation(
        claims.token_id,
        claims.token_type,
        cache_svc,
        user_id=str(claims.user_id) if claims.user_id else None,
        issued_at=claims.raw.get("iat"),
    ):
        return JSONResponse(status_code=401, content={"valid": False, "error": "TOKEN_REVOKED", "message": "Token has been revoked."})

    if not _check_endpoint_permission(request, claims.permission_ids):
        return JSONResponse(status_code=403, content={"valid": False, "error": "INSUFFICIENT_PERMISSIONS", "message": "You do not have permission to access this endpoint."})

    if claims.user_id:
        response.headers["X-User-ID"] = str(claims.user_id)
    response.headers["X-Tier-ID"] = ""
    response.headers["X-Auth-Type"] = claims.token_type
    response.headers["X-Permission-IDS"] = "[" + ",".join(str(p) for p in claims.permission_ids) + "]"
    if claims.tenant_id:
        _set_tenant_headers(response, claims.tenant_id)
    # Permission id 1 is the "admin" sentinel (only the ADMIN role holds it).
    # Forward a trusted flag so upstream services can widen scope (e.g. cross-tenant
    # trace access) without re-resolving roles or hitting the DB.
    return TokenValidationResponse(
        valid=True,
        user_id=claims.user_id,
        username=claims.username,
        tenant_id=claims.tenant_id,
        permission_ids=claims.permission_ids,
        roles=claims.roles,
        token_type=claims.token_type,
    )


# APISIX forward-auth issues GET; the original client method travels in
# X-Original-Method. Don't add POST defensively — no caller uses it, and
# silent 405s on config drift are easier to spot.
@router.get("/validate")
async def validate_token(
    request: Request,
    response: Response,
    redis=Depends(get_redis),
):
    """Step 1: identify (anon / API key / JWT). Step 2: each branch authorizes.

    DB is only acquired for the API-key branch; JWT and anonymous paths never
    open a connection, keeping the gateway hot path as cheap as possible.
    """
    token = _extract_token(request)
    if not token:
        return _validate_anonymous(request)

    cache_svc = CacheService(redis)

    if is_jwt_strict(token):
        return await _validate_jwt(token, request, response, cache_svc)

    # API key path — validates against Redis cache only, no DB needed
    api_key_svc = APIKeyService(None, cache_svc)
    return await _validate_api_key(token, request, response, api_key_svc)
