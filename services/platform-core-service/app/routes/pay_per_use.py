from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.redis import get_redis_client
from app.schemas.pay_per_use.pay_per_use import (
    CheckRequest,
    CheckResponse,
    RecordRequest,
    RecordResponse,
    TopUpRequest,
)
from app.schemas.pay_per_use.billing import (
    PlanCreateRequest,
    PlanOut,
    PlanServiceOut,
    PlanUpdateRequest,
    QuotaConfigCreate,
    QuotaConfigOut,
    QuotaConfigUpdate,
    RateLimitConfigCreate,
    RateLimitConfigOut,
    RateLimitConfigUpdate,
)
from app.services.pay_per_use import pay_per_use_service as ppu_svc
from app.services.pay_per_use import billing_policies_service as billing_svc
from app.services.pay_per_use import quota_config_service as quota_svc
from app.services.pay_per_use import rate_limit_service as rate_svc

router = APIRouter(prefix="/pay-per-use", tags=["Pay Per Use"])
billing_router = APIRouter(prefix="/billing", tags=["Billing"])

@router.post("/check", response_model=CheckResponse)
async def check_usage(body: CheckRequest, session: AsyncSession = Depends(get_db)):
    rds = get_redis_client()
    return await ppu_svc.check_usage(body, session, rds)


@router.post("/record", response_model=RecordResponse)
async def record_usage(body: RecordRequest, session: AsyncSession = Depends(get_db)):
    rds = get_redis_client()
    return await ppu_svc.record_usage(body, session, rds)


@router.get("/usage/tenant/{tenant_id}")
async def usage_tenant(
    tenant_id: str,
    response: Response,
    session: AsyncSession = Depends(get_db),
):
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, private"
    response.headers["Pragma"] = "no-cache"
    rds = get_redis_client()
    return await ppu_svc.get_tenant_usage(tenant_id, session, rds)


@router.get("/usage/tenant/{tenant_id}/api-keys")
async def usage_tenant_api_keys(tenant_id: str, session: AsyncSession = Depends(get_db)):
    return await ppu_svc.get_tenant_api_key_usage(tenant_id, session)


@router.get("/usage/adopter")
async def usage_adopter(session: AsyncSession = Depends(get_db)):
    rds = get_redis_client()
    return await ppu_svc.get_adopter_usage(session, rds)


@router.get("/wallet/{tenant_id}")
async def get_wallet(tenant_id: str, session: AsyncSession = Depends(get_db)):
    rds = get_redis_client()
    return await ppu_svc.get_wallet(tenant_id, session, rds)


@router.post("/wallet/{tenant_id}/topup")
async def topup_wallet(
    tenant_id: str,
    body: TopUpRequest,
    session: AsyncSession = Depends(get_db),
):
    return await ppu_svc.topup_wallet(tenant_id, body, session)


@router.get("/quota/{tenant_id}/status")
async def quota_status(tenant_id: str):
    rds = get_redis_client()
    return await ppu_svc.get_quota_status(tenant_id, rds)


@router.post("/quota/{tenant_id}/reset")
async def quota_reset(tenant_id: str):
    rds = get_redis_client()
    return await ppu_svc.reset_quota(tenant_id, rds)



# ── Billing Policies ──────────────────────────────────────────────────────────

@billing_router.get("/policies/{plan_id}/services", response_model=List[PlanServiceOut])
async def list_plan_services(plan_id: UUID, session: AsyncSession = Depends(get_db)):
    return await billing_svc.list_plan_services(plan_id, session)


@billing_router.post("/policies", response_model=PlanOut, status_code=status.HTTP_201_CREATED)
async def create_policy(body: PlanCreateRequest, session: AsyncSession = Depends(get_db)):
    return await billing_svc.create_policy(body, session)


@billing_router.get("/policies", response_model=List[PlanOut])
async def list_policies(session: AsyncSession = Depends(get_db)):
    return await billing_svc.list_policies(session)


@billing_router.get("/policies/tier/{tier}", response_model=PlanOut)
async def get_policy_by_tier(tier: str, session: AsyncSession = Depends(get_db)):
    return await billing_svc.get_policy_by_tier(tier, session)


@billing_router.get("/policies/{plan_id}", response_model=PlanOut)
async def get_policy(plan_id: UUID, session: AsyncSession = Depends(get_db)):
    return await billing_svc.get_policy_by_id(plan_id, session)


@billing_router.get("/policies/tenant/{tenant_id}")
async def get_policy_for_tenant(tenant_id: str):
    return await billing_svc.get_policy_for_tenant(tenant_id)


@billing_router.put("/policies/{plan_id}", response_model=PlanOut)
async def update_policy(
    plan_id: UUID, body: PlanUpdateRequest, session: AsyncSession = Depends(get_db)
):
    return await billing_svc.update_policy(plan_id, body, session)


@billing_router.delete("/policies/{plan_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_policy(plan_id: UUID, session: AsyncSession = Depends(get_db)):
    await billing_svc.delete_policy(plan_id, session)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ── Billing - Quota Config ────────────────────────────────────────────────────

@billing_router.post("/quota-configs", response_model=QuotaConfigOut, status_code=status.HTTP_201_CREATED)
async def create_quota_config(body: QuotaConfigCreate, session: AsyncSession = Depends(get_db)):
    return await quota_svc.create_quota_config(body, session)


@billing_router.get("/quota-configs", response_model=List[QuotaConfigOut])
async def list_quota_configs(session: AsyncSession = Depends(get_db)):
    return await quota_svc.list_quota_configs(session)


@billing_router.get("/quota-configs/name/{name:path}", response_model=QuotaConfigOut)
async def get_quota_config_by_name(name: str, session: AsyncSession = Depends(get_db)):
    return await quota_svc.get_quota_config_by_name(name, session)


@billing_router.get("/quota-configs/{config_id}", response_model=QuotaConfigOut)
async def get_quota_config(config_id: UUID, session: AsyncSession = Depends(get_db)):
    return await quota_svc.get_quota_config_by_id(config_id, session)


@billing_router.put("/quota-configs/{config_id}", response_model=QuotaConfigOut)
async def update_quota_config(
    config_id: UUID, body: QuotaConfigUpdate, session: AsyncSession = Depends(get_db)
):
    return await quota_svc.update_quota_config(config_id, body, session)


@billing_router.delete("/quota-configs/{config_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_quota_config(config_id: UUID, session: AsyncSession = Depends(get_db)):
    await quota_svc.delete_quota_config(config_id, session)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ── Billing - Rate Limit Config ───────────────────────────────────────────────

@billing_router.post("/rate-limit-configs", response_model=RateLimitConfigOut, status_code=status.HTTP_201_CREATED)
async def create_rate_limit_config(body: RateLimitConfigCreate, session: AsyncSession = Depends(get_db)):
    return await rate_svc.create_rate_limit_config(body, session)


@billing_router.get("/rate-limit-configs", response_model=List[RateLimitConfigOut])
async def list_rate_limit_configs(session: AsyncSession = Depends(get_db)):
    return await rate_svc.list_rate_limit_configs(session)


@billing_router.get("/rate-limit-configs/name/{name:path}", response_model=RateLimitConfigOut)
async def get_rate_limit_config_by_name(name: str, session: AsyncSession = Depends(get_db)):
    return await rate_svc.get_rate_limit_config_by_name(name, session)


@billing_router.get("/rate-limit-configs/{config_id}", response_model=RateLimitConfigOut)
async def get_rate_limit_config(config_id: UUID, session: AsyncSession = Depends(get_db)):
    return await rate_svc.get_rate_limit_config_by_id(config_id, session)


@billing_router.put("/rate-limit-configs/{config_id}", response_model=RateLimitConfigOut)
async def update_rate_limit_config(
    config_id: UUID, body: RateLimitConfigUpdate, session: AsyncSession = Depends(get_db)
):
    return await rate_svc.update_rate_limit_config(config_id, body, session)


@billing_router.delete("/rate-limit-configs/{config_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_rate_limit_config(config_id: UUID, session: AsyncSession = Depends(get_db)):
    await rate_svc.delete_rate_limit_config(config_id, session)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


