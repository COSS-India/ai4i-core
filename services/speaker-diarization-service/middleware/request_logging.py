"""
Request/response logging middleware for tracking Speaker Diarization API usage.

Copied from OCR service to keep behavior and structure consistent.
"""

import logging
import sys
import time
import os

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from ai4icore_logging import JSONFormatter

logger = logging.getLogger(__name__)
# Disable propagation to prevent duplicate logs in root logger
logger.propagate = False

# Add a handler with JSONFormatter to this logger
# This ensures logs are in JSON format even when propagation is disabled
if not logger.handlers:  # Only add if no handlers exist to prevent duplicates on reload
    handler = logging.StreamHandler(sys.stdout)
    service_name = os.getenv("SERVICE_NAME", "speaker-diarization-service")
    formatter = JSONFormatter(service_name=service_name)
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)  # Ensure INFO level logs are captured


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

        # Process request
        response = await call_next(request)

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

