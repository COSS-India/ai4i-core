"""Category reads/writes for the policy hierarchy (Category -> SubCategory
-> Policy).

Names are unique case-insensitively: the uq_category_name constraint is
case-sensitive, so "PII" vs "pii" is caught here before the insert. The
IntegrityError fallback still covers two concurrent creates of the exact
same name.
"""

from typing import List

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import DuplicateEntityError
from app.models.policy_management.category import Category
from app.schemas.policy_management.category import CategoryCreate, CategoryItem


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
