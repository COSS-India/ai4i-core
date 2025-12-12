"""
Middleware package for OCR Service.

Provides rate limiting, error handling, and request logging middleware.
Authentication can be added later following the same pattern as NMT/TTS.
"""

from .rate_limit_middleware import RateLimitMiddleware
from .error_handler_middleware import add_error_handlers
from .request_logging import RequestLoggingMiddleware
from .auth_provider import AuthProvider, OptionalAuthProvider

__all__ = [
    "RateLimitMiddleware",
    "add_error_handlers",
    "RequestLoggingMiddleware",
    "AuthProvider",
    "OptionalAuthProvider",
]


