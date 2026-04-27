"""
Core-service exceptions — re-exports from shared ai4icore_exceptions.

NO local exception classes. All services share the same exception hierarchy.
"""

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
    DuplicateEntityError,
    # Validation (422)
    ValidationError,
    # Service Errors
    ServiceError,
    ModelNotFoundError,
    ServiceUnavailableError,
    UnpublishedServiceError,
    # Rate Limiting
    RateLimitExceededError,
    # Handlers
    register_exception_handlers,
)
