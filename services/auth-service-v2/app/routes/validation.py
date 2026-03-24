"""
Token validation endpoint — called by APISIX for every request.
Uses the shared ai4icore_auth JWTVerifier.
"""

import logging

from fastapi import APIRouter, Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from ai4icore_auth.jwt_verifier import AuthClaims, JWTExpiredError, JWTVerificationError

from app.core.database import get_db
from app.core.exceptions import AuthenticationRequiredError
from app.core.security import key_manager
from app.dependencies.auth import _check_token_revocation, get_jwt_verifier
from app.dependencies.services import get_cache_service, get_user_service
from app.schemas.token import TokenValidationResponse
from app.services.cache_service import CacheService
from app.services.user_service import UserService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Validation"])

security = HTTPBearer(auto_error=False)


@router.get("/validate")
@router.post("/validate")
async def validate_token(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    cache_svc: CacheService = Depends(get_cache_service),
    user_svc: UserService = Depends(get_user_service),
    db: AsyncSession = Depends(get_db),
) -> TokenValidationResponse:
    if credentials is None:
        raise AuthenticationRequiredError()

    verifier = get_jwt_verifier()

    try:
        claims: AuthClaims = await verifier.verify(credentials.credentials)
    except JWTExpiredError:
        return TokenValidationResponse(valid=False)
    except JWTVerificationError:
        return TokenValidationResponse(valid=False)

    if claims.token_id:
        revoked = await _check_token_revocation(
            claims.token_id, claims.token_type, cache_svc, db,
        )
        if revoked:
            return TokenValidationResponse(valid=False)

    username = None
    permissions: list[str] = []
    if claims.user_id:
        user = await user_svc.get_user_by_id(claims.user_id)
        if user:
            username = user.username
            permissions = await user_svc.get_user_permission_names(claims.user_id)

    return TokenValidationResponse(
        valid=True,
        user_id=claims.user_id,
        username=username,
        tenant_id=claims.tenant_id,
        permission_ids=claims.permission_ids,
        permissions=permissions,
        roles=claims.roles,
        token_type=claims.token_type,
    )


@router.get("/.well-known/jwks.json")
async def jwks():
    return key_manager.get_jwks()
