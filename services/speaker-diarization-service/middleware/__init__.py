"""
Middleware package for Speaker Diarization Service.

Provides error handling, and request logging middleware.
"""

from .error_handler_middleware import add_error_handlers
from .request_logging import RequestLoggingMiddleware
from .auth_provider import AuthProvider, OptionalAuthProvider

__all__ = [
    "add_error_handlers",
    "RequestLoggingMiddleware",
    "AuthProvider",
    "OptionalAuthProvider",
]
