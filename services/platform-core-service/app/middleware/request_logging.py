"""
Request logging middleware — re-exports from shared ai4icore_logging.

Falls back to a minimal local implementation if the shared lib is not
available (e.g. test environments without the lib installed).
"""

try:
    from ai4icore_logging import RequestLoggingMiddleware  # type: ignore  # noqa: F401

except ImportError:
    import logging
    import time
    import uuid

    from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
    from starlette.requests import Request
    from starlette.responses import Response

    _logger = logging.getLogger("request")
    _SKIP = {"/health", "/docs", "/redoc", "/openapi.json"}

    class RequestLoggingMiddleware(BaseHTTPMiddleware):  # type: ignore[no-redef]
        async def dispatch(
            self, request: Request, call_next: RequestResponseEndpoint
        ) -> Response:
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
