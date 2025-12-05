"""
Request logging middleware for NER service.

Copied from OCR service to keep behavior consistent.
"""

import logging
import time

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Middleware for basic request/response logging."""

    async def dispatch(self, request: Request, call_next):
        start_time = time.time()
        response = await call_next(request)
        process_time_ms = (time.time() - start_time) * 1000

        logger.info(
            "%s %s - %d (%.2f ms)",
            request.method,
            request.url.path,
            response.status_code,
            process_time_ms,
        )

        return response



