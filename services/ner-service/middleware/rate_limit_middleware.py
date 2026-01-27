"""
Simple Redis-based rate limiting middleware for NER service.

Copied from OCR service to keep behavior consistent.
"""

import time
from typing import Callable, Optional

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from .exceptions import RateLimitExceededError


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Middleware for per-API-key rate limiting using Redis."""

    def __init__(
        self,
        app,
        redis_client=None,
        requests_per_minute: int = 60,
        requests_per_hour: int = 1000,
    ):
        super().__init__(app)
        self.redis_client = redis_client
        self.requests_per_minute = requests_per_minute
        self.requests_per_hour = requests_per_hour

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Skip rate limiting for health check endpoints
        if request.url.path in ["/health", "/metrics", "/"]:
            return await call_next(request)
        
        # If Redis is not available, skip rate limiting
        redis_client = getattr(request.app.state, "redis_client", None) or self.redis_client
        if not redis_client:
            return await call_next(request)

        # Use API key or IP address as the identifier
        api_key = request.headers.get("X-API-Key")
        identifier = api_key or request.client.host or "unknown"

        current_time = int(time.time())
        minute_window = current_time // 60
        hour_window = current_time // 3600

        minute_key = f"rate:{identifier}:m:{minute_window}"
        hour_key = f"rate:{identifier}:h:{hour_window}"

        try:
            pipe = redis_client.pipeline()
            pipe.incr(minute_key)
            pipe.expire(minute_key, 60)
            pipe.incr(hour_key)
            pipe.expire(hour_key, 3600)
            minute_count, _, hour_count, _ = await pipe.execute()
        except Exception:
            # On Redis error, do not block the request
            return await call_next(request)

        if minute_count > self.requests_per_minute or hour_count > self.requests_per_hour:
            raise RateLimitExceededError(
                message=f"Rate limit exceeded: {minute_count} req/min, {hour_count} req/hour",
                retry_after=60,
            )

        return await call_next(request)



