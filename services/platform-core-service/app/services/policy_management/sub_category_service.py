"""Sub-category reads/writes for the policy hierarchy (Category -> SubCategory
-> Policy).

Every sub-category belongs to exactly one category, which must already exist.
Names are unique case-insensitively across all categories, not just within
one (uq_sub_category_name_lower). The pre-insert checks give a clean 404/409;
the IntegrityError fallback covers a concurrent create of the same name.

Disabling a sub-category only flips its own is_active; the parent category
and sibling sub-categories are untouched.
"""

from typing import List, Optional

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import DuplicateEntityError, EntityNotFoundError
from app.models.policy_management.category import Category
from app.models.policy_management.sub_category import SubCategory
from app.schemas.policy_management.sub_category import (
    SubCategoryCreate,
    SubCategoryItem,
    SubCategoryStatusUpdate,
)


async def _ensure_category_exists(session: AsyncSession, category_id: int) -> None:
    result = await session.execute(select(Category.id).where(Category.id == category_id))
    if result.first() is None:
        raise EntityNotFoundError(f"Category {category_id}")


async def list_sub_categories(
    session: AsyncSession, category_id: Optional[int] = None
) -> List[SubCategoryItem]:
    stmt = select(SubCategory).order_by(SubCategory.id)
    if category_id is not None:
        await _ensure_category_exists(session, category_id)
        stmt = stmt.where(SubCategory.category_id == category_id)
    result = await session.execute(stmt)
    return [SubCategoryItem.model_validate(row) for row in result.scalars().all()]


async def create_sub_category(session: AsyncSession, body: SubCategoryCreate) -> SubCategoryItem:
    await _ensure_category_exists(session, body.category_id)

    existing = await session.execute(
        select(SubCategory.id).where(func.lower(SubCategory.name) == body.name.lower()).limit(1)
    )
    if existing.first() is not None:
        raise DuplicateEntityError(f"Sub-category '{body.name}'")

    row = SubCategory(name=body.name, description=body.description, category_id=body.category_id)
    session.add(row)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise DuplicateEntityError(f"Sub-category '{body.name}'")
    await session.refresh(row)
    return SubCategoryItem.model_validate(row)


async def update_sub_category_status(
    session: AsyncSession, sub_category_id: int, body: SubCategoryStatusUpdate
) -> SubCategoryItem:
    row = await session.get(SubCategory, sub_category_id)
    if row is None:
        raise EntityNotFoundError(f"Sub-category {sub_category_id}")
    row.is_active = body.is_active
    await session.commit()
    await session.refresh(row)
    return SubCategoryItem.model_validate(row)
