"""
Tenant Middleware - Marks requests for tenant context extraction
"""
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from typing import Callable, List
import logging

logger = logging.getLogger(__name__)

# Paths to skip tenant resolution
SKIP_PATHS = ["/health", "/", "/docs", "/openapi.json", "/redoc"]


class TenantMiddleware(BaseHTTPMiddleware):
    """
    Middleware that marks requests for tenant context extraction.
    Actual tenant context extraction happens lazily when needed.
    """

    def __init__(self, app, tenant_paths: List[str] = None):
        super().__init__(app)
        self.tenant_paths = tenant_paths or ["/api/v1"]

    async def dispatch(self, request: Request, call_next: Callable):
        if request.url.path in SKIP_PATHS:
            return await call_next(request)

        for path_prefix in self.tenant_paths:
            if request.url.path.startswith(path_prefix):
                request.state.needs_tenant_context = True
                break

        return await call_next(request)
