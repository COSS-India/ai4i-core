"""
Rate limiting middleware using Redis for per-API-key throttling.
"""
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi import Request, Response
from typing import Dict
from middleware.exceptions import RateLimitExceededError
import logging

logger = logging.getLogger(__name__)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Rate limiting middleware using Redis sliding window algorithm."""
    
    def __init__(self, app, redis_client, requests_per_minute: int = 60, requests_per_hour: int = 1000):
        super().__init__(app)
        self.redis_client = redis_client
        self.requests_per_minute = requests_per_minute
        self.requests_per_hour = requests_per_hour
    
    async def dispatch(self, request: Request, call_next):
        """Process request with rate limiting."""
        # Extract API key from request.state (populated by AuthProvider)
        api_key_id = getattr(request.state, 'api_key_id', None)
        
        # If no API key (unauthenticated request), skip rate limiting
        if not api_key_id:
            response = await call_next(request)
            return response
        
        # Check rate limits
        if not await self.check_rate_limit(api_key_id):
            raise RateLimitExceededError(
                message=f"Rate limit exceeded for API key {api_key_id}",
                retry_after=60
            )
        
        # Process request
        response = await call_next(request)
        
        # Add rate limit headers
        rate_info = await self.get_rate_limit_info(api_key_id)
        response.headers["X-RateLimit-Limit-Minute"] = str(self.requests_per_minute)
        response.headers["X-RateLimit-Remaining-Minute"] = str(rate_info["remaining_minute"])
        response.headers["X-RateLimit-Limit-Hour"] = str(self.requests_per_hour)
        response.headers["X-RateLimit-Remaining-Hour"] = str(rate_info["remaining_hour"])
        
        return response
    
    async def check_rate_limit(self, api_key_id: int) -> bool:
        """Check if API key is within rate limits using sliding window algorithm."""
        try:
            # Minute rate limit
            minute_key = f"rate_limit:minute:{api_key_id}"
            minute_count = await self.redis_client.incr(minute_key)
            if minute_count == 1:
                await self.redis_client.expire(minute_key, 60)  # 60 seconds
            
            if minute_count > self.requests_per_minute:
                logger.warning(f"Minute rate limit exceeded for API key {api_key_id}: {minute_count}/{self.requests_per_minute}")
                return False
            
            # Hour rate limit
            hour_key = f"rate_limit:hour:{api_key_id}"
            hour_count = await self.redis_client.incr(hour_key)
            if hour_count == 1:
                await self.redis_client.expire(hour_key, 3600)  # 3600 seconds
            
            if hour_count > self.requests_per_hour:
                logger.warning(f"Hour rate limit exceeded for API key {api_key_id}: {hour_count}/{self.requests_per_hour}")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"Error checking rate limit for API key {api_key_id}: {e}")
            # On error, allow the request to proceed
            return True
    
    async def get_rate_limit_info(self, api_key_id: int) -> Dict[str, int]:
        """Get current rate limit usage information."""
        try:
            minute_key = f"rate_limit:minute:{api_key_id}"
            hour_key = f"rate_limit:hour:{api_key_id}"
            
            minute_used = await self.redis_client.get(minute_key) or 0
            hour_used = await self.redis_client.get(hour_key) or 0
            
            minute_used = int(minute_used)
            hour_used = int(hour_used)
            
            return {
                "minute_used": minute_used,
                "minute_limit": self.requests_per_minute,
                "hour_used": hour_used,
                "hour_limit": self.requests_per_hour,
                "remaining_minute": max(0, self.requests_per_minute - minute_used),
                "remaining_hour": max(0, self.requests_per_hour - hour_used)
            }
        except Exception as e:
            logger.error(f"Error getting rate limit info for API key {api_key_id}: {e}")
            return {
                "minute_used": 0,
                "minute_limit": self.requests_per_minute,
                "hour_used": 0,
                "hour_limit": self.requests_per_hour,
                "remaining_minute": self.requests_per_minute,
                "remaining_hour": self.requests_per_hour
            }
