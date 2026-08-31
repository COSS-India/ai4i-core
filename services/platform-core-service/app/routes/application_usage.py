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

router = APIRouter(prefix="/pay-per-use", tags=["Usage"])


@router.get("/usage-applications-summary", response_model=ApplicationUsageSummaryResponse)
async def get_application_usage_summary(
    request: Request,
    tenant_id: str = Query(..., description="Institution (tenant) ID."),
    db: AsyncSession = Depends(get_db),
    auth_db: Optional[AsyncSession] = Depends(get_auth_db_optional),
):
    _authorize_tenant(request, tenant_id)
    svc = ApplicationUsageService(ApplicationUsageRepository(db))
    return await svc.get_summary(tenant_id, auth_db)


@router.get("/usage-applications", response_model=ApplicationUsageListResponse)
async def get_application_usage_list(
    request: Request,
    tenant_id: str = Query(..., description="Institution (tenant) ID."),
    sortOrder: str = Query("desc", pattern="^(asc|desc)$", description="Sort applications by spend."),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    auth_db: Optional[AsyncSession] = Depends(get_auth_db_optional),
):
    _authorize_tenant(request, tenant_id)
    svc = ApplicationUsageService(ApplicationUsageRepository(db))
    return await svc.get_application_list(tenant_id, auth_db, sortOrder, limit, offset)


@router.get("/usage-application", response_model=ApplicationUsageDetailResponse)
async def get_application_usage_detail(
    request: Request,
    application_id: int = Query(..., description="Application ID."),
    tenant_id: str = Query(..., description="Institution (tenant) ID."),
    db: AsyncSession = Depends(get_db),
    auth_db: Optional[AsyncSession] = Depends(get_auth_db_optional),
):
    _authorize_tenant(request, tenant_id)
    svc = ApplicationUsageService(ApplicationUsageRepository(db))
    return await svc.get_application_detail(application_id, tenant_id, auth_db)
