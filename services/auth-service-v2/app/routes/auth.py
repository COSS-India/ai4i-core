"""
Authentication routes: register, login, logout, refresh, password management.
"""

from fastapi import APIRouter, Depends, Request

from app.core.responses import success_response
from app.dependencies.auth import get_current_active_user
from app.dependencies.services import get_auth_service
from app.models.user import User
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
