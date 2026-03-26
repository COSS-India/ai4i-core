"""
Auth-service exceptions — re-exports from shared ai4icore_exceptions.

NO local exception classes. Everything comes from the shared library.
"""

# ── All exceptions from the canonical shared library ──
from ai4icore_exceptions import (  # noqa: F401
    # Base
    AppError,
    # Authentication (401)
    AuthenticationError,
    AuthenticationRequiredError,
    InvalidCredentialsError,
    TokenExpiredError,
    TokenInvalidError,
    TokenRevokedError,
    InvalidTokenError,
    InvalidAPIKeyError,
    ExpiredAPIKeyError,
    APIKeyRevokedError,
    # Authorization (403)
    AuthorizationError,
    InsufficientPermissionsError,
    UserInactiveError,
    # Resource (404, 409)
    EntityNotFoundError,
    UserNotFoundError,
    DuplicateEntityError,
    # Validation (422)
    ValidationError,
    PasswordValidationError,
    PasswordMismatchError,
    # Tenant
    TenantResolutionError,
    # Rate Limiting
    RateLimitExceededError,
    # Handlers
    register_exception_handlers,
    # Response envelope
    success_response,
    error_response,
)
