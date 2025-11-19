import json
import logging
from typing import Any, Awaitable, Callable, Optional

from redis.asyncio import Redis


logger = logging.getLogger(__name__)


def generate_cache_key(*parts: str) -> str:
    return ":".join(parts)


async def cache_get(redis: Redis, key: str) -> Optional[Any]:
    try:
        data = await redis.get(key)
        if not data:
            return None
        return json.loads(data)
    except Exception as e:
        logger.debug(f"cache_get error: {e}")
        return None


async def cache_set(redis: Redis, key: str, value: Any, ttl: int) -> None:
    try:
        await redis.set(key, json.dumps(value), ex=ttl)
    except Exception as e:
        logger.debug(f"cache_set error: {e}")


async def cache_delete(redis: Redis, key: str) -> None:
    try:
        await redis.delete(key)
    except Exception:
        pass


async def cache_delete_pattern(redis: Redis, pattern: str) -> None:
    try:
        it = redis.scan_iter(match=pattern)
        async for key in it:
            await redis.delete(key)
    except Exception:
        pass


async def cache_get_or_set(redis: Redis, key: str, ttl: int, producer: Callable[[], Awaitable[Any]]) -> Any:
    cached = await cache_get(redis, key)
    if cached is not None:
        return cached
    value = await producer()
    await cache_set(redis, key, value, ttl)
    return value


