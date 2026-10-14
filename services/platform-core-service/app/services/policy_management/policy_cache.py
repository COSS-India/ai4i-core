"""Redis cache helpers for policy data."""

import json
import logging

from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.policy_management.category import Category
from app.models.policy_management.policy import Policy
from app.models.policy_management.policy_type import PolicyType
from app.models.policy_management.sub_category import SubCategory

logger = logging.getLogger(__name__)


def policy_cache_key(policy_id: int) -> str:
    return f"policy:{policy_id}"


GLOBAL_POLICY_IDS_KEY = "global:policy_ids"


async def cache_policy(policy: Policy, session: AsyncSession, redis: Redis) -> None:
    """Store full policy data (with sub-category, category, and policy types) in Redis."""
    try:
        sub_cat_result = await session.execute(
            select(SubCategory).where(SubCategory.id == policy.sub_category_id)
        )
        sub_cat = sub_cat_result.scalar_one_or_none()

        category = None
        if sub_cat is not None:
            cat_result = await session.execute(
                select(Category).where(Category.id == sub_cat.category_id)
            )
            category = cat_result.scalar_one_or_none()

        policy_types = []
        if policy.policy_type_id:
            pt_result = await session.execute(
                select(PolicyType).where(PolicyType.id.in_(policy.policy_type_id))
            )
            policy_types = [
                {
                    "id": pt.id,
                    "policy_type": pt.policy_type,
                    "policy_fields": pt.policy_fields or {},
                }
                for pt in pt_result.scalars().all()
            ]

        payload = {
            "id": policy.id,
            "policy_id": policy.policy_id,
            "name": policy.name,
            "description": policy.description,
            "domain": policy.domain,
            "guardrail_scope": (
                policy.guardrail_scope.value
                if hasattr(policy.guardrail_scope, "value")
                else policy.guardrail_scope
            ),
            "is_global": policy.is_global,
            "is_active": policy.is_active,
            "policy_types": policy_types,
            "sub_category": (
                {
                    "id": sub_cat.id,
                    "name": sub_cat.name,
                    "is_active": sub_cat.is_active,
                }
                if sub_cat is not None
                else None
            ),
            "category": (
                {
                    "id": category.id,
                    "name": category.name,
                    "is_active": category.is_active,
                }
                if category is not None
                else None
            ),
        }

        await redis.set(
            policy_cache_key(policy.id),
            json.dumps(payload),
            ex=settings.policy_cache_ttl_seconds,
        )
        logger.debug("Cached policy id=%s", policy.id)
    except Exception:
        logger.warning("Failed to cache policy id=%s", policy.id, exc_info=True)
        await delete_policy_cache(policy.id, redis)
        return

    try:
        if policy.is_global:
            await redis.sadd(GLOBAL_POLICY_IDS_KEY, policy.id)
        else:
            await redis.srem(GLOBAL_POLICY_IDS_KEY, policy.id)
    except Exception:
        logger.warning("Failed to update global policy index for id=%s", policy.id, exc_info=True)


async def delete_policy_cache(policy_id: int, redis: Redis) -> None:
    """Remove a policy entry from the Redis cache and global index."""
    try:
        await redis.delete(policy_cache_key(policy_id))
        logger.debug("Evicted cache for policy id=%s", policy_id)
    except Exception:
        logger.warning("Failed to evict cache for policy id=%s", policy_id, exc_info=True)
    try:
        await redis.srem(GLOBAL_POLICY_IDS_KEY, policy_id)
    except Exception:
        logger.warning("Failed to remove policy id=%s from global index", policy_id, exc_info=True)
