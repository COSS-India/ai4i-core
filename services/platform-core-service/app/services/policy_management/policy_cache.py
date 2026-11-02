"""Redis cache helpers for policy data."""

import json
import logging
from typing import Optional

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


async def cache_policy(
    policy: Policy,
    session: AsyncSession,
    redis: Redis,
    *,
    sub_cat: Optional[SubCategory] = None,
    category: Optional[Category] = None,
) -> Optional[dict]:
    """Store full policy data (with sub-category, category, and policy types) in Redis.

    Pass pre-loaded ``sub_cat`` and ``category`` to avoid redundant DB round-trips
    when caching many policies that share the same ancestors.

    Returns the cached payload dict on success, or None when caching fails.
    """
    try:
        if sub_cat is None:
            sub_cat_result = await session.execute(
                select(SubCategory).where(SubCategory.id == policy.sub_category_id)
            )
            sub_cat = sub_cat_result.scalar_one_or_none()

        if category is None and sub_cat is not None:
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
        return None

    try:
        if policy.is_global:
            await redis.sadd(GLOBAL_POLICY_IDS_KEY, policy.id)
        else:
            await redis.srem(GLOBAL_POLICY_IDS_KEY, policy.id)
    except Exception:
        logger.warning("Failed to update global policy index for id=%s", policy.id, exc_info=True)

    return payload


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


async def recache_policies(
    session: AsyncSession,
    redis: Redis,
    category: Category,
    sub_category: Optional[SubCategory] = None,
) -> None:
    """Re-cache every policy under ``category``, or only those under
    ``sub_category`` when given, after a change to an ancestor their cached
    payload carries (a name, a status or the sub-category's parent)."""
    stmt = select(Policy, SubCategory).join(SubCategory, Policy.sub_category_id == SubCategory.id)
    if sub_category is not None:
        stmt = stmt.where(SubCategory.id == sub_category.id)
    else:
        stmt = stmt.where(SubCategory.category_id == category.id)
    joined = await session.execute(stmt)
    for policy, sub_cat in joined.all():
        await cache_policy(policy, session, redis, sub_cat=sub_cat, category=category)
