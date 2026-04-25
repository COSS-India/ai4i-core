"""
Authentication routes: register, login, logout, refresh, password management,
and email activation (provision + set-password).
"""

from fastapi import APIRouter, Depends, Request

from app.core.config import settings
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
    ProvisionUserRequest,
    ProvisionUserResponse,
    RegisterRequest,
    ResendSetupLinkRequest,
    SetPasswordRequest,
    SetPasswordStatusResponse,
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
        tenant_id=body.tenant_id,
    )
    return success_response(data={
        "user_id": str(user.user_id),
        "email": user.email,
        "username": user.username,
        "message": "User registered successfully.",
    })


@router.post("/login", response_model=LoginResponse)
async def login(
    body: LoginRequest,
    svc: AuthService = Depends(get_auth_service),
):
    return await svc.login(email=body.email, password=body.password)


@router.post("/guest/login", response_model=LoginResponse)
async def guest_login(
    svc: AuthService = Depends(get_auth_service),
):
    from fastapi import HTTPException
    email = (settings.guest_email or "").strip()
    password = settings.guest_password
    if not email or not password:
        raise HTTPException(status_code=503, detail="Guest login is not configured.")
    return await svc.login(email=email, password=password)


@router.post("/refresh", response_model=TokenRefreshResponse)
async def refresh_token(
    body: TokenRefreshRequest,
    svc: AuthService = Depends(get_auth_service),
):
    return await svc.refresh_token(body.refresh_token)


@router.post("/logout")
async def logout(
    current_user: User = Depends(get_current_active_user),
    svc: AuthService = Depends(get_auth_service),
):
    await svc.logout(user_id=current_user.user_id)
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


# ── Email activation ──

@router.post("/internal/provision-user", response_model=ProvisionUserResponse)
async def provision_user(
    body: ProvisionUserRequest,
    svc: AuthService = Depends(get_auth_service),
):
    """
    Internal: provision an inactive user and return a one-time setup token.
    Called by the multi-tenant service during tenant user onboarding.
    """
    user_id, setup_token = await svc.provision_user(
        email=body.email,
        username=body.username,
        full_name=body.full_name,
        phone_number=body.phone_number,
        tenant_id=body.tenant_id,
        creation_type=body.creation_type,
    )
    return ProvisionUserResponse(
        user_id=user_id,
        setup_token=setup_token,
        message="User provisioned. Setup link can now be sent to the user.",
    )


@router.get("/set-password/status", response_model=SetPasswordStatusResponse)
async def get_setup_token_status(
    token: str,
    svc: AuthService = Depends(get_auth_service),
):
    """Check whether a setup token is valid, expired, or already used."""
    result = await svc.get_setup_token_status(token)
    return SetPasswordStatusResponse(**result)


@router.post("/set-password")
async def set_password(
    body: SetPasswordRequest,
    svc: AuthService = Depends(get_auth_service),
):
    """Consume a setup token and set the user's password, activating the account."""
    await svc.set_password_with_token(
        token=body.token,
        new_password=body.new_password,
        confirm_password=body.confirm_password,
    )
    return success_response(data={"message": "Password set. You can now log in."})


@router.post("/resend-setup-link")
async def resend_setup_link(
    body: ResendSetupLinkRequest,
    svc: AuthService = Depends(get_auth_service),
):
    """Invalidate existing setup tokens and issue a new one for the given email."""
    setup_token = await svc.resend_setup_link(email=body.email)
    return success_response(data={
        "message": "New setup link issued.",
        "setup_token": setup_token,
    })
