"""
Middleware package for OCR Service.

Provides authentication, error handling, and request logging middleware.
"""

from .auth_provider import AuthProvider, OptionalAuthProvider
from .error_handler_middleware import add_error_handlers
from .request_logging import RequestLoggingMiddleware

__all__ = [
    "AuthProvider",
    "OptionalAuthProvider",
    "add_error_handlers",
    "RequestLoggingMiddleware",
]
