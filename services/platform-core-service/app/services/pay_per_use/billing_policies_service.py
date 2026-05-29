from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List
from uuid import UUID

import httpx
from fastapi import HTTPException
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.pay_per_use.quota_config import QuotaConfig
from app.models.pay_per_use.rate_limit_config import RateLimitConfig
from app.models.pay_per_use.subscription_plan import SubscriptionPlan
from app.schemas.pay_per_use.billing import (
    PlanCreateRequest,
    PlanOut,
    PlanServiceOut,
    PlanUpdateRequest,
)
from app.services.pay_per_use.pay_per_use_service import fetch_mt_services_for_tier
from app.utils.billing import plan_to_out

logger = logging.getLogger("billing-policies-service")


async def list_plan_services(plan_id: UUID, session: AsyncSession) -> List[PlanServiceOut]:
    plan = await session.get(SubscriptionPlan, plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Policy not found")
    mt_services = await fetch_mt_services_for_tier(plan.tier, session)
    out: List[PlanServiceOut] = []
    for s in mt_services:
        sid = str(s.get("id") or s.get("service_id") or "")
        name = str(s.get("service_name") or s.get("name") or "")
        cpu = s.get("cost_per_unit") or s.get("price_per_unit")
        try:
            cpu_f = float(cpu) if cpu is not None else 0.0
        except (TypeError, ValueError):
            cpu_f = 0.0
        ut = str(s.get("billing_unit_type") or s.get("unit_type") or "")
        tr = str(s.get("tier") or plan.tier)
        out.append(PlanServiceOut(service_id=sid, service_name=name, unit_type=ut, cost_per_unit=cpu_f, tier=tr))
    return out


async def create_policy(body: PlanCreateRequest, session: AsyncSession) -> PlanOut:
    pname = body.plan_name.strip()
    qc = await session.scalar(select(QuotaConfig).where(QuotaConfig.name == pname))
    if not qc:
        raise HTTPException(status_code=400, detail=f"Quota config '{pname}' not found")
    rc = await session.scalar(select(RateLimitConfig).where(RateLimitConfig.name == pname))
    if not rc:
        raise HTTPException(status_code=400, detail=f"Rate limit config '{pname}' not found")

    tier_val = body.tier.value
    existing = await session.scalar(select(SubscriptionPlan).where(SubscriptionPlan.tier == tier_val))
    if existing:
        raise HTTPException(status_code=400, detail="Tier already assigned to another plan")

    plan = SubscriptionPlan(
        plan_name=pname, cost=body.cost, tier=tier_val,
        quota_config_id=qc.id, rate_limit_config_id=rc.id,
    )
    session.add(plan)
    try:
        await session.commit()
    except Exception as e:
        await session.rollback()
        logger.exception("create_policy: %s", e)
        raise HTTPException(status_code=409, detail="Could not create plan") from e
    await session.refresh(plan)
    return await plan_to_out(session, plan)


async def list_policies(session: AsyncSession) -> List[PlanOut]:
    r = await session.execute(select(SubscriptionPlan).order_by(desc(SubscriptionPlan.created_at)))
    return [await plan_to_out(session, p) for p in r.scalars().all()]


async def get_policy_by_tier(tier: str, session: AsyncSession) -> PlanOut:
    plan = await session.scalar(
        select(SubscriptionPlan).where(SubscriptionPlan.tier == tier.strip())
    )
    if not plan:
        raise HTTPException(status_code=404, detail="No plan for this tier")
    return await plan_to_out(session, plan)


async def get_policy_by_id(plan_id: UUID, session: AsyncSession) -> PlanOut:
    plan = await session.get(SubscriptionPlan, plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Policy not found")
    return await plan_to_out(session, plan)


async def get_policy_for_tenant(tenant_id: str) -> Dict[str, Any]:
    base = settings.auth_service_url.rstrip("/")
    if not base:
        raise HTTPException(status_code=503, detail="auth_service_url is not configured")
    url = f"{base}/internal/tenant-plan/tenant-id/{tenant_id}"
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.get(url)
    if r.status_code == 404:
        raise HTTPException(status_code=404, detail="No plan assigned for tenant")
    if r.status_code != 200:
        raise HTTPException(status_code=502, detail=f"Multi-tenant error: {r.text}")
    return r.json()


async def update_policy(
    plan_id: UUID, body: PlanUpdateRequest, session: AsyncSession
) -> PlanOut:
    plan = await session.get(SubscriptionPlan, plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Policy not found")

    new_name = body.plan_name.strip() if body.plan_name is not None else None
    if new_name is not None and new_name != plan.plan_name:
        qc = await session.scalar(select(QuotaConfig).where(QuotaConfig.name == new_name))
        if not qc:
            raise HTTPException(status_code=400, detail=f"Quota config '{new_name}' not found")
        rc = await session.scalar(select(RateLimitConfig).where(RateLimitConfig.name == new_name))
        if not rc:
            raise HTTPException(status_code=400, detail=f"Rate limit config '{new_name}' not found")
        plan.plan_name = new_name
        plan.quota_config_id = qc.id
        plan.rate_limit_config_id = rc.id

    if body.cost is not None:
        plan.cost = body.cost

    if body.tier is not None:
        tier_val = body.tier.value
        if tier_val != plan.tier:
            taken = await session.scalar(
                select(SubscriptionPlan).where(
                    SubscriptionPlan.tier == tier_val,
                    SubscriptionPlan.id != plan_id,
                )
            )
            if taken:
                raise HTTPException(status_code=400, detail="Tier already assigned to another plan")
            plan.tier = tier_val

    plan.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
    await session.commit()
    await session.refresh(plan)
    return await plan_to_out(session, plan)


async def delete_policy(plan_id: UUID, session: AsyncSession) -> None:
    plan = await session.get(SubscriptionPlan, plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Policy not found")
    await session.delete(plan)
    await session.commit()
