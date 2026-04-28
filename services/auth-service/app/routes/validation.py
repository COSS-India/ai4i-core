"""
Token validation endpoint — called by APISIX for every request.
Uses the shared ai4icore_auth JWTVerifier.
"""

import logging

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from ai4icore_core.auth.jwt_verifier import AuthClaims, JWTExpiredError, JWTVerificationError

from app.core.database import get_db
from app.core.exceptions import AuthenticationRequiredError, InvalidAPIKeyError
from app.core.security import key_manager
from app.dependencies.auth import _check_token_revocation, get_jwt_verifier
from app.dependencies.services import get_api_key_service, get_cache_service, get_user_service
from app.schemas.api_key import ValidateAPIKeyErrorResponse, ValidateAPIKeyResponse
from app.schemas.token import TokenValidationResponse
from app.services.api_key_service import APIKeyService
from app.services.cache_service import CacheService
from app.services.tenant_service import TenantService, is_suspended_or_deactivated
from app.services.user_service import UserService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Validation"])

security = HTTPBearer(auto_error=False)


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


def _tenant_inactive_message() -> str:
    return "Tenant access is restricted. Contact your administrator."


def _user_inactive_message(user_status: str) -> str:
    return f"User is {user_status.lower()}, please contact your admin"


@router.get("/validate")
@router.post("/validate")
async def validate_token(
    request: Request,
    response: Response,
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    cache_svc: CacheService = Depends(get_cache_service),
    user_svc: UserService = Depends(get_user_service),
    api_key_svc: APIKeyService = Depends(get_api_key_service),
    db: AsyncSession = Depends(get_db),
):
    # Extract token — accept both "Bearer <token>" and raw "<token>"
    raw_auth = request.headers.get("Authorization", "").strip()
    if raw_auth.lower().startswith("bearer "):
        token = raw_auth[7:].strip()
    elif raw_auth:
        token = raw_auth
    elif credentials is not None:
        token = credentials.credentials
    else:
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
        user_id = result.get("user_id")
        if user_id:
            response.headers["X-User-ID"] = str(user_id)
        return ValidateAPIKeyResponse(
            valid=True,
            user_id=user_id,
            permission_ids=result.get("permission_ids", []),
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

    username = None
    if claims.user_id:
        user = await user_svc.get_user_by_id(claims.user_id)
        if not user:
            # Backward compatibility: API key validation should still succeed
            # even if the owning user record was deleted.
            if claims.token_type != "api_key":
                return JSONResponse(status_code=401, content={"valid": False, "error": "USER_NOT_FOUND"})
            logger.warning(
                "API key token validated with missing user record: user_id=%s token_id=%s",
                claims.user_id,
                claims.token_id,
            )
            user = None

        if user and not user.is_active:
            return JSONResponse(status_code=401, content={"valid": False, "error": "USER_INACTIVE"})

        if user:
            username = user.username

        if user and user.tenant_id:
            tenant_service = TenantService(db, cache_svc)
            tenant_id_str = str(user.tenant_id)

            tenant_status = await tenant_service.get_tenant_status_cached(tenant_id_str)
            if is_suspended_or_deactivated(tenant_status):
                return JSONResponse(
                    status_code=401,
                    content={
                        "valid": False,
                        "error": "TENANT_INACTIVE",
                        "message": _tenant_inactive_message(),
                    },
                )

            if user.is_tenant_active is False:
                return JSONResponse(
                    status_code=401,
                    content={
                        "valid": False,
                        "error": "TENANT_USER_INACTIVE",
                        "message": _user_inactive_message("deactivated"),
                    },
                )

    # Backward-compatible: keep JSON body and add user id header for consumers
    if claims.user_id:
        response.headers["X-User-ID"] = str(claims.user_id)

    return TokenValidationResponse(
        valid=True,
        user_id=claims.user_id,
        username=username,
        tenant_id=claims.tenant_id,
        permission_ids=claims.permission_ids,
        roles=claims.roles,
        token_type=claims.token_type,
    )


@router.get("/.well-known/jwks.json")
async def jwks():
    return key_manager.get_jwks()
