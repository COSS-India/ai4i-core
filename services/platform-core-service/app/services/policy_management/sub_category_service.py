"""Sub-category reads/writes for the policy hierarchy (Category -> SubCategory
-> Policy).

Every sub-category belongs to exactly one category, which must already exist.
Names are unique case-insensitively across all categories, not just within
one (uq_sub_category_name_lower). The pre-insert checks give a clean 404/409;
an IntegrityError on that index covers a concurrent create of the same name,
and one on the category foreign key a parent removed after the check (404);
any other integrity error is re-raised.

Enabling or disabling a sub-category writes the same is_active to every
policy under it; the parent category and sibling sub-categories are
untouched. A sub-category cannot be enabled while its category is disabled
(409) — enable the category instead.
"""

from typing import List, Optional

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError, DuplicateEntityError, EntityNotFoundError
from app.models.policy_management.category import Category
from app.models.policy_management.policy import Policy
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
        select(SubCategory.id).where(func.lower(SubCategory.name) == func.lower(body.name)).limit(1)
    )
    if existing.first() is not None:
        raise DuplicateEntityError(f"Sub-category '{body.name}'")

    row = SubCategory(name=body.name, description=body.description, category_id=body.category_id)
    session.add(row)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        if "uq_sub_category_name_lower" in str(exc.orig):
            raise DuplicateEntityError(f"Sub-category '{body.name}'")
        if "fk_sub_category_category_id" in str(exc.orig):
            raise EntityNotFoundError(f"Category {body.category_id}")
        raise
    await session.refresh(row)
    return SubCategoryItem.model_validate(row)


async def update_sub_category_status(
    session: AsyncSession, sub_category_id: int, body: SubCategoryStatusUpdate
) -> SubCategoryItem:
    row = await session.get(SubCategory, sub_category_id)
    if row is None:
        raise EntityNotFoundError(f"Sub-category {sub_category_id}")
    if body.is_active:
        category = await session.get(Category, row.category_id)
        if not category.is_active:
            raise AppError(
                f"Category '{category.name}' is disabled; enable it before enabling "
                f"sub-category '{row.name}'.",
                code="CATEGORY_DISABLED",
                status_code=409,
            )
    row.is_active = body.is_active
    await session.execute(
        update(Policy)
        .where(Policy.sub_category_id == sub_category_id)
        .values(is_active=body.is_active)
    )
    await session.commit()
    await session.refresh(row)
    return SubCategoryItem.model_validate(row)
