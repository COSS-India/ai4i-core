"""Service List column metadata API (column picker)."""

from typing import Annotated, List, Optional

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import TierStatus
from app.core.database import get_db
from app.core.permissions import is_platform_admin
from app.models.pay_per_use.tier import Tier
from app.schemas.common import error_responses
from app.schemas.model_management.service import (
    ServiceColumnDefinition,
    ServiceColumnFilter,
    ServiceColumnFilterOption,
    ServiceColumnsData,
    ServiceColumnsResponse,
)
from app.schemas.model_management.service_columns import columns_for_caller
from app.services.pay_per_use import inference_type_cache

router = APIRouter(
    prefix="/services",
    tags=["Service Management"],
)

_STATUS_OPTIONS = [
    ServiceColumnFilterOption(value="true", label="Published"),
    ServiceColumnFilterOption(value="false", label="Unpublished"),
]


async def _task_type_options(db: AsyncSession) -> List[ServiceColumnFilterOption]:
    entries = await inference_type_cache.get_all(db)
    return [
        ServiceColumnFilterOption(
            value=e["name"].lower(), label=e.get("display_name") or e["name"]
        )
        for e in entries
    ]


async def _tier_options(db: AsyncSession) -> List[ServiceColumnFilterOption]:
    result = await db.execute(
        select(Tier.id, Tier.name)
        .where(Tier.status != TierStatus.DELETED)
        .order_by(Tier.name)
    )
    return [ServiceColumnFilterOption(value=str(r.id), label=r.name) for r in result.all()]


@router.get(
    "/columns",
    summary="Service List Column Catalogue",
    responses=error_responses(401, 403),
)
async def get_service_columns(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ServiceColumnsResponse:
    """Columns the caller may show in the Service List, with filter metadata.

    Non-admin callers do not receive admin-only columns (tier, prices, ...).
    """
    admin = is_platform_admin(request)
    columns = columns_for_caller(admin)
    ids = {c.id for c in columns}

    options: dict[str, Optional[List[ServiceColumnFilterOption]]] = {"status": _STATUS_OPTIONS}
    if "task_type" in ids:
        options["task_type"] = await _task_type_options(db)
    if "tier" in ids:
        options["tier"] = await _tier_options(db)

    out = []
    for c in columns:
        flt = None
        if c.filter_type:
            flt = ServiceColumnFilter(
                type=c.filter_type, params=list(c.filter_params), options=options.get(c.id)
            )
        out.append(
            ServiceColumnDefinition(
                id=c.id,
                label=c.label,
                mandatory=c.mandatory,
                defaultVisible=c.default_visible,
                sortable=c.sortable,
                filterable=c.filterable,
                filter=flt,
            )
        )
    return ServiceColumnsResponse(success=True, data=ServiceColumnsData(columns=out))
