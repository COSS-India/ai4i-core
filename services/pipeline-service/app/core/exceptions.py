"""Re-export shared exceptions for convenient imports."""

from ai4icore_exceptions import (
    AppError,
    AuthenticationError,
    AuthorizationError,
    RateLimitExceededError,
    ValidationError,
    register_exception_handlers,
)

__all__ = [
    "AppError",
    "AuthenticationError",
    "AuthorizationError",
    "RateLimitExceededError",
    "ValidationError",
    "register_exception_handlers",
]
