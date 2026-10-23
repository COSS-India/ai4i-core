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

Updating a category changes only the fields sent; a rename re-caches its
policies, whose cached payload carries the category name. A category can
only be deleted once it has no sub-categories (fk_sub_category_category_id
is ondelete=RESTRICT): the row is locked FOR UPDATE and its sub-categories
counted for a clean 409, and an IntegrityError on that key covers a
sub-category created under it in the meantime.
"""

from typing import List

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError, DuplicateEntityError, EntityNotFoundError
from app.models.policy_management.category import Category
from app.models.policy_management.policy import Policy
from app.models.policy_management.sub_category import SubCategory
from app.schemas.policy_management.category import (
    CategoryCreate,
    CategoryItem,
    CategoryStatusUpdate,
    CategoryUpdate,
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
        await _recache_policies(session, redis, row)

    return CategoryItem.model_validate(row)


async def update_category(
    session: AsyncSession,
    category_id: int,
    body: CategoryUpdate,
    *,
    updated_by: str | None = None,
    redis=None,
) -> CategoryItem:
    row = await session.get(Category, category_id, with_for_update=True)
    if row is None:
        raise EntityNotFoundError(f"Category {category_id}")

    fields = body.model_dump(include=body.model_fields_set)
    renamed = "name" in fields and fields["name"] != row.name
    if renamed:
        existing = await session.execute(
            select(Category.id)
            .where(func.lower(Category.name) == func.lower(body.name), Category.id != category_id)
            .limit(1)
        )
        if existing.first() is not None:
            await session.rollback()  # release the row lock
            raise DuplicateEntityError(f"Category '{body.name}'")

    for field, value in fields.items():
        setattr(row, field, value)
    row.updated_by = updated_by
    row.updated_at = func.now()
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        if "uq_category_name_lower" in str(exc.orig):
            raise DuplicateEntityError(f"Category '{body.name}'")
        raise
    await session.refresh(row)

    if renamed and redis is not None:
        await _recache_policies(session, redis, row)

    return CategoryItem.model_validate(row)


async def delete_category(session: AsyncSession, category_id: int) -> None:
    row = await session.get(Category, category_id, with_for_update=True)
    if row is None:
        raise EntityNotFoundError(f"Category {category_id}")

    count = await session.scalar(
        select(func.count()).select_from(SubCategory).where(SubCategory.category_id == category_id)
    )
    name = row.name  # the row expires on rollback
    if count:
        await session.rollback()  # release the row lock
        raise _in_use_error(name, count)

    # A bulk DELETE, so the ORM never nulls a child's foreign key; the database's
    # RESTRICT rejects the delete if a child was added after the count.
    await session.execute(delete(Category).where(Category.id == category_id))
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        if "fk_sub_category_category_id" in str(exc.orig):
            raise AppError(
                f"Category '{name}' has sub-categories and cannot be deleted.",
                code="ENTITY_IN_USE",
                status_code=409,
            )
        raise


def _in_use_error(name: str, count: int) -> AppError:
    noun = "sub-category" if count == 1 else "sub-categories"
    return AppError(
        f"Category '{name}' has {count} {noun} and cannot be deleted; "
        f"delete or move them first.",
        code="ENTITY_IN_USE",
        status_code=409,
    )


async def _recache_policies(session: AsyncSession, redis, category: Category) -> None:
    """Re-cache every policy under ``category``; their payload carries the
    category's name and status."""
    from app.services.policy_management.policy_cache import cache_policy
    joined = await session.execute(
        select(Policy, SubCategory)
        .join(SubCategory, Policy.sub_category_id == SubCategory.id)
        .where(SubCategory.category_id == category.id)
    )
    for policy, sub_cat in joined.all():
        await cache_policy(policy, session, redis, sub_cat=sub_cat, category=category)
