"""PPU usage dashboard routes."""
from __future__ import annotations

from typing import Annotated, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_auth_db_optional, get_db
from app.core.exceptions import InsufficientPermissionsError, ValidationError
from app.core.permissions import (
    ROLE_ADMIN as _ROLE_ADMIN,
    authorize_own_tenant_or_admin as _authorize_tenant,
    permission_ids as _permission_ids,
)
from app.repositories.pay_per_use.usage_repository import UsageRepository
from app.schemas.enums.model_management import resolve_task_type
from app.schemas.pay_per_use.usage import (
    TenantHierarchicalListResponse,
    TenantUsageDetailResponse,
    UsageSummaryResponse,
)
from app.services.pay_per_use.usage_service import UsageService

router = APIRouter(prefix="/pay-per-use", tags=["Usage"])


def _require_admin(request: Request) -> None:
    if not _permission_ids(request) & {_ROLE_ADMIN}:
        raise InsufficientPermissionsError()


def _validate_tier_id(tier_id: Optional[str]) -> Optional[str]:
    """Rejects a non-UUID tier_id with a clean 400 before it reaches the UUID column
    comparison in the repository, where it would otherwise surface as an unhandled 500."""
    if tier_id is None:
        return None
    try:
        UUID(tier_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid tier_id format — expected a UUID",
        )
    return tier_id


def _parse_task_types(task_types: Optional[str]) -> Optional[list[str]]:
    """Comma-separated task types → validated, canonicalized list, or None if not supplied.
    Mirrors tier_service._resolve_task_types so /tiers and the usage endpoints reject
    unrecognized task_types the same way (422 VALIDATION_ERROR) instead of silently
    filtering to an empty/zeroed result.
    """
    if not task_types:
        return None
    parsed = []
    for raw in task_types.split(","):
        raw = raw.strip()
        if not raw:
            continue
        try:
            parsed.append(resolve_task_type(raw))
        except ValueError as exc:
            raise ValidationError(str(exc))
    return parsed or None


@router.get("/usage-summary", response_model=UsageSummaryResponse)
async def get_usage_summary(
    request: Request,
    billing_period: Annotated[
        Optional[str],
        Query(pattern=r"^\d{4}-(0[1-9]|1[0-2])$", description="Billing month in YYYY-MM format. Omit for all-time usage up to now."),
    ] = None,
    tier_id: Optional[str] = Query(None, description="Filter by tier ID."),
    task_types: Optional[str] = Query(None, description="Comma-separated task types to include (frontend allowlist)."),
    db: AsyncSession = Depends(get_db),
    auth_db: Optional[AsyncSession] = Depends(get_auth_db_optional),
):
    _require_admin(request)
    tier_id = _validate_tier_id(tier_id)
    svc = UsageService(UsageRepository(db))
    return await svc.get_summary(billing_period, tier_id, _parse_task_types(task_types), auth_db)


@router.get("/usage-tenants", response_model=TenantHierarchicalListResponse)
async def get_tenant_usage_list(
    request: Request,
    billing_period: Annotated[
        Optional[str],
        Query(pattern=r"^\d{4}-(0[1-9]|1[0-2])$", description="Billing month in YYYY-MM format. Omit for all-time usage up to now."),
    ] = None,
    tier_id: Optional[str] = Query(None, description="Filter by tier ID."),
    modelTaskType: Optional[str] = Query(None, description="Filter by model task type (e.g. LLM, ASR, NMT)."),
    task_types: Optional[str] = Query(None, description="Comma-separated task types to include (frontend allowlist)."),
    sortOrder: Annotated[str, Query(pattern="^(asc|desc)$", description="Sort tenants by spend ascending or descending.")] = "desc",
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of tenants to return."),
    offset: int = Query(0, ge=0, description="Number of tenants to skip (for pagination)."),
    db: AsyncSession = Depends(get_db),
    auth_db: Optional[AsyncSession] = Depends(get_auth_db_optional),
):
    _require_admin(request)
    tier_id = _validate_tier_id(tier_id)
    svc = UsageService(UsageRepository(db))
    return await svc.get_tenant_list(
        billing_period, tier_id, modelTaskType.lower() if modelTaskType else None, auth_db,
        sortOrder, limit, offset, task_types=_parse_task_types(task_types),
    )


@router.get("/usage-tenant", response_model=TenantUsageDetailResponse)
async def get_tenant_usage_detail(
    request: Request,
    tenant_id: str = Query(..., description="Tenant ID."),
    billing_period: Annotated[
        Optional[str],
        Query(pattern=r"^\d{4}-(0[1-9]|1[0-2])$", description="Billing month in YYYY-MM format. Omit for all-time usage up to now."),
    ] = None,
    task_types: Optional[str] = Query(None, description="Comma-separated task types to include (frontend allowlist)."),
    db: AsyncSession = Depends(get_db),
    auth_db: Optional[AsyncSession] = Depends(get_auth_db_optional),
):
    _authorize_tenant(request, tenant_id)

    svc = UsageService(UsageRepository(db))
    return await svc.get_tenant_detail(tenant_id, billing_period, auth_db, task_types=_parse_task_types(task_types))
