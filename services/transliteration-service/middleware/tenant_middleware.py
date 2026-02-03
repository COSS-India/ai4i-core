"""
Tenant Middleware
Extracts tenant context after authentication and sets it in request state.

Note: This middleware runs BEFORE route dependencies, so it can't access
AuthProvider results directly. Instead, it sets up a hook that will be
called when tenant context is needed (lazy evaluation in get_tenant_db_session).
"""
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from typing import Callable
import logging

logger = logging.getLogger(__name__)


class TenantMiddleware(BaseHTTPMiddleware):
    """
    Middleware that marks requests for tenant context extraction.
    Actual tenant context extraction happens lazily when needed.
    """

    async def dispatch(self, request: Request, call_next: Callable):
        # Skip tenant resolution for health checks and non-API endpoints
        if request.url.path in ["/health", "/", "/docs", "/openapi.json", "/redoc"]:
            return await call_next(request)

        if request.url.path.startswith("/api/v1/transliteration"):
            request.state.needs_tenant_context = True

        return await call_next(request)
