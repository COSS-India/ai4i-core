"""
ai4icore_exceptions — Shared exception hierarchy, response envelope, and handlers.

The canonical home for all platform exceptions. Every service uses these.

Usage:
    from ai4icore_exceptions import (
        AuthenticationRequiredError,
        InsufficientPermissionsError,
        register_exception_handlers,
        success_response,
        error_response,
    )
"""

from .exceptions import (
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
    # Service Errors
    ServiceError,
    TritonInferenceError,
    ModelNotFoundError,
    ServiceUnavailableError,
    AudioProcessingError,
    TextProcessingError,
    UnpublishedServiceError,
    # Pipeline Errors
    PipelineError,
    PipelineTaskError,
    # Response Models
    ErrorDetail,
    ErrorResponse,
)

from .handlers import register_exception_handlers
from .responses import success_response, error_response

__all__ = [
    # Base
    "AppError",
    # Authentication
    "AuthenticationError",
    "AuthenticationRequiredError",
    "InvalidCredentialsError",
    "TokenExpiredError",
    "TokenInvalidError",
    "TokenRevokedError",
    "InvalidTokenError",
    "InvalidAPIKeyError",
    "ExpiredAPIKeyError",
    "APIKeyRevokedError",
    # Authorization
    "AuthorizationError",
    "InsufficientPermissionsError",
    "UserInactiveError",
    # Resource
    "EntityNotFoundError",
    "UserNotFoundError",
    "DuplicateEntityError",
    # Validation
    "ValidationError",
    "PasswordValidationError",
    "PasswordMismatchError",
    # Tenant
    "TenantResolutionError",
    # Rate Limiting
    "RateLimitExceededError",
    # Service
    "ServiceError",
    "TritonInferenceError",
    "ModelNotFoundError",
    "ServiceUnavailableError",
    "AudioProcessingError",
    "TextProcessingError",
    "UnpublishedServiceError",
    # Pipeline
    "PipelineError",
    "PipelineTaskError",
    # Response Models
    "ErrorDetail",
    "ErrorResponse",
    # Handlers
    "register_exception_handlers",
    # Response envelope
    "success_response",
    "error_response",
]
