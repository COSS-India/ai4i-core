"""Application-level usage routes for the Metering Dashboard's Applications tab."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_auth_db_optional, get_db
from app.core.permissions import authorize_own_tenant_or_admin as _authorize_tenant
from app.repositories.pay_per_use.application_usage_repository import (
    ApplicationUsageRepository,
)
from app.schemas.pay_per_use.application_usage import (
    ApplicationUsageDetailResponse,
    ApplicationUsageListResponse,
    ApplicationUsageSummaryResponse,
)
from app.services.pay_per_use.application_usage_service import ApplicationUsageService
from app.utils.usage_period import (
    FROM_DESCRIPTION,
    PERIOD_DESCRIPTION,
    TO_DESCRIPTION,
    period_from_request,
)

router = APIRouter(prefix="/pay-per-use", tags=["Usage"])


@router.get(
    "/usage-applications-summary",
    response_model=ApplicationUsageSummaryResponse,
    description="An institution's Applications totals: spend in the selected period "
    "(periodSpend) next to the all-time allocated, spent and remaining budget "
    "(billingPeriod \"lifetime\").",
)
async def get_application_usage_summary(
    request: Request,
    tenant_id: str = Query(..., description="Institution (tenant) ID."),
    period: Optional[str] = Query(None, description=PERIOD_DESCRIPTION),
    from_: Optional[str] = Query(None, alias="from", description=FROM_DESCRIPTION),
    to: Optional[str] = Query(None, description=TO_DESCRIPTION),
    db: AsyncSession = Depends(get_db),
    auth_db: Optional[AsyncSession] = Depends(get_auth_db_optional),
):
    _authorize_tenant(request, tenant_id)
    usage_period = period_from_request(request, period, from_, to)
    svc = ApplicationUsageService(ApplicationUsageRepository(db))
    return await svc.get_summary(tenant_id, usage_period, auth_db)


@router.get(
    "/usage-applications",
    response_model=ApplicationUsageListResponse,
    description="Per-application spend in the selected period next to all-time "
    "figures, sorted by spend in the period.",
)
async def get_application_usage_list(
    request: Request,
    tenant_id: str = Query(..., description="Institution (tenant) ID."),
    period: Optional[str] = Query(None, description=PERIOD_DESCRIPTION),
    from_: Optional[str] = Query(None, alias="from", description=FROM_DESCRIPTION),
    to: Optional[str] = Query(None, description=TO_DESCRIPTION),
    sortOrder: str = Query("desc", pattern="^(asc|desc)$", description="Sort applications by spend in the period."),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    auth_db: Optional[AsyncSession] = Depends(get_auth_db_optional),
):
    _authorize_tenant(request, tenant_id)
    usage_period = period_from_request(request, period, from_, to)
    svc = ApplicationUsageService(ApplicationUsageRepository(db))
    return await svc.get_application_list(tenant_id, usage_period, auth_db, sortOrder, limit, offset)


@router.get(
    "/usage-application",
    response_model=ApplicationUsageDetailResponse,
    description="One application's spend in the selected period, per API key and "
    "in total, next to all-time figures.",
)
async def get_application_usage_detail(
    request: Request,
    application_id: int = Query(..., description="Application ID."),
    tenant_id: str = Query(..., description="Institution (tenant) ID."),
    period: Optional[str] = Query(None, description=PERIOD_DESCRIPTION),
    from_: Optional[str] = Query(None, alias="from", description=FROM_DESCRIPTION),
    to: Optional[str] = Query(None, description=TO_DESCRIPTION),
    db: AsyncSession = Depends(get_db),
    auth_db: Optional[AsyncSession] = Depends(get_auth_db_optional),
):
    _authorize_tenant(request, tenant_id)
    usage_period = period_from_request(request, period, from_, to)
    svc = ApplicationUsageService(ApplicationUsageRepository(db))
    return await svc.get_application_detail(application_id, tenant_id, usage_period, auth_db)
