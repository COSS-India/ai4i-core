"""Category reads/writes for the policy hierarchy (Category -> SubCategory
-> Policy).

Names are unique case-insensitively (uq_category_name_lower). The
pre-insert check gives a clean 409; the IntegrityError fallback covers two
concurrent creates of the same name.

Disabling a category only flips its own is_active; its sub-categories keep
their flags, so re-enabling restores them as they were. Enforcement must
treat a sub-category as disabled whenever its parent category is.
"""

from typing import List

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import DuplicateEntityError, EntityNotFoundError
from app.models.policy_management.category import Category
from app.schemas.policy_management.category import (
    CategoryCreate,
    CategoryItem,
    CategoryStatusUpdate,
)


async def list_categories(session: AsyncSession) -> List[CategoryItem]:
    result = await session.execute(select(Category).order_by(Category.id))
    return [CategoryItem.model_validate(row) for row in result.scalars().all()]


async def create_category(session: AsyncSession, body: CategoryCreate) -> CategoryItem:
    existing = await session.execute(
        select(Category.id).where(func.lower(Category.name) == body.name.lower()).limit(1)
    )
    if existing.first() is not None:
        raise DuplicateEntityError(f"Category '{body.name}'")

    row = Category(name=body.name, description=body.description)
    session.add(row)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise DuplicateEntityError(f"Category '{body.name}'")
    await session.refresh(row)
    return CategoryItem.model_validate(row)


async def update_category_status(
    session: AsyncSession, category_id: int, body: CategoryStatusUpdate
) -> CategoryItem:
    row = await session.get(Category, category_id)
    if row is None:
        raise EntityNotFoundError(f"Category {category_id}")
    row.is_active = body.is_active
    await session.commit()
    await session.refresh(row)
    return CategoryItem.model_validate(row)
