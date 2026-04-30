"""
Token validation endpoint — called by APISIX for every request.
Uses the shared ai4icore_auth JWTVerifier.
"""

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from ai4icore_auth.jwt_verifier import AuthClaims, JWTExpiredError, JWTVerificationError

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
    import base64
    import json as _json
    parts = token.split(".")
    if len(parts) != 3:
        return False
    try:
        padding = 4 - len(parts[0]) % 4
        header = _json.loads(base64.urlsafe_b64decode(parts[0] + "=" * padding))
        return header.get("alg") == "RS256"
    except Exception:
        return False


async def _check_endpoint_permission(
    request: Request,
    permission_ids: list[int],
) -> bool:
    """
    True if the caller may invoke X-Original-Method:X-Original-URI.
    Missing headers => direct call, skip the check.
    """
    method = request.headers.get("X-Original-Method")
    uri = request.headers.get("X-Original-URI")
    if not (method and uri):
        return True

    from app.main import get_permission_checker
    checker = get_permission_checker()
    if checker is None:
        return False  # fail closed

    required = await checker.get_required_permission(method, uri.split("?", 1)[0])
    return required is None or required in permission_ids


@router.get("/validate")
@router.post("/validate")
async def validate_token(
    request: Request,
    response: Response,
    cache_svc: CacheService = Depends(get_cache_service),
    api_key_svc: APIKeyService = Depends(get_api_key_service),
    db: AsyncSession = Depends(get_db),
):
    # Extract token — accept both "Bearer <token>" and raw "<token>"
    raw_auth = request.headers.get("Authorization", "").strip()
    if raw_auth.lower().startswith("bearer "):
        token = raw_auth[7:].strip()
    elif raw_auth:
        token = raw_auth
    else:
        # No token. Allow only when X-Original-* identify a public endpoint.
        method = request.headers.get("X-Original-Method")
        uri = request.headers.get("X-Original-URI")
        if method and uri:
            from app.main import get_permission_checker
            checker = get_permission_checker()
            if checker is not None:
                required = await checker.get_required_permission(method, uri.split("?", 1)[0])
                if required is None:
                    return TokenValidationResponse(valid=True)
        raise AuthenticationRequiredError()

    # Hex API key path — Redis only, zero DB calls
    if not is_jwt_strict(token):
        try:
            result = await api_key_svc.validate_api_key(token)
        except InvalidAPIKeyError:
            return JSONResponse(
                status_code=401,
                content=ValidateAPIKeyErrorResponse(
                    error="API key not found or revoked."
                ).model_dump(),
            )
        permission_ids = result.get("permission_ids") or []
        if not await _check_endpoint_permission(request, permission_ids):
            return JSONResponse(status_code=403, content={"valid": False, "error": "INSUFFICIENT_PERMISSIONS"})

        user_id = result.get("user_id")
        if user_id:
            response.headers["X-User-ID"] = str(user_id)
        response.headers["X-User-Plan"] = USER_PLAN_APIKEY
        response.headers["X-Auth-Type"] = "api_key"
        tenant_id = result.get("tenant_id")
        if tenant_id:
            response.headers["X-Tenant-ID"] = str(tenant_id)
        return ValidateAPIKeyResponse(
            valid=True,
            user_id=user_id,
            permission_ids=permission_ids,
        )

    # JWT path — existing flow unchanged
    verifier = get_jwt_verifier()

    try:
        claims: AuthClaims = await verifier.verify(token)
    except JWTExpiredError:
        return JSONResponse(status_code=401, content={"valid": False, "error": "TOKEN_EXPIRED"})
    except JWTVerificationError:
        return JSONResponse(status_code=401, content={"valid": False, "error": "TOKEN_INVALID"})

    if claims.token_id:
        revoked = await _check_token_revocation(
            claims.token_id, claims.token_type, cache_svc, db,
        )
        if revoked:
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


@router.get("/.well-known/jwks.json")
async def jwks():
    return key_manager.get_jwks()
