"""
Middleware package for OCR Service.

Provides rate limiting, authentication, error handling, and request logging middleware.
"""

from .auth_provider import AuthProvider, OptionalAuthProvider
from .rate_limit_middleware import RateLimitMiddleware
from .error_handler_middleware import add_error_handlers
from .request_logging import RequestLoggingMiddleware

__all__ = [
    "AuthProvider",
    "OptionalAuthProvider",
    "RateLimitMiddleware",
    "add_error_handlers",
    "RequestLoggingMiddleware",
]


