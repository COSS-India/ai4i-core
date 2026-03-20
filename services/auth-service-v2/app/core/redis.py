"""
Redis — re-exports from shared ai4icore_bootstrap.
Auth-service uses the same Redis infra as every other service.
"""

from ai4icore_bootstrap.redis import (  # noqa: F401
    init_redis,
    close_redis,
    get_redis,
    get_redis_client,
)
