"""Application CRUD routes — thin handlers; logic in ApplicationService.

No route-level role dependency, same as tenants.py — role gating (only
Adopter Admin / Institution Admin, MODERATOR excluded) happens inside
ApplicationService._authorize via a DB-verified role lookup, matching how
TenantService.enforce_scope / _deny_moderator / _assert_can_reveal_pii do it.
"""

from typing import Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_platform_core_db
from app.core.responses import to_response
from app.dependencies.auth import get_current_user
from app.dependencies.services import get_application_service
from app.models.user import User
from app.schemas.application import (
    ApplicationCreate,
    ApplicationListData,
    ApplicationListItem,
    ApplicationResponse,
    ApplicationUpdate,
    CreateApplicationResponse,
    GetApplicationResponse,
    ListApplicationsResponse,
    UpdateApplicationResponse,
)
from app.schemas.common import error_responses
from app.services.application_service import ApplicationService

router = APIRouter(
    # Contract shows a bare "/tenants/{tenant_id}/applications" path, but every
    # other tenant sub-resource in this service (users, plan, status) lives
    # under "/auth/tenants/{tenant_id}/..." — normalized here to match, rather
    # than introduce a one-off top-level "/tenants" namespace alongside it.
    prefix="/auth/tenants/{tenant_id}/applications",
    tags=["Applications"],
    responses=error_responses(401),
)


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=CreateApplicationResponse,
    responses=error_responses(403, 404, 409, 422),
)
async def create_application(
    tenant_id: int,
    body: ApplicationCreate,
    current_user: User = Depends(get_current_user),
    svc: ApplicationService = Depends(get_application_service),
):
    """Onboard an Application under a tenant as an independent entity.

    Only Adopter Admin / Institution Admin may call this. Name must be unique
    within the tenant (case-insensitive). Budget is optional; when given as
    allocated_percentage, the sum of every Application's percentage under
    this tenant must stay <= 100%.
    """
    app = await svc.create_application(tenant_id, body, current_user)
    return CreateApplicationResponse(data=to_response(app, ApplicationResponse))


@router.get(
    "/{application_id}",
    response_model=GetApplicationResponse,
    responses=error_responses(403, 404),
)
async def get_application(
    tenant_id: int,
    application_id: int,
    current_user: User = Depends(get_current_user),
    svc: ApplicationService = Depends(get_application_service),
):
    """Return one Application by id. 404 whether it doesn't exist or belongs to another tenant."""
    app = await svc.get_application(tenant_id, application_id, current_user)
    return GetApplicationResponse(data=to_response(app, ApplicationResponse))


@router.get(
    "",
    response_model=ListApplicationsResponse,
    responses=error_responses(403, 404),
)
async def list_applications(
    tenant_id: int,
    search: Optional[str] = Query(None, description="Match against Application name or Domain"),
    domain: Optional[str] = Query(None, description="Filter to an exact Domain"),
    page: int = Query(1, ge=1),
    size: int = Query(100, ge=1, le=500),
    current_user: User = Depends(get_current_user),
    svc: ApplicationService = Depends(get_application_service),
):
    """List Applications for a tenant, with search (name/domain) and domain filter."""
    offset = (page - 1) * size
    items, total = await svc.list_applications(
        tenant_id,
        current_user,
        search=search,
        domain=domain,
        offset=offset,
        limit=size,
    )
    return ListApplicationsResponse(
        data=ApplicationListData(
            items=[to_response(a, ApplicationListItem) for a in items],
            total=total,
        )
    )


@router.patch(
    "/{application_id}",
    response_model=UpdateApplicationResponse,
    responses=error_responses(403, 404, 409, 422),
)
async def update_application(
    tenant_id: int,
    application_id: int,
    body: ApplicationUpdate,
    current_user: User = Depends(get_current_user),
    svc: ApplicationService = Depends(get_application_service),
    platform_core_db: Optional[AsyncSession] = Depends(get_platform_core_db),
):
    """Update name / domain / status. Budget is not editable here — 422 if sent.

    Name stays unique within the tenant (case-insensitive) after edit.

    ``platform_core_db`` is only used when this update deactivates the
    Application — it carries the zeroed ceiling through to platform-core's
    budget_usage.api_key_budget_snap for the Application's Keys, same as
    the three Budget Allocation endpoints.
    """
    app = await svc.update_application(
        tenant_id, application_id, body, current_user, platform_core_db
    )
    return UpdateApplicationResponse(data=to_response(app, ApplicationResponse))
