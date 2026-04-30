"""
Redis-based per-API-key rate limiting middleware.

Supports optional OpenTelemetry tracing -- activates automatically when
``opentelemetry`` is installed.

Usage:
    from ai4icore_service_base import RateLimitMiddleware

    app.add_middleware(
        RateLimitMiddleware,
        redis_client=redis,
        requests_per_minute=60,
        requests_per_hour=1000,
    )
"""

import logging

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from ai4icore_exceptions import RateLimitExceededError

logger = logging.getLogger(__name__)

# Optional OpenTelemetry support
try:
    from opentelemetry import trace
    from opentelemetry.trace import Status, StatusCode

    _OTEL_AVAILABLE = True
except ImportError:
    _OTEL_AVAILABLE = False


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Per-API-key rate limiting using Redis counters with automatic expiry."""

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

    # ------------------------------------------------------------------
    # Middleware entry point
    # ------------------------------------------------------------------
    async def dispatch(self, request: Request, call_next) -> Response:
        redis_client = self.redis_client or getattr(request.app.state, "redis_client", None)
        if redis_client is None:
            return await call_next(request)

        api_key_id = getattr(request.state, "api_key_id", None)
        if not api_key_id:
            return await call_next(request)

        # Check rate limits
        allowed = await self._check(api_key_id, redis_client)
        if not allowed:
            raise RateLimitExceededError(
                message=f"Rate limit exceeded for API key {api_key_id}",
                retry_after=60,
            )

        response = await call_next(request)

        # Attach informational headers
        info = await self._get_info(api_key_id, redis_client)
        response.headers["X-RateLimit-Limit-Minute"] = str(self.requests_per_minute)
        response.headers["X-RateLimit-Remaining-Minute"] = str(info["remaining_minute"])
        response.headers["X-RateLimit-Limit-Hour"] = str(self.requests_per_hour)
        response.headers["X-RateLimit-Remaining-Hour"] = str(info["remaining_hour"])

        return response

    # ------------------------------------------------------------------
    # Core rate-limit check
    # ------------------------------------------------------------------
    async def _check(self, api_key_id, redis_client) -> bool:
        try:
            # Minute window
            minute_key = f"rate_limit:minute:{api_key_id}"
            minute_count = await redis_client.incr(minute_key)
            if minute_count == 1:
                await redis_client.expire(minute_key, 60)

            if minute_count > self.requests_per_minute:
                logger.warning(
                    "Minute rate limit exceeded for API key %s: %s/%s",
                    api_key_id, minute_count, self.requests_per_minute,
                )
                self._trace_exceeded("minute", api_key_id, minute_count, self.requests_per_minute)
                return False

            # Hour window
            hour_key = f"rate_limit:hour:{api_key_id}"
            hour_count = await redis_client.incr(hour_key)
            if hour_count == 1:
                await redis_client.expire(hour_key, 3600)

            if hour_count > self.requests_per_hour:
                logger.warning(
                    "Hour rate limit exceeded for API key %s: %s/%s",
                    api_key_id, hour_count, self.requests_per_hour,
                )
                self._trace_exceeded("hour", api_key_id, hour_count, self.requests_per_hour)
                return False

            return True

        except Exception as exc:
            logger.error("Error checking rate limit for API key %s: %s", api_key_id, exc)
            return True  # Fail-open on Redis errors

    # ------------------------------------------------------------------
    # Info for response headers
    # ------------------------------------------------------------------
    async def _get_info(self, api_key_id, redis_client) -> dict[str, int]:
        try:
            minute_used = int(await redis_client.get(f"rate_limit:minute:{api_key_id}") or 0)
            hour_used = int(await redis_client.get(f"rate_limit:hour:{api_key_id}") or 0)
            return {
                "remaining_minute": max(0, self.requests_per_minute - minute_used),
                "remaining_hour": max(0, self.requests_per_hour - hour_used),
            }
        except Exception:
            return {
                "remaining_minute": self.requests_per_minute,
                "remaining_hour": self.requests_per_hour,
            }

    # ------------------------------------------------------------------
    # Optional tracing helper
    # ------------------------------------------------------------------
    @staticmethod
    def _trace_exceeded(window: str, api_key_id, count: int, limit: int) -> None:
        if not _OTEL_AVAILABLE:
            return
        tracer = trace.get_tracer("ai4icore_service_base")
        with tracer.start_as_current_span("rate_limit.exceeded") as span:
            span.set_attribute("rate_limit.window", window)
            span.set_attribute("rate_limit.api_key_id", str(api_key_id))
            span.set_attribute("rate_limit.count", count)
            span.set_attribute("rate_limit.limit", limit)
            span.set_status(Status(StatusCode.ERROR, f"{window} rate limit exceeded"))
