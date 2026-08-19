"""Tenant + tenant-user CRUD routes — thin handlers; logic in TenantService."""

from typing import Optional
from uuid import UUID

import re

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request, status

from app.core.constants import RoleId
from app.core.responses import to_response
from app.utils.masking import mask_pii_in_dict
from app.dependencies.auth import get_current_user
from app.dependencies.services import get_tenant_service
from app.models.tenant import TenantStatus
from app.models.user import User
from app.schemas.common import MessageData, error_responses
from app.schemas.tenant import (
    CreateTenantResponse,
    CreateTenantUserResponse,
    DeleteTenantUserData,
    DeleteTenantUserResponse,
    GetTenantPlanResponse,
    GetTenantResponse,
    ListTenantsResponse,
    ListTenantUsersResponse,
    ResendTenantUserSetupLinkResponse,
    TenantCreate,
    TenantResponse,
    TenantStatusUpdate,
    TenantUpdate,
    TenantUserCreate,
    TenantUserCreateResponse,
    TenantUserStatusUpdate,
    TenantUserUpdate,
    UpdateTenantResponse,
    UpdateTenantStatusResponse,
    UpdateTenantUserResponse,
    UpdateTenantUserStatusResponse,
)
from app.services.tenant_service import TenantService

router = APIRouter(
    prefix="/auth/tenants",
    tags=["Tenants"],
    responses=error_responses(401),
)


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=CreateTenantResponse,
    responses=error_responses(403, 409),
)
async def create_tenant(
    body: TenantCreate,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    svc: TenantService = Depends(get_tenant_service),
):
    """Create a tenant and provision its first contact admin.

    The tenant starts PENDING. The contact admin receives a set-password
    email; the tenant becomes ACTIVE after they set a password. Duplicate
    email or organisation returns 409. Returned contact PII is masked.
    """
    tenant = await svc.create_tenant(body, current_user, background_tasks)
    return CreateTenantResponse(
        data=mask_pii_in_dict(to_response(tenant, TenantResponse))
    )


@router.get(
    "",
    response_model=ListTenantsResponse,
    responses=error_responses(403),
)
async def list_tenants(
    request: Request,
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    status_filter: Optional[TenantStatus] = Query(None, alias="status"),
    current_user: User = Depends(get_current_user),
    svc: TenantService = Depends(get_tenant_service),
):
    """List tenants with optional status filter.

    Restricted to ADMIN and PROGRAM_ADMIN. Contact PII is masked.
    """
    raw = request.headers.get("X-Permission-Ids", "")
    ids = {int(m) for m in re.findall(r"\d+", raw)}
    is_admin = RoleId.ADMIN in ids
    tenants = await svc.list_tenants(current_user, offset, limit, status_filter, is_admin=is_admin)
    return ListTenantsResponse(
        data=[mask_pii_in_dict(to_response(t, TenantResponse)) for t in tenants]
    )


@router.get(
    "/{tenant_id}",
    response_model=GetTenantResponse,
    responses=error_responses(403, 404),
)
async def get_tenant(
    request: Request,
    tenant_id: int,
    unmask: bool = Query(
        False,
        description=(
            "Return editable PII for the Edit Tenant form. Phone number is "
            "always returned unmasked; the contact email is returned unmasked "
            "only while the tenant is PENDING (before verification). List/view "
            "screens must omit this flag so they keep showing masked values."
        ),
    ),
    current_user: User = Depends(get_current_user),
    svc: TenantService = Depends(get_tenant_service),
):
    """Return one tenant by id.

    Tenant admins are limited to their own tenant. Pass `unmask=true` only
    for the edit form (ADMIN / TENANT_ADMIN).
    """
    raw = request.headers.get("X-Permission-Ids", "")
    ids = {int(m) for m in re.findall(r"\d+", raw)}
    is_admin = RoleId.ADMIN in ids
    tenant = await svc.get_tenant(current_user, tenant_id, unmask=unmask, is_admin=is_admin)
    return GetTenantResponse(data=svc.build_tenant_response(tenant, unmask=unmask))


@router.patch(
    "/{tenant_id}",
    response_model=UpdateTenantResponse,
    responses=error_responses(403, 404, 409),
)
async def update_tenant(
    tenant_id: int,
    body: TenantUpdate,
    background: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    svc: TenantService = Depends(get_tenant_service),
):
    """Update tenant profile fields (not status).

    Status changes go through PATCH /{tenant_id}/status. Duplicate
    organisation or email returns 409. Returned contact PII is masked.
    """
    tenant = await svc.update_tenant(current_user, tenant_id, body, background)
    return UpdateTenantResponse(
        data=mask_pii_in_dict(to_response(tenant, TenantResponse))
    )


@router.patch(
    "/{tenant_id}/status",
    response_model=UpdateTenantStatusResponse,
    responses=error_responses(403, 404),
)
async def update_tenant_status(
    tenant_id: int,
    body: TenantStatusUpdate,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    svc: TenantService = Depends(get_tenant_service),
):
    """Change a tenant's status (ACTIVE / SUSPENDED / DEACTIVATED).

    Admin-only. Suspend/deactivate also updates tenant users and API-key
    cache. Returned contact PII is masked.
    """
    tenant = await svc.update_tenant_status(
        current_user, tenant_id, body, background_tasks
    )
    return UpdateTenantStatusResponse(
        data=mask_pii_in_dict(to_response(tenant, TenantResponse))
    )


@router.get(
    "/{tenant_id}/plan",
    response_model=GetTenantPlanResponse,
    responses=error_responses(404),
)
async def get_tenant_plan(
    tenant_id: int,
    current_user: User = Depends(get_current_user),
    svc: TenantService = Depends(get_tenant_service),
):
    """Return the tenant's current plan assignment.

    404 if the tenant has no plan row.
    """
    plan = await svc.get_tenant_plan(tenant_id)
    return GetTenantPlanResponse(data=plan)


@router.get(
    "/{tenant_id}/users",
    response_model=ListTenantUsersResponse,
    responses=error_responses(403, 404),
)
async def list_tenant_users(
    tenant_id: int,
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    unmask: bool = Query(
        False,
        description=(
            "Return editable PII for the Edit Tenant User form. Only the phone "
            "number is returned unmasked; the email stays masked because it is "
            "non-editable for tenant users. The list/view screens must omit "
            "this flag so they keep showing masked values."
        ),
    ),
    current_user: User = Depends(get_current_user),
    svc: TenantService = Depends(get_tenant_service),
):
    """List users belonging to a tenant.

    Moderators cannot call this. Pass `unmask=true` only for the edit form
    (ADMIN / TENANT_ADMIN); email stays masked.
    """
    users = await svc.list_tenant_users(
        current_user, tenant_id, offset, limit, unmask=unmask
    )
    data = await svc.build_tenant_user_responses(users, unmask_phone=unmask)
    return ListTenantUsersResponse(data=data)


@router.post(
    "/{tenant_id}/users",
    status_code=status.HTTP_201_CREATED,
    response_model=CreateTenantUserResponse,
    responses=error_responses(403, 404, 409),
)
async def create_tenant_user(
    tenant_id: int,
    body: TenantUserCreate,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    svc: TenantService = Depends(get_tenant_service),
):
    """Provision an inactive tenant user and send a set-password email.

    Moderators cannot create users. Duplicate email/username returns 409.
    """
    user_id_str, setup_token = await svc.create_tenant_user(
        current_user, tenant_id, body, background_tasks
    )
    return CreateTenantUserResponse(
        data=TenantUserCreateResponse(user_id=user_id_str, setup_token=setup_token)
    )


@router.patch(
    "/{tenant_id}/users/{user_id}/status",
    response_model=UpdateTenantUserStatusResponse,
    responses=error_responses(403, 404),
)
async def update_tenant_user_status(
    tenant_id: int,
    user_id: UUID,
    body: TenantUserStatusUpdate,
    current_user: User = Depends(get_current_user),
    svc: TenantService = Depends(get_tenant_service),
):
    """Set a tenant user's `is_active` flag.

    Tenant-lock (`is_tenant_active`) is owned by tenant status, not this
    endpoint. Moderators cannot call this.
    """
    target = await svc.update_tenant_user_status(current_user, tenant_id, user_id, body)
    return UpdateTenantUserStatusResponse(
        data=await svc.build_tenant_user_response(target)
    )


@router.post(
    "/{tenant_id}/users/{user_id}/resend-setup-link",
    response_model=ResendTenantUserSetupLinkResponse,
    responses=error_responses(403, 404),
)
async def resend_tenant_user_setup_link(
    tenant_id: int,
    user_id: UUID,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    svc: TenantService = Depends(get_tenant_service),
):
    """Re-send the set-password (SETUP) onboarding email to a tenant user.

    Use this — not /auth/resend-verification — for users created under a tenant,
    who are provisioned passwordless and onboard via a set-password link.
    """
    await svc.resend_tenant_user_setup_link(
        current_user, tenant_id, user_id, background_tasks
    )
    return ResendTenantUserSetupLinkResponse(
        data=MessageData(
            message="A password setup link has been sent to the user's email."
        )
    )


@router.patch(
    "/{tenant_id}/users/{user_id}",
    response_model=UpdateTenantUserResponse,
    responses=error_responses(403, 404, 409),
)
async def update_tenant_user(
    tenant_id: int,
    user_id: UUID,
    body: TenantUserUpdate,
    current_user: User = Depends(get_current_user),
    svc: TenantService = Depends(get_tenant_service),
):
    """Update a tenant user's profile and/or role.

    Provide at least one field. Duplicate email/username returns 409.
    """
    target = await svc.update_tenant_user(current_user, tenant_id, user_id, body)
    return UpdateTenantUserResponse(
        data=await svc.build_tenant_user_response(target)
    )


@router.delete(
    "/{tenant_id}/users/{user_id}",
    response_model=DeleteTenantUserResponse,
    responses=error_responses(403, 404),
)
async def delete_tenant_user(
    tenant_id: int,
    user_id: UUID,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    svc: TenantService = Depends(get_tenant_service),
):
    """Delete a tenant user.
    """
    await svc.delete_tenant_user(current_user, tenant_id, user_id, background_tasks)
    return DeleteTenantUserResponse(
        data=DeleteTenantUserData(user_id=str(user_id), deleted=True)
    )
