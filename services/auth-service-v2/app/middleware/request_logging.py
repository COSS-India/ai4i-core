"""
Request logging middleware — re-exports from shared ai4icore_logging.

All services use the same structured logging. No local duplication.
Falls back to a minimal implementation if the shared lib is not available.
"""

try:
    from ai4icore_logging import RequestLoggingMiddleware

except ImportError:
    # Fallback: minimal structured request logging if shared lib not installed
    import logging
    import time
    import uuid

    from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
    from starlette.requests import Request
    from starlette.responses import Response

    _logger = logging.getLogger("request")
    _SKIP = {"/health", "/ready", "/docs", "/redoc", "/openapi.json", "/"}

    class RequestLoggingMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
            if request.url.path in _SKIP:
                return await call_next(request)

            trace_id = request.headers.get("X-Trace-Id") or str(uuid.uuid4())
            request.state.trace_id = trace_id

            start = time.monotonic()
            response = await call_next(request)
            ms = (time.monotonic() - start) * 1000

            _logger.info(
                "request_completed",
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": response.status_code,
                    "duration_ms": round(ms, 2),
                    "user_id": getattr(request.state, "user_id", None),
                    "tenant_id": getattr(request.state, "tenant_id", None),
                    "trace_id": trace_id,
                },
            )
            response.headers["X-Trace-Id"] = trace_id
            return response


__all__ = ["RequestLoggingMiddleware"]
