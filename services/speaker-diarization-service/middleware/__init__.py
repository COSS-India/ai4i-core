"""
Middleware package for Speaker Diarization Service.

Provides rate limiting, error handling, and request logging middleware.
Authentication can be added later following the same pattern as NMT/TTS/OCR.
"""

from .rate_limit_middleware import RateLimitMiddleware
from .error_handler_middleware import add_error_handlers
from .request_logging import RequestLoggingMiddleware

__all__ = [
    "RateLimitMiddleware",
    "add_error_handlers",
    "RequestLoggingMiddleware",
]

