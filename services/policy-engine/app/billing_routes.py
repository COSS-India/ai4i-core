from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import delete, desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ai4icore_env import app_env

from app.billing_schemas import (
    PlanCreateRequest,
    PlanOut,
    PlanServiceOut,
    PlanUpdateRequest,
    QuotaConfigCreate,
    QuotaConfigOut,
    QuotaConfigUpdate,
    QuotaServiceLimitOut,
    RateLimitConfigCreate,
    RateLimitConfigOut,
    RateLimitConfigUpdate,
)
from app.database import get_db_session
from app.db_models import QuotaConfig, QuotaServiceLimit, RateLimitConfig, SubscriptionPlan

logger = logging.getLogger("policy-engine-billing")

router = APIRouter(tags=["policies", "quota", "rate-limit"])


async def _fetch_mt_services_for_tier(tier: str) -> List[Dict[str, Any]]:
    base = (app_env.multi_tenant_service_url or "").rstrip("/")
    if not base:
        logger.warning("multi_tenant_service_url not set; plan services list empty")
        return []
    url = f"{base}/internal/service-configs/tier/{tier}"
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.get(url)
        if r.status_code != 200:
            logger.error("Multi-tenant service-config fetch failed: %s %s", r.status_code, r.text)
            return []
        data = r.json()
        return list(data.get("services") or [])
    except Exception as e:
        logger.exception("Error calling multi-tenant for tier services: %s", e)
        return []


def _quota_to_out(q: QuotaConfig) -> QuotaConfigOut:
    rows = q.service_limit_rows or []
    # Legacy DB rows may have NULL requests_per_hour until manual backfill (see billing_v2_schema_migration.sql).
    rph = q.requests_per_hour
    if rph is None:
        rph = 1000
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


def _quota_public_dict(q: QuotaConfig) -> Dict[str, Any]:
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


def _rate_public_dict(r: RateLimitConfig) -> Dict[str, Any]:
    return {
        "name": r.name,
        "requests_per_hour_per_api_key": r.requests_per_hour_per_api_key,
        "requests_per_hour_per_tenant": r.requests_per_hour_per_tenant,
    }


async def _plan_to_out(session: AsyncSession, plan: SubscriptionPlan) -> PlanOut:
    qc = await session.scalar(
        select(QuotaConfig).options(selectinload(QuotaConfig.service_limit_rows)).where(QuotaConfig.id == plan.quota_config_id)
    )
    rc = await session.get(RateLimitConfig, plan.rate_limit_config_id)
    if not qc or not rc:
        raise HTTPException(status_code=500, detail="Plan is missing linked quota or rate limit config")
    return PlanOut(
        id=plan.id,
        plan_name=plan.plan_name,
        cost=Decimal(str(plan.cost)),
        tier=plan.tier,
        quota_config=_quota_public_dict(qc),
        rate_limit_config=_rate_public_dict(rc),
    )


# --- Quota configs ---
@router.post("/quota-configs", response_model=QuotaConfigOut, status_code=status.HTTP_201_CREATED)
async def create_quota_config(
    body: QuotaConfigCreate,
    session: AsyncSession = Depends(get_db_session),
):
    row = QuotaConfig(name=body.name.strip(), requests_per_hour=body.requests_per_hour)
    session.add(row)
    await session.flush()
    for sl in body.service_limits:
        session.add(
            QuotaServiceLimit(
                quota_config_id=row.id,
                service_type=sl.service_type.strip(),
                unit_type=sl.unit_type.strip(),
                limit_value=sl.limit_value,
            )
        )
    try:
        await session.commit()
    except Exception as e:
        await session.rollback()
        logger.exception("create_quota_config: %s", e)
        raise HTTPException(status_code=409, detail="Could not create quota config (duplicate name?)") from e
    await session.refresh(row)
    q2 = await session.scalar(
        select(QuotaConfig).options(selectinload(QuotaConfig.service_limit_rows)).where(QuotaConfig.id == row.id)
    )
    return _quota_to_out(q2 or row)


@router.get("/quota-configs", response_model=List[QuotaConfigOut])
async def list_quota_configs(session: AsyncSession = Depends(get_db_session)):
    r = await session.execute(
        select(QuotaConfig).options(selectinload(QuotaConfig.service_limit_rows)).order_by(desc(QuotaConfig.created_at))
    )
    return [_quota_to_out(x) for x in r.scalars().all()]


@router.get("/quota-configs/name/{name:path}", response_model=QuotaConfigOut)
async def get_quota_config_by_name(name: str, session: AsyncSession = Depends(get_db_session)):
    n = name.strip()
    row = await session.scalar(
        select(QuotaConfig).options(selectinload(QuotaConfig.service_limit_rows)).where(QuotaConfig.name == n)
    )
    if not row:
        raise HTTPException(status_code=404, detail="Quota config not found")
    return _quota_to_out(row)


@router.get("/quota-configs/{config_id}", response_model=QuotaConfigOut)
async def get_quota_config(config_id: UUID, session: AsyncSession = Depends(get_db_session)):
    row = await session.scalar(
        select(QuotaConfig).options(selectinload(QuotaConfig.service_limit_rows)).where(QuotaConfig.id == config_id)
    )
    if not row:
        raise HTTPException(status_code=404, detail="Quota config not found")
    return _quota_to_out(row)


@router.put("/quota-configs/{config_id}", response_model=QuotaConfigOut)
async def update_quota_config(
    config_id: UUID,
    body: QuotaConfigUpdate,
    session: AsyncSession = Depends(get_db_session),
):
    row = await session.scalar(
        select(QuotaConfig).options(selectinload(QuotaConfig.service_limit_rows)).where(QuotaConfig.id == config_id)
    )
    if not row:
        raise HTTPException(status_code=404, detail="Quota config not found")
    if body.name is not None:
        row.name = body.name.strip()
    if body.requests_per_hour is not None:
        row.requests_per_hour = body.requests_per_hour
    if body.service_limits is not None:
        await session.execute(delete(QuotaServiceLimit).where(QuotaServiceLimit.quota_config_id == row.id))
        for sl in body.service_limits:
            session.add(
                QuotaServiceLimit(
                    quota_config_id=row.id,
                    service_type=sl.service_type.strip(),
                    unit_type=sl.unit_type.strip(),
                    limit_value=sl.limit_value,
                )
            )
    row.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
    try:
        await session.commit()
    except Exception as e:
        await session.rollback()
        raise HTTPException(status_code=409, detail="Update conflict (duplicate name?)") from e
    q2 = await session.scalar(
        select(QuotaConfig).options(selectinload(QuotaConfig.service_limit_rows)).where(QuotaConfig.id == row.id)
    )
    return _quota_to_out(q2 or row)


@router.delete("/quota-configs/{config_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_quota_config(config_id: UUID, session: AsyncSession = Depends(get_db_session)):
    row = await session.get(QuotaConfig, config_id)
    if not row:
        raise HTTPException(status_code=404, detail="Quota config not found")
    await session.delete(row)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- Rate limit configs ---
@router.post("/rate-limit-configs", response_model=RateLimitConfigOut, status_code=status.HTTP_201_CREATED)
async def create_rate_limit_config(
    body: RateLimitConfigCreate,
    session: AsyncSession = Depends(get_db_session),
):
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
        raise HTTPException(status_code=409, detail="Could not create rate limit config (duplicate name?)") from e
    await session.refresh(row)
    return row


@router.get("/rate-limit-configs", response_model=List[RateLimitConfigOut])
async def list_rate_limit_configs(session: AsyncSession = Depends(get_db_session)):
    r = await session.execute(select(RateLimitConfig).order_by(desc(RateLimitConfig.created_at)))
    return list(r.scalars().all())


@router.get("/rate-limit-configs/name/{name:path}", response_model=RateLimitConfigOut)
async def get_rate_limit_config_by_name(name: str, session: AsyncSession = Depends(get_db_session)):
    row = await session.scalar(select(RateLimitConfig).where(RateLimitConfig.name == name.strip()))
    if not row:
        raise HTTPException(status_code=404, detail="Rate limit config not found")
    return row


@router.get("/rate-limit-configs/{config_id}", response_model=RateLimitConfigOut)
async def get_rate_limit_config(config_id: UUID, session: AsyncSession = Depends(get_db_session)):
    row = await session.get(RateLimitConfig, config_id)
    if not row:
        raise HTTPException(status_code=404, detail="Rate limit config not found")
    return row


@router.put("/rate-limit-configs/{config_id}", response_model=RateLimitConfigOut)
async def update_rate_limit_config(
    config_id: UUID,
    body: RateLimitConfigUpdate,
    session: AsyncSession = Depends(get_db_session),
):
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


@router.delete("/rate-limit-configs/{config_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_rate_limit_config(config_id: UUID, session: AsyncSession = Depends(get_db_session)):
    row = await session.get(RateLimitConfig, config_id)
    if not row:
        raise HTTPException(status_code=404, detail="Rate limit config not found")
    await session.delete(row)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- Plans (exposed as /policies) ---
@router.get("/policies/{plan_id}/services", response_model=List[PlanServiceOut])
async def list_plan_services(plan_id: UUID, session: AsyncSession = Depends(get_db_session)):
    plan = await session.get(SubscriptionPlan, plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Policy not found")
    mt_services = await _fetch_mt_services_for_tier(plan.tier)
    out: List[PlanServiceOut] = []
    for s in mt_services:
        sid = str(s.get("id") or s.get("service_id") or "")
        name = str(s.get("service_name") or s.get("name") or "")
        cpu = s.get("cost_per_unit")
        if cpu is None:
            cpu = s.get("price_per_unit")
        try:
            cpu_f = float(cpu) if cpu is not None else 0.0
        except (TypeError, ValueError):
            cpu_f = 0.0
        ut = str(s.get("billing_unit_type") or s.get("unit_type") or "")
        tr = str(s.get("tier") or plan.tier)
        out.append(
            PlanServiceOut(
                service_id=sid,
                service_name=name,
                unit_type=ut,
                cost_per_unit=cpu_f,
                tier=tr,
            )
        )
    return out


@router.post("/policies", response_model=PlanOut, status_code=status.HTTP_201_CREATED)
async def create_policy(
    body: PlanCreateRequest,
    session: AsyncSession = Depends(get_db_session),
):
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
        plan_name=pname,
        cost=body.cost,
        tier=tier_val,
        quota_config_id=qc.id,
        rate_limit_config_id=rc.id,
    )
    session.add(plan)
    try:
        await session.commit()
    except Exception as e:
        await session.rollback()
        logger.exception("create policy: %s", e)
        raise HTTPException(status_code=409, detail="Could not create plan") from e
    await session.refresh(plan)
    return await _plan_to_out(session, plan)


@router.get("/policies", response_model=List[PlanOut])
async def list_policies(session: AsyncSession = Depends(get_db_session)):
    r = await session.execute(select(SubscriptionPlan).order_by(desc(SubscriptionPlan.created_at)))
    plans = list(r.scalars().all())
    out: List[PlanOut] = []
    for p in plans:
        out.append(await _plan_to_out(session, p))
    return out


@router.get("/policies/tier/{tier}", response_model=PlanOut)
async def get_policy_by_tier(tier: str, session: AsyncSession = Depends(get_db_session)):
    plan = await session.scalar(select(SubscriptionPlan).where(SubscriptionPlan.tier == tier.strip()))
    if not plan:
        raise HTTPException(status_code=404, detail="No plan for this tier")
    return await _plan_to_out(session, plan)


@router.get("/policies/{plan_id}", response_model=PlanOut)
async def get_policy(plan_id: UUID, session: AsyncSession = Depends(get_db_session)):
    plan = await session.get(SubscriptionPlan, plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Policy not found")
    return await _plan_to_out(session, plan)


@router.get("/policies/tenant/{tenant_id}")
async def get_policy_for_tenant(tenant_id: str):
    """Resolve tenant's assigned plan snapshot from multi-tenant service."""
    base = (app_env.multi_tenant_service_url or "").rstrip("/")
    if not base:
        raise HTTPException(status_code=503, detail="multi_tenant_service_url is not configured")
    url = f"{base}/internal/tenant-plan/tenant-id/{tenant_id}"
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.get(url)
    if r.status_code == 404:
        raise HTTPException(status_code=404, detail="No plan assigned for tenant")
    if r.status_code != 200:
        raise HTTPException(status_code=502, detail=f"Multi-tenant error: {r.text}")
    return r.json()


@router.put("/policies/{plan_id}", response_model=PlanOut)
async def update_policy(
    plan_id: UUID,
    body: PlanUpdateRequest,
    session: AsyncSession = Depends(get_db_session),
):
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
                select(SubscriptionPlan).where(SubscriptionPlan.tier == tier_val, SubscriptionPlan.id != plan_id)
            )
            if taken:
                raise HTTPException(status_code=400, detail="Tier already assigned to another plan")
            plan.tier = tier_val

    plan.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
    await session.commit()
    await session.refresh(plan)
    return await _plan_to_out(session, plan)


@router.delete("/policies/{plan_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_policy(plan_id: UUID, session: AsyncSession = Depends(get_db_session)):
    plan = await session.get(SubscriptionPlan, plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Policy not found")
    await session.delete(plan)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
