"""
Redis client lifecycle — re-exports from shared ai4icore_bootstrap.

Core-service uses a single Redis logical DB for entity caching (models, services).
"""

from ai4icore_bootstrap.redis import (  # noqa: F401
    init_redis,
    close_redis,
    get_redis,
    get_redis_client,
)
