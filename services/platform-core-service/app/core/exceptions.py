"""
Core-service exceptions — re-exports from shared ai4icore_exceptions.

NO local exception classes. All services share the same exception hierarchy.
"""

from ai4icore_core.exceptions import (  # noqa: F401
    # Base
    AppError,
    # Resource (404, 409)
    EntityNotFoundError,
    DuplicateEntityError,
    # Validation (422)
    ValidationError,
    # AuthZ (403) — used by the alert auth dependencies
    InsufficientPermissionsError,
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
