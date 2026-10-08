"""Policy reads for the policy hierarchy (Category -> SubCategory -> Policy).

A policy is enforced only when it, its sub-category and that sub-category's
category are all active. Toggling a category or sub-category already writes
is_active down to its policies; checking all three flags here as well keeps
enforcement correct for a policy that is enabled on its own later.
"""

from typing import List, Optional

from sqlalchemy import Select, and_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.models.policy_management.category import Category
from app.models.policy_management.policy import Policy
from app.models.policy_management.sub_category import SubCategory


def is_enforced() -> ColumnElement[bool]:
    """SQL condition for an enforced policy. The query must join
    Policy -> SubCategory -> Category (see ``enforced_policies_query``)."""
    return and_(Policy.is_active, SubCategory.is_active, Category.is_active)


def enforced_policies_query(sub_category_id: Optional[int] = None) -> Select:
    """SELECT of the policies currently in force, optionally only those under
    one sub-category."""
    stmt = (
        select(Policy)
        .join(Policy.sub_category)
        .join(SubCategory.category)
        .where(is_enforced())
        .order_by(Policy.id)
    )
    if sub_category_id is not None:
        stmt = stmt.where(Policy.sub_category_id == sub_category_id)
    return stmt


async def list_enforced_policies(
    session: AsyncSession, sub_category_id: Optional[int] = None
) -> List[Policy]:
    result = await session.execute(enforced_policies_query(sub_category_id))
    return list(result.scalars().all())


async def is_policy_enforced(session: AsyncSession, policy_id: int) -> bool:
    """True if the policy exists and it and both its parents are active."""
    result = await session.execute(
        select(Policy.id)
        .join(Policy.sub_category)
        .join(SubCategory.category)
        .where(Policy.id == policy_id, is_enforced())
    )
    return result.first() is not None
