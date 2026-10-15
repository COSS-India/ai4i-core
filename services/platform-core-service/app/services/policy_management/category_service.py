"""Category reads/writes for the policy hierarchy (Category -> SubCategory
-> Policy).

Names are unique case-insensitively (uq_category_name_lower). The
pre-insert check gives a clean 409; an IntegrityError on that index covers two
concurrent creates of the same name.

Enabling or disabling a category changes only the category row; its
sub-categories and policies keep their own is_active, so whatever was
disabled on its own is still disabled after the category is re-enabled.
A sub-category or policy is in effect only when its own flag and every
ancestor's flag are true. Nothing is deleted. The category row is locked
FOR UPDATE so a concurrent sub-category enable (which locks the same row)
waits. A request for the state the category is already in changes nothing.
"""

from typing import List

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import DuplicateEntityError, EntityNotFoundError
from app.models.policy_management.category import Category
from app.models.policy_management.policy import Policy
from app.models.policy_management.sub_category import SubCategory
from app.schemas.policy_management.category import (
    CategoryCreate,
    CategoryItem,
    CategoryStatusUpdate,
)


async def list_categories(session: AsyncSession) -> List[CategoryItem]:
    result = await session.execute(select(Category).order_by(Category.id))
    return [CategoryItem.model_validate(row) for row in result.scalars().all()]


async def create_category(
    session: AsyncSession, body: CategoryCreate, *, created_by: str | None = None
) -> CategoryItem:
    existing = await session.execute(
        select(Category.id).where(func.lower(Category.name) == func.lower(body.name)).limit(1)
    )
    if existing.first() is not None:
        raise DuplicateEntityError(f"Category '{body.name}'")

    row = Category(name=body.name, description=body.description, created_by=created_by)
    session.add(row)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        if "uq_category_name_lower" in str(exc.orig):
            raise DuplicateEntityError(f"Category '{body.name}'")
        raise
    await session.refresh(row)
    return CategoryItem.model_validate(row)


async def update_category_status(
    session: AsyncSession,
    category_id: int,
    body: CategoryStatusUpdate,
    *,
    updated_by: str | None = None,
    redis=None,
) -> CategoryItem:
    row = await session.get(Category, category_id, with_for_update=True)
    if row is None:
        raise EntityNotFoundError(f"Category {category_id}")
    if row.is_active == body.is_active:
        item = CategoryItem.model_validate(row)
        await session.rollback()  # release the row lock
        return item
    row.is_active = body.is_active
    row.updated_by = updated_by
    await session.commit()
    await session.refresh(row)

    if redis is not None:
        from app.services.policy_management.policy_cache import cache_policy
        sub_cat_result = await session.execute(
            select(SubCategory.id).where(SubCategory.category_id == category_id)
        )
        sub_cat_ids = [r[0] for r in sub_cat_result.all()]
        if sub_cat_ids:
            policy_result = await session.execute(
                select(Policy).where(Policy.sub_category_id.in_(sub_cat_ids))
            )
            for policy in policy_result.scalars().all():
                await cache_policy(policy, session, redis)

    return CategoryItem.model_validate(row)
