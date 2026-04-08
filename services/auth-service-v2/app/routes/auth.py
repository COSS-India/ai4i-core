"""
Authentication routes: register, login, logout, refresh, password management.
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from app.core.responses import success_response
from app.core.database import get_db
from app.dependencies.auth import get_current_active_user
from app.dependencies.permissions import require_any_role
from app.dependencies.services import get_auth_service, get_cache_service
from app.models.user import User
from app.repositories.session_repository import SessionRepository
from app.schemas.auth import (
    LoginRequest,
    LoginResponse,
    LogoutRequest,
    LogoutResponse,
    PasswordChangeRequest,
    RegisterRequest,
    TokenRefreshRequest,
    TokenRefreshResponse,
)
from app.services.auth_service import AuthService
from app.services.cache_service import CacheService
from app.services.session_service import SessionService

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/register")
async def register(
    body: RegisterRequest,
    svc: AuthService = Depends(get_auth_service),
):
    user = await svc.register(
        email=body.email,
        username=body.username,
        password=body.password,
        confirm_password=body.confirm_password,
        full_name=body.full_name,
        phone_number=body.phone_number,
        tz=body.timezone,
        language=body.language,
        tenant_id=body.tenant_id,
        is_tenant=body.is_tenant,
    )
    return success_response(data={
        "id": user.id,
        "email": user.email,
        "username": user.username,
        "message": "User registered successfully.",
    })


@router.post("/login", response_model=LoginResponse)
async def login(
    request: Request,
    body: LoginRequest,
    svc: AuthService = Depends(get_auth_service),
):
    ip_address = request.headers.get("X-Forwarded-For", request.client.host if request.client else None)
    user_agent = request.headers.get("User-Agent")

    return await svc.login(
        email=body.email,
        password=body.password,
        ip_address=ip_address,
        user_agent=user_agent,
    )


@router.post("/refresh", response_model=TokenRefreshResponse)
async def refresh_token(
    body: TokenRefreshRequest,
    svc: AuthService = Depends(get_auth_service),
):
    return await svc.refresh_token(body.refresh_token)


@router.post("/logout")
async def logout(
    body: LogoutRequest,
    current_user: User = Depends(get_current_active_user),
    svc: AuthService = Depends(get_auth_service),
):
    await svc.logout(user_id=current_user.id, refresh_token_str=body.refresh_token)
    return LogoutResponse(message="Logged out successfully.", logged_out=True)


@router.post("/change-password")
async def change_password(
    body: PasswordChangeRequest,
    current_user: User = Depends(get_current_active_user),
    svc: AuthService = Depends(get_auth_service),
):
    await svc.change_password(
        user=current_user,
        current_password=body.current_password,
        new_password=body.new_password,
        confirm_password=body.confirm_password,
    )
    return success_response(data={"message": "Password changed successfully."})


@router.post("/sessions/revoke-by-tenant/{tenant_id}")
async def revoke_sessions_by_tenant(
    request: Request,
    tenant_id: str,
    _: User = Depends(require_any_role("ADMIN")),
    db: AsyncSession = Depends(get_db),
    cache: CacheService = Depends(get_cache_service),
):
    """
    Admin-only endpoint to invalidate all active sessions for users in a tenant.
    Used by multi-tenant service when tenant is suspended/deactivated.
    """
    mt_factory = getattr(request.app.state, "multi_tenant_session_factory", None)
    if not mt_factory:
        raise HTTPException(status_code=503, detail="Multi-tenant DB not configured in auth service")

    tenant_service = TenantService(mt_factory)
    user_ids = await tenant_service.get_tenant_user_ids(tenant_id) or []
    if not user_ids:
        return success_response(data={
            "tenant_id": tenant_id,
            "users_matched": 0,
            "sessions_revoked": 0,
        })

    session_service = SessionService(SessionRepository(db), cache)
    sessions_revoked = 0
    for user_id in user_ids:
        sessions_revoked += await session_service.invalidate_all_for_user(user_id)
    await session_service.commit()

    return success_response(data={
        "tenant_id": tenant_id,
        "users_matched": len(user_ids),
        "sessions_revoked": sessions_revoked,
    })


class RevokeSessionsByUsersRequest(BaseModel):
    user_ids: list[int]


@router.post("/sessions/revoke-by-users")
async def revoke_sessions_by_users(
    body: RevokeSessionsByUsersRequest,
    _: User = Depends(require_any_role("ADMIN")),
    db: AsyncSession = Depends(get_db),
    cache: CacheService = Depends(get_cache_service),
):
    """
    Admin-only endpoint to invalidate all active sessions for a set of users.
    Useful for external orchestrators that already know impacted user IDs.
    """
    user_ids = sorted({int(uid) for uid in body.user_ids if uid is not None})
    if not user_ids:
        return success_response(data={"users_matched": 0, "sessions_revoked": 0})

    session_service = SessionService(SessionRepository(db), cache)
    sessions_revoked = 0
    for user_id in user_ids:
        sessions_revoked += await session_service.invalidate_all_for_user(user_id)
    await session_service.commit()

    return success_response(data={
        "users_matched": len(user_ids),
        "sessions_revoked": sessions_revoked,
    })
