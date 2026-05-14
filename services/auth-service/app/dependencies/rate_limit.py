"""Lightweight Redis token-bucket rate limiter.

Used by /auth/forgot-password (3 / hour / email) per security spec.
Designed to be a thin building block — single function callable from any
route handler. Each call increments a counter for the given key; first
increment also sets a TTL. Once count > limit before TTL elapses, raises
HTTPException(429) with Retry-After.

Storage: Redis DB 0 (the default), prefixed with ``rl:`` to avoid collision
with cache namespaces.
"""

from typing import Optional

import redis.asyncio as aioredis
from fastapi import HTTPException, status


async def enforce_rate_limit(
    redis: aioredis.Redis,
    key: str,
    *,
    limit: int,
    window_seconds: int,
    error_code: str = "RATE_LIMITED",
    error_message: Optional[str] = None,
) -> None:
    """Enforce ``limit`` calls per ``window_seconds`` for the given ``key``.

    Raises HTTPException(429) with Retry-After once the limit is breached.
    Caller is expected to have stripped/lowered ``key`` if email-based, etc.
    """
    full_key = f"rl:{key}"
    pipe = redis.pipeline()
    pipe.incr(full_key)
    pipe.expire(full_key, window_seconds)
    count, _ = await pipe.execute()

    if count > limit:
        retry_after = max(int(ttl), 1)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "code": error_code,
                "message": error_message or "Too many requests. Try again later.",
            },
            headers={"Retry-After": str(retry_after)},
        )
