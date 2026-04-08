"""
Token validation endpoint — called by APISIX for every request.
Uses the shared ai4icore_auth JWTVerifier.
"""

import logging

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import JSONResponse
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
from app.services.tenant_service import TenantService
from app.services.user_service import UserService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Validation"])

security = HTTPBearer(auto_error=False)


def _is_suspended_or_deactivated(status_val: str | None) -> bool:
    if not status_val:
        return False
    status = str(status_val).strip().upper()
    if "." in status:
        status = status.split(".")[-1]
    return status in {"SUSPENDED", "DEACTIVATED"}


def _tenant_inactive_message(tenant_status: str) -> str:
    return f"tenant is {tenant_status.lower()} , please contact your platform admin"


def _user_inactive_message(user_status: str) -> str:
    return f"User is {user_status.lower()} , please contact your admin"


@router.get("/validate")
@router.post("/validate")
async def validate_token(
    request: Request,
    response: Response,
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
            return JSONResponse(status_code=401, content={"valid": False, "error": "USER_NOT_FOUND"})

        if not user.is_active:
            return JSONResponse(status_code=401, content={"valid": False, "error": "USER_INACTIVE"})

        username = user.username

        tenant_service = None
        mt_factory = getattr(request.app.state, "multi_tenant_session_factory", None)
        if mt_factory:
            tenant_service = TenantService(mt_factory)

        # Enforce tenant lifecycle status on every token validation.
        # This ensures suspended/deactivated tenant admins/users are cut off on next request.
        if tenant_service:
            tenant_id = user.tenant_id_cached or claims.tenant_id
            is_tenant_user = bool(user.is_tenant)

            if not tenant_id:
                tenant_id = await tenant_service.resolve_and_cache_tenant_id(claims.user_id, is_tenant_user)

            if tenant_id:
                tenant_status = await tenant_service.get_tenant_status(tenant_id)
                if tenant_status is None:
                    tenant_status = await tenant_service.get_tenant_status_by_user_id(claims.user_id, is_tenant_user)
                if _is_suspended_or_deactivated(tenant_status):
                    return JSONResponse(
                        status_code=401,
                        content={
                            "valid": False,
                            "error": "TENANT_INACTIVE",
                            "message": _tenant_inactive_message(str(tenant_status)),
                        },
                    )

                # tenant admin only checks tenant status; tenant user checks both tenant and tenant-user status
                if not is_tenant_user:
                    tenant_user_status = await tenant_service.get_tenant_user_status(tenant_id, claims.user_id)
                    if _is_suspended_or_deactivated(tenant_user_status):
                        return JSONResponse(
                            status_code=401,
                            content={
                                "valid": False,
                                "error": "TENANT_USER_INACTIVE",
                                "message": _user_inactive_message(str(tenant_user_status)),
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
