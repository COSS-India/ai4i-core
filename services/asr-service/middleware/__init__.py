"""
Middleware package for ASR Service.

Contains authentication, rate limiting, and error handling middleware.
Request logging is now handled by ai4icore_logging.LoggingPlugin.
"""

from .auth_provider import AuthProvider, OptionalAuthProvider
from .rate_limit_middleware import RateLimitMiddleware
from .error_handler_middleware import add_error_handlers

__all__ = [
    "AuthProvider",
    "OptionalAuthProvider", 
    "RateLimitMiddleware",
    "add_error_handlers",
]
