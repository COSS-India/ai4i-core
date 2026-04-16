"""
Token validation endpoint — called by APISIX for every request.
Uses the shared ai4icore_auth JWTVerifier.

Zero-DB: JWT verification + Redis revocation check only.
User/tenant status enforcement happens at login time and via
event-driven session revocation — not on every request.
"""

import logging

from fastapi import APIRouter, Depends, Response
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from ai4icore_auth.jwt_verifier import AuthClaims, JWTExpiredError, JWTVerificationError

from app.core.exceptions import AuthenticationRequiredError
from app.core.security import key_manager
from app.dependencies.auth import get_jwt_verifier
from app.dependencies.services import get_cache_service
from app.schemas.token import TokenValidationResponse
from app.services.cache_service import CacheService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Validation"])

security = HTTPBearer(auto_error=False)


@router.get("/validate")
@router.post("/validate")
async def validate_token(
    response: Response,
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    cache_svc: CacheService = Depends(get_cache_service),
) -> TokenValidationResponse:
    if credentials is None:
        raise AuthenticationRequiredError()

    verifier = get_jwt_verifier()

    try:
        claims: AuthClaims = await verifier.verify(credentials.credentials)
    except JWTExpiredError:
        return JSONResponse(status_code=401, content={"valid": False, "error": "TOKEN_EXPIRED"})
    except JWTVerificationError:
        return JSONResponse(status_code=401, content={"valid": False, "error": "TOKEN_INVALID"})

    # Redis-only revocation check (no DB fallback — keeps validate zero-DB)
    if claims.token_id:
        if claims.token_type == "api_key":
            is_valid = await cache_svc.is_api_key_valid(claims.token_id)
        else:
            is_valid = await cache_svc.is_refresh_token_valid(claims.token_id)
        if not is_valid:
            return JSONResponse(status_code=401, content={"valid": False, "error": "TOKEN_REVOKED"})

    if claims.user_id:
        response.headers["X-User-ID"] = str(claims.user_id)

    return TokenValidationResponse(
        valid=True,
        user_id=claims.user_id,
        username=None,
        tenant_id=claims.tenant_id,
        permission_ids=claims.permission_ids,
        roles=claims.roles,
        token_type=claims.token_type,
    )


@router.get("/.well-known/jwks.json")
async def jwks():
    return key_manager.get_jwks()
