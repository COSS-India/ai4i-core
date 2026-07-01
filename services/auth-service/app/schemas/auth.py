"""
Authentication request/response schemas.
"""

import re
from typing import Annotated, Optional

from pydantic import EmailStr, Field
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

_PASSWORD_FIELD = Field(..., min_length=PASSWORD_MIN_LENGTH, max_length=PASSWORD_MAX_LENGTH)


# ── Requests ──

class RegisterRequest(BaseSchema):
    email: EmailStr
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
    current_refresh_token: str | None = None


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
