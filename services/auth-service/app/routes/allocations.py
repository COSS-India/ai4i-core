"""Budget Allocation APIs — three level-specific endpoints, replacing the
old single PUT /auth/allocations (scoped by a tenant_id/application_id
query param).

Route definitions only — no business logic; scope/validation/persistence
all live in AllocationService. No route-level role dependency, same
convention as application.py: role gating (Adopter Admin / Institution
Admin only) happens inside AllocationService via the shared
authorize_institution_scope, DB-verified rather than trusted off the
gateway header.
"""

from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_platform_core_db
from app.dependencies.auth import get_current_user
from app.dependencies.services import get_allocation_service
from app.models.user import User
from app.schemas.allocation import (
    APIKeyBudgetAllocationRequest,
    ApplicationAllocationResponseItem,
    ApplicationBudgetAllocationRequest,
    TenantBudgetAllocationRequest,
)
from app.schemas.common import error_responses
from app.services.allocation_service import AllocationService

router = APIRouter(tags=["Allocations"], responses=error_responses(401))


@router.put(
    "/auth/tenants/{tenant_id}/budget-allocation",
    response_model=list[ApplicationAllocationResponseItem],
    responses=error_responses(403, 404, 422),
)
async def update_tenant_budget_allocation(
    tenant_id: int,
    body: TenantBudgetAllocationRequest,
    current_user: User = Depends(get_current_user),
    svc: AllocationService = Depends(get_allocation_service),
    platform_core_db: Optional[AsyncSession] = Depends(get_platform_core_db),
):
    """Rebalance an Institution's Budget across its Applications.

    An Application not listed in ``applications`` is not required to be —
    it's proportionally re-fit against what's left of the Tenant's own
    (unchanged) total, the same unconditional re-fit rule used everywhere
    a parent's children are being resolved. A listed Application's own
    un-listed Keys go through the same rule one level down, whenever that
    Application's own amount actually changes. Returns every Application
    under the Tenant that has an allocation, not just the ones listed —
    see AllocationService.update_tenant_application_allocations.
    """
    return await svc.update_tenant_application_allocations(
        tenant_id, body, current_user, platform_core_db
    )


@router.put(
    "/auth/applications/{application_id}/budget-allocation",
    response_model=ApplicationAllocationResponseItem,
    responses=error_responses(403, 404, 422),
)
async def update_application_budget_allocation(
    application_id: int,
    body: ApplicationBudgetAllocationRequest,
    current_user: User = Depends(get_current_user),
    svc: AllocationService = Depends(get_allocation_service),
    platform_core_db: Optional[AsyncSession] = Depends(get_platform_core_db),
):
    """Rebalance one Application's Budget across its own API Keys.

    ``allocation`` (the Application's own value) is echo-only — this
    endpoint never changes an Application's share of the Institution's
    Budget, only its Keys' shares of the Application; it must match
    what's already stored. A Key not listed in ``api_keys`` is not
    required to be — it's proportionally re-fit against what's left of
    the Application's own (unchanged) total, the same unconditional
    re-fit rule used everywhere a parent's children are being resolved.
    Returns every Key under the Application, not just the ones listed —
    see AllocationService.update_application_key_allocations.
    """
    return await svc.update_application_key_allocations(
        application_id, body, current_user, platform_core_db
    )


@router.put(
    "/auth/api-keys/{key_id}/budget-allocation",
    response_model=ApplicationAllocationResponseItem,
    responses=error_responses(403, 404, 422),
)
async def update_api_key_budget_allocation(
    key_id: int,
    body: APIKeyBudgetAllocationRequest,
    current_user: User = Depends(get_current_user),
    svc: AllocationService = Depends(get_allocation_service),
    platform_core_db: Optional[AsyncSession] = Depends(get_platform_core_db),
):
    """Update a single API Key's own allocation.

    Because Key allocations are relative to their parent Application, and
    resizing one Key re-fits any of its siblings the caller left
    unmentioned, this returns the complete parent Application object —
    including every sibling Key — not just the one Key updated. See
    AllocationService.update_single_api_key_allocation.
    """
    return await svc.update_single_api_key_allocation(key_id, body, current_user, platform_core_db)
