"""
Tenant Middleware
Extracts tenant context after authentication and sets it in request state.

Note: This middleware runs BEFORE route dependencies, so it can't access
AuthProvider results directly. Instead, it sets up a hook that will be
called when tenant context is needed (lazy evaluation in get_tenant_db_session).
"""
from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from typing import Callable
import logging
import traceback

logger = logging.getLogger(__name__)


class TenantMiddleware(BaseHTTPMiddleware):
    """
    Middleware that marks requests for tenant context extraction.
    Actual tenant context extraction happens lazily when needed.
    """

    async def dispatch(self, request: Request, call_next: Callable):
        # Skip tenant resolution for health checks and non-API endpoints
        if request.url.path in ["/health", "/", "/docs", "/openapi.json", "/redoc"]:
            try:
                return await call_next(request)
            except Exception as exc:
                logger.error("Error processing health request in TenantMiddleware: %s\n%s", exc, traceback.format_exc())
                return JSONResponse(status_code=500, content={"detail": {"code": "INTERNAL_ERROR", "message": "Internal server error"}})

        if request.url.path.startswith("/api/v1/language-diarization"):
            request.state.needs_tenant_context = True

        try:
            return await call_next(request)
        except Exception as exc:
            # Defensive: ensure we always return a Response (avoid "No response returned.")
            logger.error("Unhandled exception in downstream app (TenantMiddleware): %s\n%s", exc, traceback.format_exc())
            return JSONResponse(status_code=500, content={"detail": {"code": "INTERNAL_ERROR", "message": "Internal server error"}})
