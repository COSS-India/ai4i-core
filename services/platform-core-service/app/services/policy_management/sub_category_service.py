"""Sub-category reads/writes for the policy hierarchy (Category -> SubCategory
-> Policy).

Every sub-category belongs to exactly one category, which must already exist.
Names are unique case-insensitively across all categories, not just within
one (uq_sub_category_name_lower). The pre-insert checks give a clean 404/409;
an IntegrityError on that index covers a concurrent create of the same name,
and one on the category foreign key a parent removed after the check (404);
any other integrity error is re-raised.

Enabling or disabling a sub-category changes only the sub-category row; its
policies keep their own is_active, and the parent category and sibling
sub-categories are untouched. A policy is in effect only when its own flag
and every ancestor's flag are true. A sub-category cannot be enabled while
its category is disabled (409) — enable the category instead. The parent
category row is locked FOR UPDATE, the same lock a category toggle and any
other toggle of this sub-category take, and the sub-category is re-read once
the lock is held, so neither the check nor the no-op test works on a stale
row. A request for the state the sub-category is already in changes nothing.

Updating a sub-category changes only the fields sent; a new category_id
moves it, with its policies, under that category (404 if it does not
exist). For the same reason a toggle refuses to enable it under a disabled
category, an enabled sub-category can't be moved under one (409). A move
locks the current and target category rows, then the sub-category, in the
order a toggle takes them, so neither sees the other's half-done change. A
rename or move re-caches its policies, whose cached payload carries the
sub-category and category names. A sub-category can only be deleted once no
policy references it (fk_policy_sub_category_id is ondelete=RESTRICT): the
row is locked FOR UPDATE and its policies counted for a clean 409, and an
IntegrityError on that key covers a policy created under it in the meantime.
"""

from typing import List, Optional

from sqlalchemy import delete, func, select
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
    SubCategoryUpdate,
)
from app.services.policy_management.errors import in_use_error


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


async def create_sub_category(
    session: AsyncSession, body: SubCategoryCreate, *, created_by: str | None = None
) -> SubCategoryItem:
    await _ensure_category_exists(session, body.category_id)

    existing = await session.execute(
        select(SubCategory.id).where(func.lower(SubCategory.name) == func.lower(body.name)).limit(1)
    )
    if existing.first() is not None:
        raise DuplicateEntityError(f"Sub-category '{body.name}'")

    row = SubCategory(
        name=body.name, description=body.description, category_id=body.category_id, created_by=created_by
    )
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
    session: AsyncSession,
    sub_category_id: int,
    body: SubCategoryStatusUpdate,
    *,
    updated_by: str | None = None,
    redis=None,
) -> SubCategoryItem:
    row = await session.get(SubCategory, sub_category_id)
    if row is None:
        raise EntityNotFoundError(f"Sub-category {sub_category_id}")
    category = await session.get(Category, row.category_id, with_for_update=True)
    await session.refresh(row)  # read after the lock, not before it
    if body.is_active and not category.is_active:
        raise AppError(
            f"Category '{category.name}' is disabled; enable it before enabling "
            f"sub-category '{row.name}'.",
            code="CATEGORY_DISABLED",
            status_code=409,
        )
    if row.is_active == body.is_active:
        item = SubCategoryItem.model_validate(row)
        await session.rollback()  # release the category row lock
        return item
    row.is_active = body.is_active
    row.updated_by = updated_by
    await session.commit()
    await session.refresh(row)

    if redis is not None:
        from app.services.policy_management.policy_cache import cache_policy
        result = await session.execute(
            select(Policy).where(Policy.sub_category_id == sub_category_id)
        )
        for policy in result.scalars().all():
            await cache_policy(policy, session, redis)

    return SubCategoryItem.model_validate(row)


async def update_sub_category(
    session: AsyncSession,
    sub_category_id: int,
    body: SubCategoryUpdate,
    *,
    updated_by: str | None = None,
    redis=None,
) -> SubCategoryItem:
    fields = body.model_dump(include=body.model_fields_set)
    target: Optional[Category] = None
    if "category_id" in fields:
        row, target = await _lock_for_move(session, sub_category_id, body.category_id)
    else:
        row = await session.get(SubCategory, sub_category_id, with_for_update=True)
        if row is None:
            raise EntityNotFoundError(f"Sub-category {sub_category_id}")

    renamed = "name" in fields and fields["name"] != row.name
    moved = target is not None and target.id != row.category_id
    try:
        if moved and row.is_active and not target.is_active:
            raise AppError(
                f"Category '{target.name}' is disabled; disable sub-category "
                f"'{row.name}' before moving it there.",
                code="CATEGORY_DISABLED",
                status_code=409,
            )
        if renamed:
            existing = await session.execute(
                select(SubCategory.id)
                .where(
                    func.lower(SubCategory.name) == func.lower(body.name),
                    SubCategory.id != sub_category_id,
                )
                .limit(1)
            )
            if existing.first() is not None:
                raise DuplicateEntityError(f"Sub-category '{body.name}'")
    except AppError:
        await session.rollback()  # release the row locks
        raise

    for field, value in fields.items():
        setattr(row, field, value)
    row.updated_by = updated_by  # updated_at is set by the column's onupdate
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        if "uq_sub_category_name_lower" in str(exc.orig):
            raise DuplicateEntityError(f"Sub-category '{body.name}'")
        raise
    await session.refresh(row)

    if (renamed or moved) and redis is not None:
        from app.services.policy_management.policy_cache import recache_policies
        category = target if moved else await session.get(Category, row.category_id)
        await recache_policies(session, redis, category, sub_category=row)

    return SubCategoryItem.model_validate(row)


async def _lock_for_move(
    session: AsyncSession, sub_category_id: int, target_id: int
) -> tuple[SubCategory, Category]:
    """Lock the sub-category's current and target categories (in id order, so
    two moves can't deadlock), then the sub-category: categories first, as a
    status toggle does. If another move changed the parent before the lock was
    held, start again with the new parent. 404 if either row is missing."""
    row = await session.get(SubCategory, sub_category_id)
    if row is None:
        raise EntityNotFoundError(f"Sub-category {sub_category_id}")
    while True:
        parent_id = row.category_id
        result = await session.execute(
            select(Category)
            .where(Category.id.in_({parent_id, target_id}))
            .order_by(Category.id)
            .with_for_update()
        )
        locked = {c.id: c for c in result.scalars().all()}
        await session.refresh(row, with_for_update=True)
        if row.category_id == parent_id:
            break
        await session.rollback()
        await session.refresh(row)
    if target_id not in locked:
        await session.rollback()
        raise EntityNotFoundError(f"Category {target_id}")
    return row, locked[target_id]


async def delete_sub_category(session: AsyncSession, sub_category_id: int) -> None:
    row = await session.get(SubCategory, sub_category_id, with_for_update=True)
    if row is None:
        raise EntityNotFoundError(f"Sub-category {sub_category_id}")

    count = await session.scalar(
        select(func.count()).select_from(Policy).where(Policy.sub_category_id == sub_category_id)
    )
    entity = f"Sub-category '{row.name}'"  # the row expires on rollback
    if count:
        await session.rollback()  # release the row lock
        raise in_use_error(entity, count, "policy", "policies")

    # A bulk DELETE, so the ORM never nulls a policy's foreign key. RESTRICT is
    # checked when the statement runs, not at commit, so both are guarded.
    try:
        await session.execute(delete(SubCategory).where(SubCategory.id == sub_category_id))
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        if "fk_policy_sub_category_id" in str(exc.orig):
            raise in_use_error(entity, None, "policy", "policies")
        raise
