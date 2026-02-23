"""
Try-It rate limiting utilities
Supports Redis-based and in-memory rate limiting for anonymous try-it access
"""
import os
import time
import logging
from typing import Dict, Any, Optional
from fastapi import Request

logger = logging.getLogger(__name__)

# Try-It rate limiting configuration
TRY_IT_LIMIT = int(os.getenv("TRY_IT_LIMIT", "5"))
TRY_IT_TTL_SECONDS = int(os.getenv("TRY_IT_TTL_SECONDS", "3600"))

# In-memory fallback counter (used when Redis is unavailable)
try_it_counters: Dict[str, Dict[str, Any]] = {}


def get_try_it_key(request: Request) -> str:
    """Generate a unique key for try-it rate limiting based on session ID or IP."""
    session_id = request.headers.get("X-Anonymous-Session-Id") or request.headers.get("x-anonymous-session-id")
    if session_id:
        return f"tryit:nmt:session:{session_id}"
    client_ip = request.client.host if request.client else "unknown"
    return f"tryit:nmt:ip:{client_ip}"


async def increment_try_it_count(key: str, redis_client) -> int:
    """
    Increment try-it request count for the given key.
    
    Args:
        key: Rate limiting key (session ID or IP based)
        redis_client: Redis client instance (can be None for in-memory fallback)
        
    Returns:
        Current count after increment
    """
    # Prefer Redis if available
    if redis_client:
        try:
            count = await redis_client.incr(key)
            if count == 1:
                await redis_client.expire(key, TRY_IT_TTL_SECONDS)
            return int(count)
        except Exception as e:
            logger.warning(f"Redis increment failed, falling back to in-memory: {e}")
            # Fall through to in-memory counter

    # Fallback: in-memory counter with TTL
    now = time.time()
    entry = try_it_counters.get(key)
    if not entry or (now - entry["started_at"] > TRY_IT_TTL_SECONDS):
        entry = {"count": 0, "started_at": now}
    entry["count"] += 1
    try_it_counters[key] = entry
    return entry["count"]


def is_try_it_rate_limit_exceeded(count: int) -> bool:
    """Check if try-it rate limit is exceeded."""
    return count > TRY_IT_LIMIT
