"""
Authentication request/response schemas.
"""

import re
from typing import Annotated, Any, Optional

from pydantic import EmailStr, Field, field_validator
from pydantic.functional_validators import AfterValidator
from pydantic import StringConstraints

# email_validator (used by EmailStr) hardcodes a reject-list of special-use
# domains (RFC 2606: .invalid, .test, .localhost, etc.) regardless of the
# check_deliverability flag. For anti-enumeration endpoints we need a looser
# check: any string that looks like an email must reach business logic and
# return 200 silently. We enforce RFC 5321 structural bounds (local part ≤ 64
# chars, domain ≤ 253 chars, TLD ≥ 2 chars) to block obvious non-emails, but
# intentionally skip deliverability checks so legitimate users still get
# helpful format errors.
_BASIC_EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,253}\.[^@\s]{2,63}$")

def _loose_email_validator(v: str) -> str:
    if not isinstance(v, str):
        raise ValueError("value is not a valid email address")
    v = v.strip().lower()
    if not _BASIC_EMAIL_RE.match(v):
        raise ValueError("value is not a valid email address")
    return v

_AnyEmail = Annotated[str, StringConstraints(max_length=254), AfterValidator(_loose_email_validator)]

from app.core.constants import (
    FULL_NAME_MAX_LENGTH,
    PASSWORD_MAX_LENGTH,
    PASSWORD_MIN_LENGTH,
    PHONE_NUMBER_MAX_LENGTH,
    TIMEZONE_MAX_LENGTH,
)
from app.schemas.base import BaseSchema
from app.schemas.common import MessageData, SuccessResponse
from app.schemas.text_validators import check_name_chars, clean_text

_PASSWORD_FIELD = Field(..., min_length=PASSWORD_MIN_LENGTH, max_length=PASSWORD_MAX_LENGTH)


# ── Requests ──

class RegisterRequest(BaseSchema):
    email: EmailStr
    password: str = _PASSWORD_FIELD
    confirm_password: str = _PASSWORD_FIELD
    # Same rules TenantUserUpdate/UserUpdate apply to this column: cleaned of
    # invisible characters and restricted to name-like text (tenant.py, user.py).
    full_name: Optional[str] = Field(None, min_length=2, max_length=FULL_NAME_MAX_LENGTH)
    phone_number: Optional[str] = Field(None, max_length=PHONE_NUMBER_MAX_LENGTH)
    timezone: str = Field(default="UTC", max_length=TIMEZONE_MAX_LENGTH)
    tenant_id: Optional[int] = Field(
        None,
        description="Tenant integer ID to associate with the user.",
    )

    @field_validator("full_name", mode="before")
    @classmethod
    def _clean_full_name(cls, v: Any) -> Any:
        return clean_text(v)

    @field_validator("full_name", mode="after")
    @classmethod
    def _validate_full_name(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            return check_name_chars(v)
        return v


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
    email: _AnyEmail
    tenant_id: Optional[int] = Field(
        default=None,
        ge=1,
        description=(
            "Pending tenant ID. Required with masked contact emails from Tenant "
            "Management; resolves the contact admin directly without auth."
        ),
    )


class VerifyEmailRequest(BaseSchema):
    token: str


class ResendVerificationRequest(BaseSchema):
    email: _AnyEmail


class ForgotPasswordRequest(BaseSchema):
    email: _AnyEmail


class ResetPasswordRequest(BaseSchema):
    token: str
    new_password: str = _PASSWORD_FIELD
    confirm_password: str = _PASSWORD_FIELD


class SetPasswordStatusRequest(BaseSchema):
    token: str = Field(..., min_length=10, max_length=2048)


# ── Unwrapped responses (these routes never used {success, data}) ──

class LoginResponse(BaseSchema):
    """POST /auth/login"""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class GuestLoginResponse(LoginResponse):
    """POST /auth/guest/login"""


class RefreshTokenResponse(BaseSchema):
    """POST /auth/refresh"""

    access_token: str
    token_type: str = "bearer"
    expires_in: int


class ChangePasswordResponse(BaseSchema):
    """POST /auth/change-password

    Keeps the pre-existing `message` field so old consumers of this
    endpoint are unaffected, and adds a fresh token pair alongside it so the
    caller's own client can stay logged in without depending on a guessed
    refresh token (see change_password in auth_service.py).
    """

    message: str = "Password changed successfully."
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class LogoutResponse(BaseSchema):
    """POST /auth/logout"""

    message: str
    logged_out: bool


class GetSetupTokenStatusResponse(BaseSchema):
    """GET /auth/set-password/status"""

    valid: bool
    status: str
    message: str


# ── Enveloped responses (these routes already returned {success, data}) ──

class CheckEmailData(BaseSchema):
    exists: bool


class RegisterData(BaseSchema):
    user_id: str
    email: str
    username: str
    message: str


class ResetPasswordData(BaseSchema):
    message: str
    sign_out_other_sessions: bool = True


class CheckEmailResponse(SuccessResponse):
    """GET /auth/check-email"""

    data: CheckEmailData


class RegisterResponse(SuccessResponse):
    """POST /auth/register"""

    data: RegisterData


class VerifyEmailResponse(SuccessResponse):
    """POST /auth/verify-email"""

    data: MessageData


class ResendVerificationResponse(SuccessResponse):
    """POST /auth/resend-verification"""

    data: MessageData


class ForgotPasswordResponse(SuccessResponse):
    """POST /auth/forgot-password"""

    data: MessageData


class ResetPasswordResponse(SuccessResponse):
    """POST /auth/reset-password"""

    data: ResetPasswordData


class SetPasswordResponse(SuccessResponse):
    """POST /auth/set-password"""

    data: MessageData


class ResendSetupLinkResponse(SuccessResponse):
    """POST /auth/resend-setup-link"""

    data: MessageData
