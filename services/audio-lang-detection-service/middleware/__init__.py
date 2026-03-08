"""
Middleware package for Audio Language Detection Service.

Provides error handling, request logging, and tenant routing middleware.
"""

from .error_handler_middleware import add_error_handlers
from .request_logging import RequestLoggingMiddleware
from .auth_provider import AuthProvider, OptionalAuthProvider


__all__ = [
    "add_error_handlers",
    "RequestLoggingMiddleware",
    "AuthProvider",
    "OptionalAuthProvider",
    "get_tenant_context",
    "try_get_tenant_context",
    "TenantMiddleware",
    "TenantSchemaRouter",
    "get_tenant_db_session",
]
