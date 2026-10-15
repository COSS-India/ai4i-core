"""policy_type reads/writes for the policy hierarchy."""

from typing import List

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import EntityInUseError, EntityNotFoundError
from app.repositories.policy_management.policy_type_repository import PolicyTypeRepository
from app.schemas.policy_management.policy_type import (
    PolicyTypeCreate,
    PolicyTypeItem,
    PolicyTypeUpdate,
)


def _filter_policy_fields(policy_fields: dict, search: str) -> dict | None:
    term = search.strip().lower()

    filtered_custom = [
        entry for entry in (policy_fields.get("custom_field") or [])
        if term in str(entry.get("entity_name", "")).lower()
    ]

    filtered_model = []
    for entry in (policy_fields.get("model_supported_field") or []):
        narrowed = {
            lang: [e for e in entities if term in str(e.get("entity_name", "")).lower()]
            for lang, entities in entry.items()
        }
        narrowed = {lang: ents for lang, ents in narrowed.items() if ents}
        if narrowed:
            filtered_model.append(narrowed)

    if not filtered_custom and not filtered_model:
        return None

    result = {}
    if filtered_custom:
        result["custom_field"] = filtered_custom
    if filtered_model:
        result["model_supported_field"] = filtered_model
    return result


async def list_policy_types(session: AsyncSession, entity: str | None = None) -> List[PolicyTypeItem]:
    repo = PolicyTypeRepository(session)
    rows = await repo.get_all()
    items = [PolicyTypeItem.model_validate(row) for row in rows]
    if entity:
        narrowed = []
        for item in items:
            filtered = _filter_policy_fields(item.policy_fields, entity)
            if filtered is not None:
                narrowed.append(item.model_copy(update={"policy_fields": filtered}))
        items = narrowed
    return items


async def get_policy_type(session: AsyncSession, policy_type_id: int) -> PolicyTypeItem:
    repo = PolicyTypeRepository(session)
    row = await repo.get_by_id(policy_type_id)
    if row is None:
        raise EntityNotFoundError(f"PolicyType {policy_type_id}")
    return PolicyTypeItem.model_validate(row)


async def create_policy_type(session: AsyncSession, body: PolicyTypeCreate, created_by: str | None = None) -> PolicyTypeItem:
    repo = PolicyTypeRepository(session)
    row = await repo.create(policy_type=body.policy_type, policy_fields=body.policy_fields, created_by=created_by)
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
