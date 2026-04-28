"""
Redis client lifecycle for auth-service.

Single logical DB (default 0) for API keys, tenant status, revocation keys, etc.
Keys are distinguished by prefix (e.g. auth:apikey:, auth:tenant_status:).
"""

import logging
from collections.abc import AsyncGenerator
from urllib.parse import urlparse, urlunparse

import redis.asyncio as aioredis

logger = logging.getLogger(__name__)

_redis: aioredis.Redis | None = None

MAX_CONNECT_RETRIES = 3


def _strip_db_from_redis_url(url: str) -> str:
    parsed = urlparse(url)
    return urlunparse(
        (
            parsed.scheme,
            parsed.netloc,
            "",
            parsed.params,
            parsed.query,
            parsed.fragment,
        ),
    )


async def _connect_with_retry(client: aioredis.Redis, name: str, required: bool = True) -> bool:
    """Try to connect to Redis. Returns True on success."""
    for attempt in range(1, MAX_CONNECT_RETRIES + 1):
        try:
            await client.ping()
            logger.info("Redis connection established for %s.", name)
            return True
        except (aioredis.ConnectionError, aioredis.TimeoutError, OSError) as exc:
            logger.warning(
                "Redis %s attempt %d/%d failed: %s",
                name, attempt, MAX_CONNECT_RETRIES, exc,
            )
            if attempt == MAX_CONNECT_RETRIES:
                if required:
                    raise
                logger.error(
                    "Redis %s unavailable after %d retries — service will operate in degraded mode.",
                    name, MAX_CONNECT_RETRIES,
                )
                return False
    return False


async def init_redis(url: str, socket_timeout: int = 10, redis_db: int = 0) -> None:
    """Create a single Redis client for all auth cache domains."""
    global _redis

    base_url = _strip_db_from_redis_url(url)

    _redis = aioredis.from_url(
        base_url,
        db=redis_db,
        socket_timeout=socket_timeout,
        socket_connect_timeout=socket_timeout,
        decode_responses=True,
    )

    await _connect_with_retry(_redis, "auth")


async def close_redis() -> None:
    """Close the Redis connection."""
    global _redis

    if _redis:
        await _redis.aclose()

    _redis = None
    logger.info("Redis connection closed.")


def get_redis_client() -> aioredis.Redis:
    if _redis is None:
        raise RuntimeError("Redis not initialized.")
    return _redis


# Backward-compatible names — all resolve to the single DB 0 client.
def get_redis_client_api_permissions() -> aioredis.Redis:
    return get_redis_client()


def get_redis_client_role_permissions() -> aioredis.Redis:
    return get_redis_client()


def get_redis_client_api_keys() -> aioredis.Redis:
    return get_redis_client()


def get_redis_client_refresh_tokens() -> aioredis.Redis:
    return get_redis_client()


async def get_redis() -> AsyncGenerator[aioredis.Redis, None]:
    yield get_redis_client()


async def get_redis_api_permissions() -> AsyncGenerator[aioredis.Redis, None]:
    yield get_redis_client()


async def get_redis_role_permissions() -> AsyncGenerator[aioredis.Redis, None]:
    yield get_redis_client()


async def get_redis_api_keys() -> AsyncGenerator[aioredis.Redis, None]:
    yield get_redis_client()


async def get_redis_refresh_tokens() -> AsyncGenerator[aioredis.Redis, None]:
    yield get_redis_client()
