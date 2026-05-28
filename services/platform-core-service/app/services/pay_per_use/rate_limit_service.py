from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import List
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.pay_per_use.rate_limit_config import RateLimitConfig
from app.schemas.pay_per_use.billing import RateLimitConfigCreate, RateLimitConfigOut, RateLimitConfigUpdate

logger = logging.getLogger("rate-limit-service")


async def create_rate_limit_config(
    body: RateLimitConfigCreate, session: AsyncSession
) -> RateLimitConfigOut:
    row = RateLimitConfig(
        name=body.name.strip(),
        requests_per_hour_per_api_key=body.requests_per_hour_per_api_key,
        requests_per_hour_per_tenant=body.requests_per_hour_per_tenant,
    )
    session.add(row)
    try:
        await session.commit()
    except Exception as e:
        await session.rollback()
        logger.exception("create_rate_limit_config: %s", e)
        raise HTTPException(
            status_code=409, detail="Could not create rate limit config (duplicate name?)"
        ) from e
    await session.refresh(row)
    return row


async def list_rate_limit_configs(session: AsyncSession) -> List[RateLimitConfigOut]:
    r = await session.execute(select(RateLimitConfig).order_by(desc(RateLimitConfig.created_at)))
    return list(r.scalars().all())


async def get_rate_limit_config_by_name(name: str, session: AsyncSession) -> RateLimitConfigOut:
    row = await session.scalar(
        select(RateLimitConfig).where(RateLimitConfig.name == name.strip())
    )
    if not row:
        raise HTTPException(status_code=404, detail="Rate limit config not found")
    return row


async def get_rate_limit_config_by_id(config_id: UUID, session: AsyncSession) -> RateLimitConfigOut:
    row = await session.get(RateLimitConfig, config_id)
    if not row:
        raise HTTPException(status_code=404, detail="Rate limit config not found")
    return row


async def update_rate_limit_config(
    config_id: UUID, body: RateLimitConfigUpdate, session: AsyncSession
) -> RateLimitConfigOut:
    row = await session.get(RateLimitConfig, config_id)
    if not row:
        raise HTTPException(status_code=404, detail="Rate limit config not found")
    data = body.model_dump(exclude_unset=True)
    if "name" in data and data["name"] is not None:
        data["name"] = str(data["name"]).strip()
    for k, v in data.items():
        setattr(row, k, v)
    row.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
    try:
        await session.commit()
    except Exception as e:
        await session.rollback()
        raise HTTPException(status_code=409, detail="Update conflict") from e
    await session.refresh(row)
    return row


async def delete_rate_limit_config(config_id: UUID, session: AsyncSession) -> None:
    row = await session.get(RateLimitConfig, config_id)
    if not row:
        raise HTTPException(status_code=404, detail="Rate limit config not found")
    await session.delete(row)
    await session.commit()
