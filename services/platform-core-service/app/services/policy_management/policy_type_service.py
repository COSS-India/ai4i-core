"""policy_type reads/writes for the policy hierarchy.

policy_type names are unique (uq_policy_type_policy_type). The pre-insert/
pre-update check gives a clean 409; an IntegrityError on that constraint
covers concurrent creates of the same name.
"""

from typing import List

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import DuplicateEntityError, EntityInUseError, EntityNotFoundError
from app.repositories.policy_management.policy_type_repository import PolicyTypeRepository
from app.schemas.policy_management.policy_type import (
    PolicyTypeCreate,
    PolicyTypeItem,
    PolicyTypeUpdate,
)


def _matches_entity(policy_fields: dict, search: str) -> bool:
    term = search.strip().lower()
    for entry in policy_fields.get("custom_field") or []:
        if term in str(entry.get("entity_name", "")).lower():
            return True
    for entry in policy_fields.get("model_supported_field") or []:
        for entities in entry.values():
            for e in entities:
                if term in str(e.get("entity_name", "")).lower():
                    return True
    return False


async def list_policy_types(session: AsyncSession, entity: str | None = None) -> List[PolicyTypeItem]:
    repo = PolicyTypeRepository(session)
    rows = await repo.get_all()
    items = [PolicyTypeItem.model_validate(row) for row in rows]
    if entity:
        items = [item for item in items if _matches_entity(item.policy_fields, entity)]
    return items


async def get_policy_type(session: AsyncSession, policy_type_id: int) -> PolicyTypeItem:
    repo = PolicyTypeRepository(session)
    row = await repo.get_by_id(policy_type_id)
    if row is None:
        raise EntityNotFoundError(f"PolicyType {policy_type_id}")
    return PolicyTypeItem.model_validate(row)


async def create_policy_type(session: AsyncSession, body: PolicyTypeCreate, created_by: str | None = None) -> PolicyTypeItem:
    repo = PolicyTypeRepository(session)
    if await repo.get_by_name(body.policy_type) is not None:
        raise DuplicateEntityError(f"PolicyType '{body.policy_type}'")
    try:
        row = await repo.create(policy_type=body.policy_type, policy_fields=body.policy_fields, created_by=created_by)
    except IntegrityError as exc:
        await session.rollback()
        if "uq_policy_type_policy_type" in str(exc.orig):
            raise DuplicateEntityError(f"PolicyType '{body.policy_type}'")
        raise
    return PolicyTypeItem.model_validate(row)


async def update_policy_type(
    session: AsyncSession, policy_type_id: int, body: PolicyTypeUpdate, updated_by: str | None = None, redis=None
) -> PolicyTypeItem:
    repo = PolicyTypeRepository(session)
    existing = await repo.get_by_id(policy_type_id)
    if existing is None:
        raise EntityNotFoundError(f"PolicyType {policy_type_id}")

    data = body.model_dump(exclude_none=True, exclude={"policy_type_id"})
    if updated_by is not None:
        data["updated_by"] = updated_by
    if not data:
        return PolicyTypeItem.model_validate(existing)

    row = await repo.update(policy_type_id, data)

    if redis is not None:
        from sqlalchemy import select, text
        from app.models.policy_management.policy import Policy
        from app.services.policy_management.policy_cache import cache_policy

        affected = await session.execute(
            select(Policy).where(text(":id = ANY(policy_type_id)")).params(id=policy_type_id)
        )
        for policy in affected.scalars().all():
            await cache_policy(policy, session, redis)

    return PolicyTypeItem.model_validate(row)


async def delete_policy_type(session: AsyncSession, policy_type_id: int) -> int:
    repo = PolicyTypeRepository(session)
    if await repo.get_by_id(policy_type_id) is None:
        raise EntityNotFoundError(f"PolicyType {policy_type_id}")
    if await repo.is_referenced_by_policy(policy_type_id):
        raise EntityInUseError(f"PolicyType {policy_type_id}")
    await repo.delete(policy_type_id)
    return policy_type_id
