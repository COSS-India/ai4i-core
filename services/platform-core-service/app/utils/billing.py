from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, List

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.pay_per_use.quota_config import QuotaConfig
from app.models.pay_per_use.rate_limit_config import RateLimitConfig
from app.models.pay_per_use.subscription_plan import SubscriptionPlan
from app.schemas.pay_per_use.billing import PlanOut, QuotaConfigOut, QuotaServiceLimitOut


def quota_to_out(q: QuotaConfig) -> QuotaConfigOut:
    rows = q.service_limit_rows or []
    # Legacy DB rows may have NULL requests_per_hour until manual backfill.
    rph = q.requests_per_hour if q.requests_per_hour is not None else 1000
    display_name = (q.name or "").strip() or f"quota-{q.id}"
    return QuotaConfigOut(
        id=q.id,
        name=display_name,
        requests_per_hour=rph,
        service_limits=[
            QuotaServiceLimitOut(
                service_type=r.service_type,
                unit_type=r.unit_type,
                limit_value=r.limit_value,
            )
            for r in rows
        ],
        created_at=q.created_at,
        updated_at=q.updated_at,
    )


def quota_public_dict(q: QuotaConfig) -> Dict[str, Any]:
    rph = q.requests_per_hour if q.requests_per_hour is not None else 1000
    nm = (q.name or "").strip() or f"quota-{q.id}"
    return {
        "name": nm,
        "requests_per_hour": rph,
        "service_limits": [
            {"service_type": r.service_type, "unit_type": r.unit_type, "limit_value": r.limit_value}
            for r in (q.service_limit_rows or [])
        ],
    }


def rate_public_dict(r: RateLimitConfig) -> Dict[str, Any]:
    return {
        "name": r.name,
        "requests_per_hour_per_api_key": r.requests_per_hour_per_api_key,
        "requests_per_hour_per_tenant": r.requests_per_hour_per_tenant,
    }


async def plan_to_out(session: AsyncSession, plan: SubscriptionPlan) -> PlanOut:
    qc = await session.scalar(
        select(QuotaConfig)
        .options(selectinload(QuotaConfig.service_limit_rows))
        .where(QuotaConfig.id == plan.quota_config_id)
    )
    rc = await session.get(RateLimitConfig, plan.rate_limit_config_id)
    if not qc or not rc:
        raise HTTPException(status_code=500, detail="Plan is missing linked quota or rate limit config")
    return PlanOut(
        id=plan.id,
        plan_name=plan.plan_name,
        cost=Decimal(str(plan.cost)),
        tier=plan.tier,
        quota_config=quota_public_dict(qc),
        rate_limit_config=rate_public_dict(rc),
    )
