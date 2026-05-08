"""
Authentication request/response schemas.
"""

from typing import Optional

from pydantic import EmailStr, Field

from app.core.constants import (
    FULL_NAME_MAX_LENGTH,
    PASSWORD_MAX_LENGTH,
    PASSWORD_MIN_LENGTH,
    PHONE_NUMBER_MAX_LENGTH,
    TIMEZONE_MAX_LENGTH,
    USERNAME_MAX_LENGTH,
)
from app.schemas.base import BaseSchema

_PASSWORD_FIELD = Field(..., min_length=PASSWORD_MIN_LENGTH, max_length=PASSWORD_MAX_LENGTH)


# ── Requests ──

class RegisterRequest(BaseSchema):
    email: EmailStr
    username: str = Field(..., min_length=3, max_length=USERNAME_MAX_LENGTH)
    password: str = _PASSWORD_FIELD
    confirm_password: str = _PASSWORD_FIELD
    full_name: Optional[str] = Field(None, max_length=FULL_NAME_MAX_LENGTH)
    phone_number: Optional[str] = Field(None, max_length=PHONE_NUMBER_MAX_LENGTH)
    timezone: str = Field(default="UTC", max_length=TIMEZONE_MAX_LENGTH)
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
    new_password: str = _PASSWORD_FIELD
    confirm_password: str = _PASSWORD_FIELD


class SetPasswordRequest(BaseSchema):
    token: str
    new_password: str = _PASSWORD_FIELD
    confirm_password: str = _PASSWORD_FIELD


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
    new_password: str = _PASSWORD_FIELD
    confirm_password: str = _PASSWORD_FIELD


class SetPasswordStatusRequest(BaseSchema):
    token: str = Field(..., min_length=10, max_length=2048)


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


class SetPasswordStatusResponse(BaseSchema):
    valid: bool
    status: str
    message: str
