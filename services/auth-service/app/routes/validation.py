"""
Token validation endpoint — called by APISIX / nginx forward-auth on every
request through the gateway.

Two-step flow:
  1. Identify the caller (anonymous / hex API key / JWT) and validate the
     token if one is presented.
  2. Authorize: check the caller's permission_ids against the permission
     required by X-Original-Method:X-Original-URI.
"""

import base64
import json

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from ai4icore_auth.jwt_verifier import JWTExpiredError, JWTVerificationError

from app.core.database import get_db
from app.core.exceptions import AuthenticationRequiredError, InvalidAPIKeyError
from app.core.security import key_manager
from app.dependencies.auth import _check_token_revocation, get_jwt_verifier
from app.dependencies.services import get_api_key_service, get_cache_service
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
        padding = 4 - len(parts[0]) % 4
        header = json.loads(base64.urlsafe_b64decode(parts[0] + "=" * padding))
        return header.get("alg") == "RS256"
    except Exception:
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
    return True, await checker.get_required_permission(method, uri.split("?", 1)[0])


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
        return TokenValidationResponse(valid=True)
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
            content=ValidateAPIKeyErrorResponse(error="API key not found or revoked.").model_dump(),
        )

    permission_ids = result.get("permission_ids") or []
    if not await _check_endpoint_permission(request, permission_ids):
        return JSONResponse(status_code=403, content={"valid": False, "error": "INSUFFICIENT_PERMISSIONS"})

    user_id = result.get("user_id")
    tenant_id = result.get("tenant_id")
    if user_id:
        response.headers["X-User-ID"] = str(user_id)
    response.headers["X-User-Plan"] = USER_PLAN_APIKEY
    response.headers["X-Auth-Type"] = "api_key"
    if tenant_id:
        response.headers["X-Tenant-ID"] = str(tenant_id)
    return ValidateAPIKeyResponse(valid=True, user_id=user_id, permission_ids=permission_ids)


async def _validate_jwt(
    token: str,
    request: Request,
    response: Response,
    cache_svc: CacheService,
    db: AsyncSession,
) -> Response:
    """JWT path — verify signature, check revocation, then endpoint authz."""
    try:
        claims = await get_jwt_verifier().verify(token)
    except JWTExpiredError:
        return JSONResponse(status_code=401, content={"valid": False, "error": "TOKEN_EXPIRED"})
    except JWTVerificationError:
        return JSONResponse(status_code=401, content={"valid": False, "error": "TOKEN_INVALID"})

    if claims.token_id and await _check_token_revocation(
        claims.token_id, claims.token_type, cache_svc, db,
    ):
        return JSONResponse(status_code=401, content={"valid": False, "error": "TOKEN_REVOKED"})

    if not await _check_endpoint_permission(request, claims.permission_ids):
        return JSONResponse(status_code=403, content={"valid": False, "error": "INSUFFICIENT_PERMISSIONS"})

    if claims.user_id:
        response.headers["X-User-ID"] = str(claims.user_id)
    response.headers["X-User-Plan"] = USER_PLAN_JWT
    response.headers["X-Auth-Type"] = claims.token_type
    if claims.tenant_id:
        response.headers["X-Tenant-ID"] = str(claims.tenant_id)
    return TokenValidationResponse(
        valid=True,
        user_id=claims.user_id,
        username=claims.username,
        tenant_id=claims.tenant_id,
        permission_ids=claims.permission_ids,
        roles=claims.roles,
        token_type=claims.token_type,
    )


# nginx auth_request and APISIX forward-auth both issue GET; the original
# client method travels in X-Original-Method. Don't add POST defensively —
# no caller uses it, and silent 405s on config drift are easier to spot.
@router.get("/validate")
async def validate_token(
    request: Request,
    response: Response,
    cache_svc: CacheService = Depends(get_cache_service),
    api_key_svc: APIKeyService = Depends(get_api_key_service),
    db: AsyncSession = Depends(get_db),
):
    """Step 1: identify (anon / API key / JWT). Step 2: each branch authorizes."""
    token = _extract_token(request)
    if not token:
        return await _validate_anonymous(request)
    if is_jwt_strict(token):
        return await _validate_jwt(token, request, response, cache_svc, db)
    return await _validate_api_key(token, request, response, api_key_svc)


@router.get("/.well-known/jwks.json")
async def jwks():
    return key_manager.get_jwks()
