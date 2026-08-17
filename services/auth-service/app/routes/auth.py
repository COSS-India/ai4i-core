"""
Authentication routes: register, login, logout, refresh, password management,
and email activation (provision + set-password).
"""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from pydantic import EmailStr

from app.core.config import settings
from app.dependencies.auth import (
    get_current_user,
    get_current_user_id,
    get_optional_current_user,
)
from app.dependencies.services import get_auth_service, get_cache_service
from app.models.user import User
from app.schemas.auth import (
    ChangePasswordResponse,
    CheckEmailData,
    CheckEmailResponse,
    ForgotPasswordRequest,
    ForgotPasswordResponse,
    GetSetupTokenStatusResponse,
    GuestLoginResponse,
    LoginRequest,
    LoginResponse,
    LogoutResponse,
    MessageData,
    PasswordChangeRequest,
    RefreshTokenResponse,
    RegisterData,
    RegisterRequest,
    RegisterResponse,
    ResendSetupLinkRequest,
    ResendSetupLinkResponse,
    ResendVerificationRequest,
    ResendVerificationResponse,
    ResetPasswordData,
    ResetPasswordRequest,
    ResetPasswordResponse,
    SetPasswordRequest,
    SetPasswordResponse,
    TokenRefreshRequest,
    VerifyEmailRequest,
    VerifyEmailResponse,
)
from app.schemas.common import error_responses
from app.services.auth_service import AuthService
from app.services.cache_service import CacheService
from app.utils.masking import mask_email

router = APIRouter(
    prefix="/auth",
    tags=["Authentication"],
    responses=error_responses(422),
)


@router.get(
    "/check-email",
    response_model=CheckEmailResponse
)
async def check_email(
    email: EmailStr = Query(...),
    svc: AuthService = Depends(get_auth_service),
):
    """Return whether the given email already belongs to a user.

    Used by the registration form to show an in-use hint before submit.
    """
    exists = await svc.check_email_exists(email)
    return CheckEmailResponse(data=CheckEmailData(exists=exists))


@router.post(
    "/register",
    status_code=status.HTTP_201_CREATED,
    response_model=RegisterResponse
)
async def register(
    body: RegisterRequest,
    background_tasks: BackgroundTasks,
    svc: AuthService = Depends(get_auth_service),
):
    """Create a user and send a verification email.

    The account cannot sign in until the verification link is consumed.
    Returned `email` is masked.
    """
    user = await svc.register(
        email=body.email,
        password=body.password,
        confirm_password=body.confirm_password,
        full_name=body.full_name,
        phone_number=body.phone_number,
        tz=body.timezone,
        tenant_id=body.tenant_id,
        background_tasks=background_tasks,
    )
    return RegisterResponse(
        data=RegisterData(
            user_id=str(user.id),
            email=mask_email(user.email),
            username=user.username,
            message=(
                "Account created. Check your inbox for a verification link to "
                "activate your account before signing in."
            ),
        )
    )


@router.post(
    "/verify-email",
    response_model=VerifyEmailResponse
)
async def verify_email(
    body: VerifyEmailRequest,
    background_tasks: BackgroundTasks,
    svc: AuthService = Depends(get_auth_service),
):
    """Consume a verification token from the link in the verify-email email
    and activate the user. Sends a welcome email after activation.
    """
    await svc.verify_email_token(body.token, background_tasks=background_tasks)
    return VerifyEmailResponse(
        data=MessageData(message="Email verified. You can now sign in.")
    )


@router.post(
    "/resend-verification",
    response_model=ResendVerificationResponse
)
async def resend_verification(
    body: ResendVerificationRequest,
    background_tasks: BackgroundTasks,
    svc: AuthService = Depends(get_auth_service),
):
    """Re-issue a verify-email link for a user who registered but hasn't
    verified yet. Old verify tokens for this user are deactivated first.

    Anti-enumeration: returns the same generic 200 message regardless of
    whether the email matches a real account (consistent with
    /auth/forgot-password and /auth/resend-setup-link).
    """
    await svc.resend_verification(email=body.email, background_tasks=background_tasks)
    return ResendVerificationResponse(
        data=MessageData(message="If this email is registered, you will receive an email.")
    )


@router.post(
    "/forgot-password",
    response_model=ForgotPasswordResponse,
)
async def forgot_password(
    body: ForgotPasswordRequest,
    background_tasks: BackgroundTasks,
    svc: AuthService = Depends(get_auth_service),
):
    """Request a password-reset link.

    Anti-enumeration: returns the same generic 200 message regardless of
    whether the email matches a real, active account. Rate-limiting is handled
    at the gateway (APISIX) level.
    """
    await svc.request_password_reset(email=body.email, background_tasks=background_tasks)
    return ForgotPasswordResponse(
        data=MessageData(
            message="If this email is registered, you'll receive a reset link shortly."
        )
    )


@router.post(
    "/reset-password",
    response_model=ResetPasswordResponse
)
async def reset_password(
    body: ResetPasswordRequest,
    background_tasks: BackgroundTasks,
    svc: AuthService = Depends(get_auth_service),
):
    """Consume a reset token and set the user's new password.

    Single-use, 30-min expiry per spec. Revokes all refresh tokens so other
    active sessions are signed out. Sends a password-changed notification.
    """
    await svc.reset_password_with_token(
        token=body.token,
        new_password=body.new_password,
        confirm_password=body.confirm_password,
        background_tasks=background_tasks,
    )
    return ResetPasswordResponse(
        data=ResetPasswordData(
            message="Password has been reset. Sign in with your new password.",
            sign_out_other_sessions=True,
        )
    )


@router.post(
    "/login",
    response_model=LoginResponse,
    responses=error_responses(401),
)
async def login(
    body: LoginRequest,
    svc: AuthService = Depends(get_auth_service),
):
    """Authenticate with email and password and return an access/refresh pair."""
    return await svc.login(email=body.email, password=body.password)


@router.post(
    "/guest/login",
    response_model=GuestLoginResponse,
    responses=error_responses(401, 503),
)
async def guest_login(
    svc: AuthService = Depends(get_auth_service),
):
    """Authenticate as the platform guest account when guest credentials are
    configured. Returns 503 if guest login is not enabled.
    """
    email = (settings.guest_email or "").strip()
    password = settings.guest_password.get_secret_value() if settings.guest_password else None
    if not email or not password:
        raise HTTPException(
            status_code=503,
            detail={"code": "SERVICE_UNAVAILABLE", "message": "Guest login is not configured."},
        )
    return await svc.login(email=email, password=password)


@router.post(
    "/refresh",
    response_model=RefreshTokenResponse,
    responses=error_responses(401)
)
async def refresh_token(
    body: TokenRefreshRequest,
    svc: AuthService = Depends(get_auth_service),
):
    """Exchange a valid refresh token for a new access token."""
    return await svc.refresh_token(body.refresh_token)


@router.post(
    "/logout",
    response_model=LogoutResponse,
    responses=error_responses(401)
)
async def logout(
    user_id: UUID = Depends(get_current_user_id),
    svc: AuthService = Depends(get_auth_service),
    cache_svc: CacheService = Depends(get_cache_service),
):
    """Revoke the user's refresh token and mark all access tokens as logged out.

    Global logout: any access token issued before now is rejected by
    /auth/validate's revocation check, regardless of its 60-min TTL.
    """
    await svc.logout(user_id=user_id)
    await cache_svc.revoke_all_sessions(str(user_id))
    return LogoutResponse(message="Logged out successfully.", logged_out=True)


@router.post(
    "/change-password",
    response_model=ChangePasswordResponse,
    responses=error_responses(401),
)
async def change_password(
    body: PasswordChangeRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    svc: AuthService = Depends(get_auth_service),
):
    """Change the authenticated user's password and return a fresh token pair.

    Other sessions are signed out. The caller receives new tokens so they can
    stay logged in without guessing which stored refresh token was theirs.
    """
    return await svc.change_password(
        user=current_user,
        current_password=body.current_password,
        new_password=body.new_password,
        confirm_password=body.confirm_password,
        background_tasks=background_tasks,
    )


# ── Email activation ──

@router.get(
    "/set-password/status",
    response_model=GetSetupTokenStatusResponse
)
async def get_setup_token_status(
    token: str = Query(...),
    svc: AuthService = Depends(get_auth_service),
):
    """Check whether a setup token is valid, expired, or already used."""
    result = await svc.get_setup_token_status(token)
    return GetSetupTokenStatusResponse(**result)


@router.post(
    "/set-password",
    response_model=SetPasswordResponse
)
async def set_password(
    body: SetPasswordRequest,
    background_tasks: BackgroundTasks,
    svc: AuthService = Depends(get_auth_service),
):
    """Consume a setup token and set the user's password, activating the account.
    Sends a welcome email after activation.
    """
    await svc.set_password_with_token(
        token=body.token,
        new_password=body.new_password,
        confirm_password=body.confirm_password,
        background_tasks=background_tasks,
    )
    return SetPasswordResponse(
        data=MessageData(message="Password set. You can now log in.")
    )


@router.post(
    "/resend-setup-link",
    response_model=ResendSetupLinkResponse
)
async def resend_setup_link(
    body: ResendSetupLinkRequest,
    background_tasks: BackgroundTasks,
    svc: AuthService = Depends(get_auth_service),
    current_user: Optional[User] = Depends(get_optional_current_user),
):
    """Invalidate existing setup tokens and issue a new one for the given email."""
    await svc.resend_setup_link(
        email=body.email,
        background_tasks=background_tasks,
        tenant_id=body.tenant_id,
        caller=current_user,
    )
    return ResendSetupLinkResponse(
        data=MessageData(message="New setup link issued.")
    )
