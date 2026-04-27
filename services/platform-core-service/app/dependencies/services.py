"""
Service dependency factories.

Routes use these via Depends() — never construct repos or services directly.
This is the only place where repositories are imported and wired into
business-logic services.
"""

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

import redis.asyncio as aioredis

from app.core.config import settings
from app.core.database import get_db
from app.core.redis import get_redis
from app.repositories.model_repository import ModelRepository
from app.repositories.service_repository import ServiceRepository
from app.services.cache_service import CacheService
from app.services.model_service import ModelService
from app.services.service_service import ServiceService


async def get_cache_service(
    redis_client: aioredis.Redis = Depends(get_redis),
) -> CacheService:
    return CacheService(
        redis_client=redis_client,
        model_ttl_seconds=settings.model_cache_ttl_seconds,
        service_ttl_seconds=settings.service_cache_ttl_seconds,
    )


async def get_model_service(
    db: AsyncSession = Depends(get_db),
    cache: CacheService = Depends(get_cache_service),
) -> ModelService:
    return ModelService(
        model_repo=ModelRepository(db),
        service_repo=ServiceRepository(db),
        cache=cache,
    )


async def get_service_service(
    db: AsyncSession = Depends(get_db),
    cache: CacheService = Depends(get_cache_service),
) -> ServiceService:
    return ServiceService(
        service_repo=ServiceRepository(db),
        model_repo=ModelRepository(db),
        cache=cache,
    )
