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

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

from app.core.jwt_verifier import JWTExpiredError, JWTVerificationError
from app.core.redis import get_redis
from app.core.exceptions import AuthenticationRequiredError, InvalidAPIKeyError
from app.dependencies.auth import check_token_revocation, get_jwt_verifier
from app.schemas.api_key import ValidateAPIKeyErrorResponse, ValidateAPIKeyResponse
from app.schemas.token import TokenValidationResponse
from app.services.api_key_service import APIKeyService
from app.services.cache_service import CacheService

USER_PLAN_JWT: str = "P1"
USER_PLAN_APIKEY: str = "P2"

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


async def _required_endpoint_permission(request: Request) -> tuple[bool, int | None]:
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
    checker = getattr(request.app.state, "permission_checker", None)
    if checker is None:
        return False, None
    return True, checker.get_required_permission(method, uri.split("?", 1)[0])


async def _check_endpoint_permission(request: Request, permission_ids: list[int]) -> bool:
    """Authorize a caller's permission_ids against the endpoint's required perm.

    Allow when: gateway didn't signal an endpoint (direct call), OR the
    endpoint is public, OR the caller holds the required permission.
    """
    looked_up, required = await _required_endpoint_permission(request)
    if not looked_up:
        return True
    return required is None or required in permission_ids


def _extract_token(request: Request) -> str:
    """Pull the bearer token from the Authorization header, or empty string."""
    raw = request.headers.get("Authorization", "").strip()
    if raw.lower().startswith("bearer "):
        return raw[7:].strip()
    return raw


# ── Per-token-type validators ─────────────────────────────────────────────


async def _validate_anonymous(request: Request) -> Response:
    """No token: allow only when X-Original-* point at a public endpoint."""
    looked_up, required = await _required_endpoint_permission(request)
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
    if not await _check_endpoint_permission(request, permission_ids):
        return JSONResponse(status_code=403, content={"valid": False, "error": "INSUFFICIENT_PERMISSIONS", "message": "You do not have permission to access this endpoint."})

    user_id = result.get("user_id")
    tenant_id = result.get("tenant_id")
    if user_id:
        response.headers["X-User-ID"] = str(user_id)
    response.headers["X-User-Plan"] = USER_PLAN_APIKEY
    response.headers["X-Tier-ID"] = result.get("tier_id")
    response.headers["X-Budget-Exhausted"] = result.get("budget_exhausted")
    response.headers["X-Quota-Exhausted"] = result.get("quota_exhausted")
    response.headers["X-Auth-Type"] = "api_key"
    response.headers["X-Permission-IDS"] = "[" + ",".join(str(p) for p in permission_ids) + "]"
    if tenant_id:
        response.headers["X-Tenant-ID"] = str(tenant_id)
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

    if claims.token_id and await check_token_revocation(
        claims.token_id, claims.token_type, cache_svc,
    ):
        return JSONResponse(status_code=401, content={"valid": False, "error": "TOKEN_REVOKED", "message": "Token has been revoked."})

    if not await _check_endpoint_permission(request, claims.permission_ids):
        return JSONResponse(status_code=403, content={"valid": False, "error": "INSUFFICIENT_PERMISSIONS", "message": "You do not have permission to access this endpoint."})

    if claims.user_id:
        response.headers["X-User-ID"] = str(claims.user_id)
    response.headers["X-User-Plan"] = USER_PLAN_JWT
    response.headers["X-Tier-ID"] = ""
    response.headers["X-Budget-Exhausted"] = "false"
    response.headers["X-Quota-Exhausted"] = ""
    response.headers["X-Auth-Type"] = claims.token_type
    response.headers["X-Permission-IDS"] = "[" + ",".join(str(p) for p in claims.permission_ids) + "]"
    if claims.tenant_id:
        response.headers["X-Tenant-ID"] = str(claims.tenant_id)
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
        return await _validate_anonymous(request)

    cache_svc = CacheService(redis)

    if is_jwt_strict(token):
        return await _validate_jwt(token, request, response, cache_svc)

    # API key path — validates against Redis cache only, no DB needed
    api_key_svc = APIKeyService(None, cache_svc)
    return await _validate_api_key(token, request, response, api_key_svc)
