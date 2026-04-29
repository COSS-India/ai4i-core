"""
Authentication request/response schemas.
"""

from typing import Optional

from pydantic import EmailStr, Field

from app.schemas.base import BaseSchema


# ── Requests ──

class RegisterRequest(BaseSchema):
    email: EmailStr
    username: str = Field(..., min_length=3, max_length=100)
    password: str = Field(..., min_length=8, max_length=100)
    confirm_password: str = Field(..., min_length=8, max_length=100)
    full_name: Optional[str] = Field(None, max_length=255)
    phone_number: Optional[str] = Field(None, max_length=20)
    timezone: str = Field(default="UTC", max_length=50)
    tenant_id: Optional[int] = Field(
        None,
        description="Tenant integer ID to associate with the user.",
    )


class LoginRequest(BaseSchema):
    email: EmailStr
    password: str


class TokenRefreshRequest(BaseSchema):
    refresh_token: str


class PasswordChangeRequest(BaseSchema):
    current_password: str
    new_password: str = Field(..., min_length=8, max_length=100)
    confirm_password: str = Field(..., min_length=8, max_length=100)


class LogoutRequest(BaseSchema):
    refresh_token: Optional[str] = None


class ProvisionUserRequest(BaseSchema):
    email: EmailStr
    username: str = Field(..., min_length=3, max_length=100)
    full_name: Optional[str] = Field(None, max_length=255)
    phone_number: Optional[str] = Field(None, max_length=20)
    tenant_id: Optional[int] = Field(None, description="Tenant integer ID.")
    creation_type: str = Field(
        default="default",
        description="Legacy values 'tenant'/'direct' normalize to 'default'; only 'default' and 'google' persist.",
    )


class SetPasswordRequest(BaseSchema):
    token: str
    new_password: str = Field(..., min_length=8, max_length=100)
    confirm_password: str = Field(..., min_length=8, max_length=100)


class ResendSetupLinkRequest(BaseSchema):
    email: EmailStr


class VerifyEmailRequest(BaseSchema):
    token: str


class ResendVerificationRequest(BaseSchema):
    email: EmailStr


class ForgotPasswordRequest(BaseSchema):
    email: EmailStr


class ResetPasswordRequest(BaseSchema):
    token: str
    new_password: str = Field(..., min_length=8, max_length=100)
    confirm_password: str = Field(..., min_length=8, max_length=100)


# ── Responses ──

class LoginResponse(BaseSchema):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class TokenRefreshResponse(BaseSchema):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class LogoutResponse(BaseSchema):
    message: str
    logged_out: bool


class ProvisionUserResponse(BaseSchema):
    user_id: str
    setup_token: str
    message: str


class SetPasswordStatusResponse(BaseSchema):
    valid: bool
    status: str
    message: str
