"""
Rate limiting middleware using Redis for per-API-key throttling.

Copied from NMT service to keep semantics and structure consistent.
"""

from typing import Dict

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode

from middleware.exceptions import RateLimitExceededError
import logging

logger = logging.getLogger(__name__)
tracer = trace.get_tracer("ocr-service")


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Rate limiting middleware using Redis sliding window algorithm."""

    def __init__(
        self,
        app,
        redis_client,
        requests_per_minute: int = 60,
        requests_per_hour: int = 1000,
    ):
        super().__init__(app)
        self.redis_client = redis_client
        self.requests_per_minute = requests_per_minute
        self.requests_per_hour = requests_per_hour

    async def dispatch(self, request: Request, call_next):
        """Process request with rate limiting."""
        # Get Redis client from self or app.state (fallback)
        redis_client = self.redis_client
        if redis_client is None:
            redis_client = getattr(request.app.state, "redis_client", None)

        # If Redis is not available, skip rate limiting
        if redis_client is None:
            response = await call_next(request)
            return response

        # Extract API key from request.state (populated by AuthProvider)
        api_key_id = getattr(request.state, "api_key_id", None)

        # If no API key (unauthenticated request), skip rate limiting
        if not api_key_id:
            response = await call_next(request)
            return response

        # Check rate limits with tracing
        if not tracer:
            # Fallback if tracing not available
            if not await self.check_rate_limit(api_key_id, redis_client):
                raise RateLimitExceededError(
                    message=f"Rate limit exceeded for API key {api_key_id}",
                    retry_after=60,
                )
        else:
            with tracer.start_as_current_span("rate_limit.check") as span:
                span.set_attribute("rate_limit.api_key_id", str(api_key_id))
                span.set_attribute("rate_limit.limit_per_minute", self.requests_per_minute)
                span.set_attribute("rate_limit.limit_per_hour", self.requests_per_hour)
                span.add_event("rate_limit.check.start")
                
                if not await self.check_rate_limit(api_key_id, redis_client):
                    span.set_attribute("rate_limit.exceeded", True)
                    span.add_event("rate_limit.exceeded")
                    span.set_status(Status(StatusCode.ERROR, "Rate limit exceeded"))
                    raise RateLimitExceededError(
                        message=f"Rate limit exceeded for API key {api_key_id}",
                        retry_after=60,
                    )
                
                span.set_attribute("rate_limit.exceeded", False)
                span.add_event("rate_limit.check.passed")
                span.set_status(Status(StatusCode.OK))

        # Process request
        response = await call_next(request)

        # Add rate limit headers
        if tracer:
            with tracer.start_as_current_span("rate_limit.get_info") as span:
                span.set_attribute("rate_limit.api_key_id", str(api_key_id))
                rate_info = await self.get_rate_limit_info(api_key_id, redis_client)
                span.set_attribute("rate_limit.minute_used", rate_info["minute_used"])
                span.set_attribute("rate_limit.hour_used", rate_info["hour_used"])
                span.set_attribute("rate_limit.remaining_minute", rate_info["remaining_minute"])
                span.set_attribute("rate_limit.remaining_hour", rate_info["remaining_hour"])
        else:
            rate_info = await self.get_rate_limit_info(api_key_id, redis_client)
        
        response.headers["X-RateLimit-Limit-Minute"] = str(self.requests_per_minute)
        response.headers["X-RateLimit-Remaining-Minute"] = str(
            rate_info["remaining_minute"]
        )
        response.headers["X-RateLimit-Limit-Hour"] = str(self.requests_per_hour)
        response.headers["X-RateLimit-Remaining-Hour"] = str(
            rate_info["remaining_hour"]
        )

        return response

    async def check_rate_limit(self, api_key_id: int, redis_client) -> bool:
        """Check if API key is within rate limits using sliding window algorithm."""
        if redis_client is None:
            return True  # Skip rate limiting if Redis is not available

        if not tracer:
            # Fallback if tracing not available
            return await self._check_rate_limit_impl(api_key_id, redis_client)

        with tracer.start_as_current_span("redis.rate_limit_check") as span:
            span.set_attribute("redis.operation", "rate_limit_check")
            span.set_attribute("redis.api_key_id", str(api_key_id))
            
            try:
                # Minute rate limit
                minute_key = f"rate_limit:minute:{api_key_id}"
                span.add_event("redis.operation.start", {"key": minute_key, "operation": "incr"})
                minute_count = await redis_client.incr(minute_key)
                span.set_attribute("rate_limit.minute_count", minute_count)
                
                if minute_count == 1:
                    await redis_client.expire(minute_key, 60)  # 60 seconds
                    span.add_event("redis.operation", {"operation": "expire", "ttl": 60})

                if minute_count > self.requests_per_minute:
                    span.set_attribute("rate_limit.minute_exceeded", True)
                    span.add_event("rate_limit.minute_exceeded", {
                        "count": minute_count,
                        "limit": self.requests_per_minute
                    })
                    logger.warning(
                        "Minute rate limit exceeded for API key %s: %s/%s",
                        api_key_id,
                        minute_count,
                        self.requests_per_minute,
                    )
                    return False

                # Hour rate limit
                hour_key = f"rate_limit:hour:{api_key_id}"
                span.add_event("redis.operation.start", {"key": hour_key, "operation": "incr"})
                hour_count = await redis_client.incr(hour_key)
                span.set_attribute("rate_limit.hour_count", hour_count)
                
                if hour_count == 1:
                    await redis_client.expire(hour_key, 3600)  # 3600 seconds
                    span.add_event("redis.operation", {"operation": "expire", "ttl": 3600})

                if hour_count > self.requests_per_hour:
                    span.set_attribute("rate_limit.hour_exceeded", True)
                    span.add_event("rate_limit.hour_exceeded", {
                        "count": hour_count,
                        "limit": self.requests_per_hour
                    })
                    logger.warning(
                        "Hour rate limit exceeded for API key %s: %s/%s",
                        api_key_id,
                        hour_count,
                        self.requests_per_hour,
                    )
                    return False

                span.set_attribute("rate_limit.passed", True)
                span.add_event("rate_limit.check.complete", {"status": "passed"})
                return True

            except Exception as exc:  # pragma: no cover - defensive path
                span.set_attribute("error", True)
                span.set_attribute("error.type", type(exc).__name__)
                span.set_attribute("error.message", str(exc))
                span.set_status(Status(StatusCode.ERROR, str(exc)))
                span.record_exception(exc)
                logger.error("Error checking rate limit for API key %s: %s", api_key_id, exc)
                # On error, allow the request to proceed
                return True

    async def _check_rate_limit_impl(self, api_key_id: int, redis_client) -> bool:
        """Fallback implementation when tracing is not available."""
        try:
            minute_key = f"rate_limit:minute:{api_key_id}"
            minute_count = await redis_client.incr(minute_key)
            if minute_count == 1:
                await redis_client.expire(minute_key, 60)

            if minute_count > self.requests_per_minute:
                logger.warning(
                    "Minute rate limit exceeded for API key %s: %s/%s",
                    api_key_id,
                    minute_count,
                    self.requests_per_minute,
                )
                return False

            hour_key = f"rate_limit:hour:{api_key_id}"
            hour_count = await redis_client.incr(hour_key)
            if hour_count == 1:
                await redis_client.expire(hour_key, 3600)

            if hour_count > self.requests_per_hour:
                logger.warning(
                    "Hour rate limit exceeded for API key %s: %s/%s",
                    api_key_id,
                    hour_count,
                    self.requests_per_hour,
                )
                return False

            return True

        except Exception as exc:
            logger.error("Error checking rate limit for API key %s: %s", api_key_id, exc)
            return True

    async def get_rate_limit_info(
        self, api_key_id: int, redis_client
    ) -> Dict[str, int]:
        """Get current rate limit usage information."""
        if redis_client is None:
            return {
                "minute_used": 0,
                "minute_limit": self.requests_per_minute,
                "hour_used": 0,
                "hour_limit": self.requests_per_hour,
                "remaining_minute": self.requests_per_minute,
                "remaining_hour": self.requests_per_hour,
            }

        try:
            minute_key = f"rate_limit:minute:{api_key_id}"
            hour_key = f"rate_limit:hour:{api_key_id}"

            minute_used = await redis_client.get(minute_key) or 0
            hour_used = await redis_client.get(hour_key) or 0

            minute_used = int(minute_used)
            hour_used = int(hour_used)

            return {
                "minute_used": minute_used,
                "minute_limit": self.requests_per_minute,
                "hour_used": hour_used,
                "hour_limit": self.requests_per_hour,
                "remaining_minute": max(
                    0, self.requests_per_minute - minute_used
                ),
                "remaining_hour": max(0, self.requests_per_hour - hour_used),
            }
        except Exception as exc:  # pragma: no cover - defensive path
            logger.error(
                "Error getting rate limit info for API key %s: %s", api_key_id, exc
            )
            return {
                "minute_used": 0,
                "minute_limit": self.requests_per_minute,
                "hour_used": 0,
                "hour_limit": self.requests_per_hour,
                "remaining_minute": self.requests_per_minute,
                "remaining_hour": self.requests_per_hour,
            }


