"""
Redis client lifecycle and get_redis dependency.

Used by ALL microservices. No service-specific imports.
"""

import logging
from collections.abc import AsyncGenerator

import redis.asyncio as aioredis

logger = logging.getLogger(__name__)

_redis_client: aioredis.Redis | None = None

MAX_CONNECT_RETRIES = 3


async def init_redis(
    url: str,
    socket_timeout: int = 10,
) -> None:
    """Create the async Redis client. Called during app startup."""
    global _redis_client

    logger.info("Connecting to Redis: %s", url.split("@")[-1] if "@" in url else url)

    _redis_client = aioredis.from_url(
        url,
        socket_timeout=socket_timeout,
        socket_connect_timeout=socket_timeout,
        decode_responses=True,
    )

    for attempt in range(1, MAX_CONNECT_RETRIES + 1):
        try:
            await _redis_client.ping()
            logger.info("Redis connection established.")
            return
        except (aioredis.ConnectionError, aioredis.TimeoutError) as exc:
            logger.warning("Redis attempt %d/%d failed: %s", attempt, MAX_CONNECT_RETRIES, exc)
            if attempt == MAX_CONNECT_RETRIES:
                raise


async def close_redis() -> None:
    """Close the Redis connection. Called during app shutdown."""
    global _redis_client
    if _redis_client:
        await _redis_client.aclose()
        logger.info("Redis connection closed.")
    _redis_client = None


async def get_redis() -> AsyncGenerator[aioredis.Redis, None]:
    """FastAPI dependency that yields the Redis client."""
    if _redis_client is None:
        raise RuntimeError("Redis not initialized. Call init_redis() first.")
    yield _redis_client


def get_redis_client() -> aioredis.Redis:
    """Return the raw Redis client (for non-DI contexts)."""
    if _redis_client is None:
        raise RuntimeError("Redis not initialized.")
    return _redis_client
