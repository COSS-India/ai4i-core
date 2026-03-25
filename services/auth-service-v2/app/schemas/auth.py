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
    language: str = Field(default="en", max_length=10)
    is_tenant: Optional[bool] = Field(
        None,
        description="True for tenant admin users, False for tenant users, None for non-tenant.",
    )


class LoginRequest(BaseSchema):
    email: EmailStr
    password: str
    remember_me: bool = False


class TokenRefreshRequest(BaseSchema):
    refresh_token: str


class PasswordChangeRequest(BaseSchema):
    current_password: str
    new_password: str = Field(..., min_length=8, max_length=100)
    confirm_password: str = Field(..., min_length=8, max_length=100)


class PasswordResetRequest(BaseSchema):
    email: EmailStr


class PasswordResetConfirm(BaseSchema):
    token: str
    new_password: str = Field(..., min_length=8, max_length=100)
    confirm_password: str = Field(..., min_length=8, max_length=100)


class LogoutRequest(BaseSchema):
    refresh_token: Optional[str] = None


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
