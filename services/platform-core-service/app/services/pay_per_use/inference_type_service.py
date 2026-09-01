"""CRUD for the ``inference_types`` catalogue.

The DB is the source of truth; ``inference_type_cache`` is rebuilt after every
committed mutation (never before — a cache that leads the DB can serve an id
for a row that was rolled back).
"""

import logging
from typing import Any, Dict, List, Optional

from fastapi import HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.pay_per_use.inference_type import InferenceType
from app.models.pay_per_use.quota_usage import QuotaUsage
from app.models.pay_per_use.tier import TierQuota
from app.schemas.inference_types import InferenceTypeCreate, InferenceTypeItem, InferenceTypeUpdate
from app.services.pay_per_use import inference_type_cache

logger = logging.getLogger(__name__)


def _row_to_dict(row: InferenceType) -> Dict[str, Any]:
    return {
        "id": row.id,
        "name": row.name,
        "endpoint_patterns": list(row.endpoint_patterns or []),
        "unit": row.unit,
        "pricing": row.pricing,
    }


def _to_item(entry: Dict[str, Any]) -> InferenceTypeItem:
    """Project the stored ``endpoint_patterns`` array onto the legacy
    scalar-plus-aliases response shape. See InferenceTypeItem's docstring."""
    patterns = list(entry.get("endpoint_patterns") or [])
    aliases = patterns[1:]
    return InferenceTypeItem(
        id=entry["id"],
        name=entry["name"],
        endpoint_pattern=patterns[0] if patterns else "",
        endpoint_aliases=aliases or None,
        unit=entry["unit"],
        pricing=entry["pricing"],
    )


async def list_inference_types(session: AsyncSession) -> List[InferenceTypeItem]:
    entries = await inference_type_cache.get_all(session)
    return [_to_item(e) for e in entries]


async def get_inference_type(session: AsyncSession, name: str) -> InferenceTypeItem:
    entry = await inference_type_cache.get_by_name(session, name)
    if entry is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Inference type '{name}' not found",
        )
    return _to_item(entry)


async def _referencing_tables(session: AsyncSession, type_id: int, name: str) -> List[str]:
    """Tables holding rows that point at this inference type.

    Checks ``inference_name`` as well as ``inference_type_id`` because phase 1
    ids are nullable: a row predating the backfill, or one the backfill could
    not resolve, references the type by string only and would otherwise slip
    past the guard.
    """
    tables = []
    for table, model in (("tier_quotas", TierQuota), ("quota_usage", QuotaUsage)):
        stmt = select(model.id).where(
            or_(
                model.inference_type_id == type_id,
                func.lower(model.inference_name) == name,
            )
        ).limit(1)
        result = await session.execute(stmt)
        if result.first() is not None:
            tables.append(table)
    return tables



async def create_inference_type(
    body: InferenceTypeCreate, session: AsyncSession, created_by: Optional[str] = None
) -> InferenceTypeItem:
    row = InferenceType(
        name=body.name,
        endpoint_patterns=body.endpoint_patterns,
        unit=body.unit,
        pricing=body.pricing,
        created_by=created_by,
        updated_by=created_by,
    )
    session.add(row)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Inference type '{body.name}' already exists",
        )
    await session.refresh(row)

    await inference_type_cache.rebuild(session)
    return _to_item(_row_to_dict(row))


async def update_inference_type(
    name: str,
    body: InferenceTypeUpdate,
    session: AsyncSession,
    updated_by: Optional[str] = None,
) -> InferenceTypeItem:
    normalized = name.lower()
    result = await session.execute(
        select(InferenceType).where(InferenceType.name == normalized)
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Inference type '{name}' not found",
        )

    # A rename orphans every tier_quotas/quota_usage row that still references
    # this type by string, so it is guarded exactly like a delete.
    if body.name is not None and body.name != row.name:
        referencing = await _referencing_tables(session, row.id, row.name)
        if referencing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"Cannot rename inference type '{row.name}': referenced by "
                    f"{', '.join(referencing)}"
                ),
            )
        row.name = body.name

    if body.endpoint_patterns is not None:
        row.endpoint_patterns = body.endpoint_patterns
    if body.unit is not None:
        row.unit = body.unit
    if body.pricing is not None:
        row.pricing = body.pricing
    row.updated_by = updated_by

    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Inference type '{body.name}' already exists",
        )
    await session.refresh(row)

    await inference_type_cache.rebuild(session)
    return _to_item(_row_to_dict(row))


async def delete_inference_type(name: str, session: AsyncSession) -> None:
    normalized = name.lower()
    result = await session.execute(
        select(InferenceType).where(InferenceType.name == normalized)
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Inference type '{name}' not found",
        )

    referencing = await _referencing_tables(session, row.id, row.name)
    if referencing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Cannot delete inference type '{row.name}': referenced by "
                f"{', '.join(referencing)}"
            ),
        )

    await session.delete(row)
    await session.commit()
    await inference_type_cache.rebuild(session)
