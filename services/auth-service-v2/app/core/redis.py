"""
Redis client lifecycle for auth-service.

Uses dedicated logical Redis DBs for:
- API permissions map
- Role permission cache
- API key token cache
- Refresh token cache
"""

import logging
from collections.abc import AsyncGenerator
from urllib.parse import urlparse, urlunparse

import redis.asyncio as aioredis

logger = logging.getLogger(__name__)

_redis_api_permissions: aioredis.Redis | None = None
_redis_role_permissions: aioredis.Redis | None = None
_redis_api_keys: aioredis.Redis | None = None
_redis_refresh_tokens: aioredis.Redis | None = None

MAX_CONNECT_RETRIES = 3


def _strip_db_from_redis_url(url: str) -> str:
  
    parsed = urlparse(url)
    return urlunparse(
        (
            parsed.scheme,
            parsed.netloc,
            "",  # remove path (/0 etc.)
            parsed.params,
            parsed.query,
            parsed.fragment,
        ),
    )


async def _connect_with_retry(client: aioredis.Redis, name: str) -> None:
    for attempt in range(1, MAX_CONNECT_RETRIES + 1):
        try:
            await client.ping()
            logger.info("Redis connection established for %s cache.", name)
            return
        except (aioredis.ConnectionError, aioredis.TimeoutError) as exc:
            logger.warning(
                "Redis %s attempt %d/%d failed: %s",
                name, attempt, MAX_CONNECT_RETRIES, exc,
            )
            if attempt == MAX_CONNECT_RETRIES:
                raise


async def init_redis(
    url: str,
    socket_timeout: int = 10,
    api_permissions_db: int = 0,
    role_permissions_db: int = 1,
    api_keys_db: int = 2,
    refresh_tokens_db: int = 3,
) -> None:
    """Create dedicated Redis clients for each auth cache domain."""
    global _redis_api_permissions, _redis_role_permissions, _redis_api_keys, _redis_refresh_tokens

    base_url = _strip_db_from_redis_url(url)

    _redis_api_permissions = aioredis.from_url(
        base_url,
        db=api_permissions_db,
        socket_timeout=socket_timeout,
        socket_connect_timeout=socket_timeout,
        decode_responses=True,
    )
    _redis_role_permissions = aioredis.from_url(
        base_url,
        db=role_permissions_db,
        socket_timeout=socket_timeout,
        socket_connect_timeout=socket_timeout,
        decode_responses=True,
    )
    _redis_api_keys = aioredis.from_url(
        base_url,
        db=api_keys_db,
        socket_timeout=socket_timeout,
        socket_connect_timeout=socket_timeout,
        decode_responses=True,
    )
    _redis_refresh_tokens = aioredis.from_url(
        base_url,
        db=refresh_tokens_db,
        socket_timeout=socket_timeout,
        socket_connect_timeout=socket_timeout,
        decode_responses=True,
    )

    await _connect_with_retry(_redis_api_permissions, "api-permissions")
    await _connect_with_retry(_redis_role_permissions, "role-permissions")
    await _connect_with_retry(_redis_api_keys, "api-keys")
    await _connect_with_retry(_redis_refresh_tokens, "refresh-tokens")


async def close_redis() -> None:
    """Close all Redis connections."""
    global _redis_api_permissions, _redis_role_permissions, _redis_api_keys, _redis_refresh_tokens

    if _redis_api_permissions:
        await _redis_api_permissions.aclose()
    if _redis_role_permissions:
        await _redis_role_permissions.aclose()
    if _redis_api_keys:
        await _redis_api_keys.aclose()
    if _redis_refresh_tokens:
        await _redis_refresh_tokens.aclose()

    _redis_api_permissions = None
    _redis_role_permissions = None
    _redis_api_keys = None
    _redis_refresh_tokens = None
    logger.info("Redis connections closed.")


def get_redis_client_api_permissions() -> aioredis.Redis:
    if _redis_api_permissions is None:
        raise RuntimeError("Redis (api permissions) not initialized.")
    return _redis_api_permissions


def get_redis_client_role_permissions() -> aioredis.Redis:
    if _redis_role_permissions is None:
        raise RuntimeError("Redis (role permissions) not initialized.")
    return _redis_role_permissions


def get_redis_client_api_keys() -> aioredis.Redis:
    if _redis_api_keys is None:
        raise RuntimeError("Redis (api keys) not initialized.")
    return _redis_api_keys


def get_redis_client_refresh_tokens() -> aioredis.Redis:
    if _redis_refresh_tokens is None:
        raise RuntimeError("Redis (refresh tokens) not initialized.")
    return _redis_refresh_tokens


# Backward-compatible helpers
def get_redis_client() -> aioredis.Redis:
    """Default client for auth tokens and oauth state."""
    return get_redis_client_api_keys()


async def get_redis() -> AsyncGenerator[aioredis.Redis, None]:
    """Default dependency for auth tokens and oauth state."""
    yield get_redis_client_api_keys()


async def get_redis_api_permissions() -> AsyncGenerator[aioredis.Redis, None]:
    yield get_redis_client_api_permissions()


async def get_redis_role_permissions() -> AsyncGenerator[aioredis.Redis, None]:
    yield get_redis_client_role_permissions()


async def get_redis_api_keys() -> AsyncGenerator[aioredis.Redis, None]:
    yield get_redis_client_api_keys()


async def get_redis_refresh_tokens() -> AsyncGenerator[aioredis.Redis, None]:
    yield get_redis_client_refresh_tokens()
