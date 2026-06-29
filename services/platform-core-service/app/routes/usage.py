"""PPU usage dashboard routes."""
from __future__ import annotations

import re
from datetime import date
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_auth_db_optional, get_db
from app.core.exceptions import InsufficientPermissionsError
from app.repositories.pay_per_use.ppu_usage_repository import PPUUsageRepository
from app.schemas.pay_per_use.usage import (
    TenantUsageDetailResponse,
    TenantUsageListResponse,
    UsageSummaryResponse,
)
from app.services.pay_per_use.ppu_usage_service import PPUUsageService

router = APIRouter(prefix="/usage", tags=["Usage"])

_ROLE_ADMIN = 1
_ROLE_MODERATOR = 2
_ROLE_TENANT_ADMIN = 5


def _permission_ids(request: Request) -> set[int]:
    raw = request.headers.get("X-Permission-IDS", "")
    return {int(m) for m in re.findall(r"\d+", raw)}


def _require_admin(request: Request) -> None:
    if not _permission_ids(request) & {_ROLE_ADMIN, _ROLE_MODERATOR}:
        raise InsufficientPermissionsError()


def _require_usage_access(request: Request) -> None:
    if not _permission_ids(request) & {_ROLE_ADMIN, _ROLE_MODERATOR, _ROLE_TENANT_ADMIN}:
        raise InsufficientPermissionsError()


def _is_admin(request: Request) -> bool:
    return bool(_permission_ids(request) & {_ROLE_ADMIN, _ROLE_MODERATOR})


def _caller_tenant_id(request: Request) -> Optional[str]:
    return request.headers.get("X-Tenant-Id") or None


@router.get("/summary", response_model=UsageSummaryResponse)
async def get_usage_summary(
    request: Request,
    billing_period: Annotated[
        Optional[str],
        Query(pattern=r"^\d{4}-(0[1-9]|1[0-2])$", description="Billing month in YYYY-MM format. Defaults to current month."),
    ] = None,
    db: AsyncSession = Depends(get_db),
):
    _require_admin(request)
    month = billing_period or date.today().strftime("%Y-%m")
    svc = PPUUsageService(PPUUsageRepository(db))
    return await svc.get_summary(month)


@router.get("/tenants", response_model=TenantUsageListResponse)
async def get_tenant_usage_list(
    request: Request,
    billing_period: Annotated[
        Optional[str],
        Query(pattern=r"^\d{4}-(0[1-9]|1[0-2])$", description="Billing month in YYYY-MM format. Defaults to current month."),
    ] = None,
    tier: Optional[str] = Query(None, description="Filter by tier name."),
    modelTaskType: Optional[str] = Query(None, description="Filter by model task type (e.g. LLM, ASR, NMT)."),
    db: AsyncSession = Depends(get_db),
    auth_db: Optional[AsyncSession] = Depends(get_auth_db_optional),
):
    _require_admin(request)
    month = billing_period or date.today().strftime("%Y-%m")
    svc = PPUUsageService(PPUUsageRepository(db))
    return await svc.get_tenant_list(month, tier, modelTaskType.lower() if modelTaskType else None, auth_db)


@router.get("/tenant", response_model=TenantUsageDetailResponse)
async def get_tenant_usage_detail(
    request: Request,
    tenant_id: str = Query(..., description="Tenant ID."),
    billing_period: Annotated[
        Optional[str],
        Query(pattern=r"^\d{4}-(0[1-9]|1[0-2])$", description="Billing month in YYYY-MM format. Defaults to current month."),
    ] = None,
    db: AsyncSession = Depends(get_db),
    auth_db: Optional[AsyncSession] = Depends(get_auth_db_optional),
):
    _require_usage_access(request)

    if not _is_admin(request):
        caller_tid = _caller_tenant_id(request)
        if not caller_tid:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Tenant admin requires a tenant context (X-Tenant-Id).",
            )
        if caller_tid != tenant_id:
            raise InsufficientPermissionsError()

    month = billing_period or date.today().strftime("%Y-%m")
    svc = PPUUsageService(PPUUsageRepository(db))
    return await svc.get_tenant_detail(tenant_id, month, auth_db)
