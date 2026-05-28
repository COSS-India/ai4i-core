from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import List
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import delete, desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.pay_per_use.quota_config import QuotaConfig, QuotaServiceLimit
from app.schemas.pay_per_use.billing import QuotaConfigCreate, QuotaConfigOut, QuotaConfigUpdate
from app.utils.billing import quota_to_out

logger = logging.getLogger("quota-config-service")


async def create_quota_config(body: QuotaConfigCreate, session: AsyncSession) -> QuotaConfigOut:
    row = QuotaConfig(name=body.name.strip(), requests_per_hour=body.requests_per_hour)
    session.add(row)
    await session.flush()
    for sl in body.service_limits:
        session.add(QuotaServiceLimit(
            quota_config_id=row.id,
            service_type=sl.service_type.strip(),
            unit_type=sl.unit_type.strip(),
            limit_value=sl.limit_value,
        ))
    try:
        await session.commit()
    except Exception as e:
        await session.rollback()
        logger.exception("create_quota_config: %s", e)
        raise HTTPException(status_code=409, detail="Could not create quota config (duplicate name?)") from e
    await session.refresh(row)
    q2 = await session.scalar(
        select(QuotaConfig)
        .options(selectinload(QuotaConfig.service_limit_rows))
        .where(QuotaConfig.id == row.id)
    )
    return quota_to_out(q2 or row)


async def list_quota_configs(session: AsyncSession) -> List[QuotaConfigOut]:
    r = await session.execute(
        select(QuotaConfig)
        .options(selectinload(QuotaConfig.service_limit_rows))
        .order_by(desc(QuotaConfig.created_at))
    )
    return [quota_to_out(x) for x in r.scalars().all()]


async def get_quota_config_by_name(name: str, session: AsyncSession) -> QuotaConfigOut:
    row = await session.scalar(
        select(QuotaConfig)
        .options(selectinload(QuotaConfig.service_limit_rows))
        .where(QuotaConfig.name == name.strip())
    )
    if not row:
        raise HTTPException(status_code=404, detail="Quota config not found")
    return quota_to_out(row)


async def get_quota_config_by_id(config_id: UUID, session: AsyncSession) -> QuotaConfigOut:
    row = await session.scalar(
        select(QuotaConfig)
        .options(selectinload(QuotaConfig.service_limit_rows))
        .where(QuotaConfig.id == config_id)
    )
    if not row:
        raise HTTPException(status_code=404, detail="Quota config not found")
    return quota_to_out(row)


async def update_quota_config(
    config_id: UUID, body: QuotaConfigUpdate, session: AsyncSession
) -> QuotaConfigOut:
    row = await session.scalar(
        select(QuotaConfig)
        .options(selectinload(QuotaConfig.service_limit_rows))
        .where(QuotaConfig.id == config_id)
    )
    if not row:
        raise HTTPException(status_code=404, detail="Quota config not found")
    if body.name is not None:
        row.name = body.name.strip()
    if body.requests_per_hour is not None:
        row.requests_per_hour = body.requests_per_hour
    if body.service_limits is not None:
        await session.execute(
            delete(QuotaServiceLimit).where(QuotaServiceLimit.quota_config_id == row.id)
        )
        for sl in body.service_limits:
            session.add(QuotaServiceLimit(
                quota_config_id=row.id,
                service_type=sl.service_type.strip(),
                unit_type=sl.unit_type.strip(),
                limit_value=sl.limit_value,
            ))
    row.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
    try:
        await session.commit()
    except Exception as e:
        await session.rollback()
        raise HTTPException(status_code=409, detail="Update conflict (duplicate name?)") from e
    q2 = await session.scalar(
        select(QuotaConfig)
        .options(selectinload(QuotaConfig.service_limit_rows))
        .where(QuotaConfig.id == row.id)
    )
    return quota_to_out(q2 or row)


async def delete_quota_config(config_id: UUID, session: AsyncSession) -> None:
    row = await session.get(QuotaConfig, config_id)
    if not row:
        raise HTTPException(status_code=404, detail="Quota config not found")
    await session.delete(row)
    await session.commit()
