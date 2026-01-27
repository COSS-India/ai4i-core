"""
Request/response logging middleware for tracking Audio Language Detection API usage.

Copied from language-diarization service to keep behavior and structure consistent.
"""

import logging
import time

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from ai4icore_logging import get_logger

logger = get_logger(__name__)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Request logging middleware for tracking API usage."""

    def __init__(self, app):
        super().__init__(app)

    async def dispatch(self, request: Request, call_next):
        """Log request and response information."""
        # Capture start time
        start_time = time.time()

        # Extract request info
        method = request.method
        path = request.url.path
        client_ip = request.client.host if request.client else "unknown"
        user_agent = request.headers.get("user-agent", "unknown")

        # Extract auth context from request.state if available
        user_id = getattr(request.state, "user_id", None)
        api_key_id = getattr(request.state, "api_key_id", None)
        
        # Log incoming request immediately for debugging - use try/except to ensure it always logs
        try:
            logger.info(
                f"Incoming {method} request to {path} from {client_ip}",
                extra={
                    "method": method,
                    "path": path,
                    "client_ip": client_ip,
                    "user_id": user_id,
                    "api_key_id": api_key_id,
                }
            )
        except Exception as e:
            # Fallback to basic logging if structured logging fails
            import sys
            print(f"ERROR: Failed to log incoming request: {e}", file=sys.stderr)
            logger.error(f"Failed to log incoming request: {e}")

        # Process request
        try:
            response = await call_next(request)
        except Exception as e:
            # Log the exception before re-raising
            logger.error(f"Exception during request processing: {e}", exc_info=True)
            raise

        # Calculate processing time
        processing_time = time.time() - start_time

        # Determine log level based on status code
        status_code = response.status_code
        if 200 <= status_code < 300:
            log_level = logging.INFO
        elif 400 <= status_code < 500:
            log_level = logging.WARNING
        else:
            log_level = logging.ERROR

        # Log request/response
        log_message = (
            f"{method} {path} - {status_code} - {processing_time:.3f}s - "
            f"user_id={user_id} api_key_id={api_key_id} - "
            f"client_ip={client_ip}"
        )

        logger.log(log_level, log_message)

        # Add processing time header
        response.headers["X-Process-Time"] = f"{processing_time:.3f}"

        return response

