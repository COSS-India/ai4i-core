"""
Middleware package for OCR Service.

Provides rate limiting, error handling, and request logging middleware.
Authentication is now handled by ai4icore_auth shared library.
"""

from .rate_limit_middleware import RateLimitMiddleware
from .error_handler_middleware import add_error_handlers
from .request_logging import RequestLoggingMiddleware
from ai4icore_auth import AuthProvider, OptionalAuthProvider

__all__ = [
    "AuthProvider",
    "OptionalAuthProvider",
    "RateLimitMiddleware",
    "add_error_handlers",
    "RequestLoggingMiddleware",
]


