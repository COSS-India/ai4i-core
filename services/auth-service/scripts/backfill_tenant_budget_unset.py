"""
One-time backfill: push tenant_budget_unset=True onto every already-issued
API key belonging to a tenant with tenants.allocated_budget IS NULL.

Why this is needed: APIKeyService.set_tenant_budget_unset_for_tenant is only
ever called from TenantService.revise_tenant_budget, which by definition
pushes False — a Budget was just assigned there. A key issued under a
tenant that has never been through a budget revision therefore has no
tenant_budget_unset entry in its cached_data/Redis hash at all.
/auth/validate's _cached_tenant_budget_unset reads that absence as
"configured" (fail-open, same shape as _cached_budget_window_is_expired),
so those keys keep making real, billed inference calls with zero budget
enforcement — exactly the population this fix set out to close. Nothing
else self-heals this: a tier reassignment only force-writes tier_id
(set_tier_id_for_tenant), and a Redis eviction rehydrates cached_data
verbatim (APIKeyService._rehydrate_cache_from_db) rather than recomputing
it.

Idempotent — safe to re-run (e.g. after a fresh batch of Tenants signed up
before their first Budget allocation). Run once after deploying this fix:

    cd services/auth-service && .venv/bin/python -m scripts.backfill_tenant_budget_unset
"""
import asyncio
import logging

from sqlalchemy import select

from ai4i_core.bootstrap.database import get_db
from app.core.config import settings
from app.core.database import init_database, close_database
from app.core.redis import init_redis, close_redis, get_redis_client
from app.models.tenant import Tenant
from app.repositories.api_key_repository import APIKeyRepository
from app.services.api_key_service import APIKeyService
from app.services.cache_service import CacheService

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("backfill_tenant_budget_unset")


async def _run() -> int:
    async for session in get_db():
        result = await session.execute(
            select(Tenant.id).where(Tenant.allocated_budget.is_(None))
        )
        tenant_ids = [row[0] for row in result.all()]
        logger.info(
            "Backfilling tenant_budget_unset for %d tenant(s) with no allocated_budget",
            len(tenant_ids),
        )

        svc = APIKeyService(APIKeyRepository(session), CacheService(get_redis_client()))
        for tenant_id in tenant_ids:
            await svc.set_tenant_budget_unset_for_tenant(tenant_id, True)
            logger.info("tenant_id=%s: pushed tenant_budget_unset=1", tenant_id)
        return len(tenant_ids)
    return 0


async def main() -> None:
    await init_database(
        db_url=settings.get_database_url(),
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
    )
    await init_redis(
        url=settings.get_redis_url(),
        socket_timeout=settings.redis_timeout,
        redis_db=settings.redis_db,
    )
    try:
        count = await _run()
        logger.info("Done. %d tenant(s) backfilled.", count)
    finally:
        await close_redis()
        await close_database()


if __name__ == "__main__":
    asyncio.run(main())
