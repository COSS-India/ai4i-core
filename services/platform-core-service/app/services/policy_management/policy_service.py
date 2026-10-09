"""Policy reads/writes for the policy management domain.

policy.name is unique (case-insensitive, uq_policy_name_lower) and
policy.policy_id is unique (uq_policy_policy_id). The pre-insert/pre-update
check gives a clean 409; an IntegrityError on those constraints covers
concurrent creates of the same name.
"""

from typing import List, Optional, Tuple

from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError, DuplicateEntityError, EntityNotFoundError
from app.repositories.policy_management.policy_repository import PolicyRepository
from app.schemas.policy_management.policy import PolicyCreate, PolicyItem, PolicyUpdate


async def _assert_policy_types_exist(session: AsyncSession, ids: List[int]) -> None:
    from app.models.policy_management.policy_type import PolicyType

    result = await session.execute(select(PolicyType.id).where(PolicyType.id.in_(ids)))
    found = {row[0] for row in result.all()}
    missing = sorted(set(ids) - found)
    if missing:
        raise EntityNotFoundError(f"PolicyType {missing}")


async def list_policies(
    session: AsyncSession,
    name: Optional[str] = None,
    sub_category_id: Optional[int] = None,
    offset: int = 0,
    limit: int = 100,
) -> Tuple[List[PolicyItem], int]:
    from app.models.policy_management.sub_category import SubCategory
    from sqlalchemy import select as _select

    if sub_category_id is not None:
        result = await session.execute(
            _select(SubCategory.id).where(SubCategory.id == sub_category_id)
        )
        if result.first() is None:
            raise EntityNotFoundError(f"SubCategory {sub_category_id}")

    repo = PolicyRepository(session)
    rows, total = await repo.get_all(name=name, sub_category_id=sub_category_id, offset=offset, limit=limit)
    return [PolicyItem.model_validate(row) for row in rows], total


async def get_policy(session: AsyncSession, policy_id: int) -> PolicyItem:
    repo = PolicyRepository(session)
    row = await repo.get_by_id(policy_id)
    if row is None:
        raise EntityNotFoundError(f"Policy {policy_id}")
    return PolicyItem.model_validate(row)


async def create_policy(
    session: AsyncSession, body: PolicyCreate, created_by: str | None = None
) -> PolicyItem:
    repo = PolicyRepository(session)
    if await repo.get_by_name(body.name) is not None:
        raise DuplicateEntityError(f"Policy '{body.name}'")

    await _assert_policy_types_exist(session, body.policy_type_id)

    policy_id_str = await repo.get_next_policy_id()
    data = body.model_dump()
    data["policy_id"] = policy_id_str
    if created_by is not None:
        data["created_by"] = created_by

    try:
        row = await repo.create(data)
    except IntegrityError as exc:
        await session.rollback()
        orig = str(exc.orig)
        if "uq_policy_name_lower" in orig:
            raise DuplicateEntityError(f"Policy '{body.name}'")
        if "uq_policy_policy_id" in orig:
            raise DuplicateEntityError(f"Policy ID '{policy_id_str}'")
        if "fk_policy_sub_category_id" in orig:
            raise EntityNotFoundError(f"SubCategory {body.sub_category_id}")
        raise
    return PolicyItem.model_validate(row)


async def update_policy(
    session: AsyncSession, policy_id: int, body: PolicyUpdate, updated_by: str | None = None
) -> PolicyItem:
    repo = PolicyRepository(session)
    existing = await repo.get_by_id(policy_id)
    if existing is None:
        raise EntityNotFoundError(f"Policy {policy_id}")

    data = body.model_dump(exclude_none=True, exclude={"id"})
    if updated_by is not None:
        data["updated_by"] = updated_by
    if not data:
        return PolicyItem.model_validate(existing)

    if body.policy_type_id is not None:
        await _assert_policy_types_exist(session, body.policy_type_id)

    try:
        row = await repo.update(policy_id, data)
    except IntegrityError as exc:
        await session.rollback()
        orig = str(exc.orig)
        if "fk_policy_sub_category_id" in orig:
            raise EntityNotFoundError(f"SubCategory {data.get('sub_category_id')}")
        raise
    return PolicyItem.model_validate(row)


async def delete_policy(
    session: AsyncSession,
    policy_id: int,
    auth_db: Optional[AsyncSession] = None,
) -> int:
    repo = PolicyRepository(session)
    existing = await repo.get_by_id(policy_id)
    if existing is None:
        raise EntityNotFoundError(f"Policy {policy_id}")

    if not existing.is_active:
        raise AppError(
            message=f"Policy {policy_id} is not active and cannot be deleted.",
            code="POLICY_NOT_ACTIVE",
            status_code=409,
        )

    if auth_db is not None:
        result = await auth_db.execute(
            text("SELECT 1 FROM applications WHERE :pid = ANY(policy_id) LIMIT 1"),
            {"pid": policy_id},
        )
        if result.first() is not None:
            raise AppError(
                message=f"Policy {policy_id} is linked to one or more applications and cannot be deleted.",
                code="ENTITY_IN_USE",
                status_code=409,
            )

    await repo.delete(policy_id)
    return policy_id
