"""Bulk allocation edit — PUT /auth/allocations.

Route definition only — no business logic; scope/validation/persistence all
live in AllocationService. No route-level role dependency, same convention
as application.py: role gating (Adopter Admin / Institution Admin only)
happens inside AllocationService via the shared authorize_institution_scope,
DB-verified rather than trusted off the gateway header.
"""

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_platform_core_db
from app.core.exceptions import ValidationError
from app.dependencies.auth import get_current_user
from app.dependencies.services import get_allocation_service
from app.models.user import User
from app.schemas.allocation import AllocationUpdateRequest, AllocationUpdateResponse
from app.schemas.common import error_responses
from app.services.allocation_service import AllocationService

router = APIRouter(
    prefix="/auth/allocations",
    tags=["Allocations"],
    responses=error_responses(401),
)


@router.put(
    "",
    response_model=AllocationUpdateResponse,
    responses=error_responses(403, 404, 422),
)
async def update_allocations(
    body: AllocationUpdateRequest,
    tenant_id: Optional[int] = Query(
        None, description="Scope: Institution -> Applications. Mutually exclusive with application_id."
    ),
    application_id: Optional[int] = Query(
        None, description="Scope: Application -> API Keys. Mutually exclusive with tenant_id."
    ),
    current_user: User = Depends(get_current_user),
    svc: AllocationService = Depends(get_allocation_service),
    platform_core_db: Optional[AsyncSession] = Depends(get_platform_core_db),
):
    """Rebalance Budget allocation across Applications (an Institution's own
    Budget) or across API Keys (one Application's own Budget) — exactly one
    of `tenant_id`/`application_id` must be given.

    Only the rows explicitly listed at this call's own scope are touched;
    siblings you don't mention are left exactly as they are. Within a row
    you DID list and resize, its own un-listed children (an Application's
    un-listed Keys) DO go through the unconditional proportional re-fit —
    see AllocationService.update_tenant_application_allocations and
    allocation_validator.resolve_level for the full two-rule split.
    """
    if tenant_id is not None and application_id is not None:
        raise ValidationError(
            message="Pass exactly one of tenant_id or application_id, not both.",
            code="AMBIGUOUS_SCOPE",
        )
    if tenant_id is not None:
        data = await svc.update_tenant_application_allocations(
            tenant_id, body, current_user, platform_core_db
        )
    elif application_id is not None:
        data = await svc.update_application_key_allocations(
            application_id, body, current_user, platform_core_db
        )
    else:
        raise ValidationError(
            message="Pass exactly one of tenant_id or application_id.",
            code="MISSING_SCOPE",
        )
    return AllocationUpdateResponse(data=data)
