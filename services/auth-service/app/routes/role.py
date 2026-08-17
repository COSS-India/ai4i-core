"""
Role and permission management routes.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.exceptions import EntityNotFoundError
from app.core.responses import to_response
from app.dependencies.auth import get_current_user
from app.dependencies.permissions import require_any_role
from app.dependencies.services import get_role_service
from app.dependencies.tenant_scope import enforce_target_user_same_tenant
from app.models.role_name import RoleName
from app.models.user import User
from app.repositories.tenant_repository import TenantRepository
from app.repositories.user_repository import UserRepository
from app.schemas.common import error_responses
from app.schemas.role import (
    AssignGuestServicesResponse,
    AssignRoleResponse,
    GetUserRolesData,
    GetUserRolesResponse,
    GuestServicesAssignRequest,
    GuestServicesData,
    ListGuestServicesResponse,
    ListRolesResponse,
    RemoveRoleResponse,
    RoleAssignRequest,
    RoleMessageData,
    RoleResponse,
)
from app.services.role_service import RoleService
from app.services.tenant_lifecycle import assert_tenant_admin_assignable

router = APIRouter(
    prefix="/auth/roles",
    tags=["Roles"],
    responses=error_responses(401, 422),
)


@router.get(
    "/list",
    response_model=ListRolesResponse,
    responses=error_responses(403)
)
async def list_roles(
    _admin: User = Depends(require_any_role(RoleName.ADMIN, RoleName.TENANT_ADMIN)),
    svc: RoleService = Depends(get_role_service),
):
    """Return every role in the catalog.

    Requires ADMIN or TENANT_ADMIN.
    """
    roles = await svc.list_roles()
    items = [to_response(r, RoleResponse, json_mode=False) for r in roles]
    return ListRolesResponse(data=items)


@router.post(
    "/assign",
    response_model=AssignRoleResponse,
    responses=error_responses(403, 404)
)
async def assign_role(
    request: Request,
    body: RoleAssignRequest,
    _admin: User = Depends(require_any_role(RoleName.ADMIN, RoleName.TENANT_ADMIN)),
    svc: RoleService = Depends(get_role_service),
    db: AsyncSession = Depends(get_db),
):
    """Assign a role to a user. Existing roles are kept (additive).

    Tenant admins may only act on users in their own tenant. Requires ADMIN
    or TENANT_ADMIN.
    """
    await enforce_target_user_same_tenant(
        request, _admin, body.user_id, db, bypass_roles=(RoleName.ADMIN, RoleName.MODERATOR)
    )
    if body.role_name == RoleName.TENANT_ADMIN:
        target = await UserRepository(db).get_by_id(body.user_id)
        if not target:
            raise EntityNotFoundError(f"User {body.user_id}")
        await assert_tenant_admin_assignable(TenantRepository(db), target.tenant_id)
    await svc.assign_role(body.user_id, body.role_name)
    return AssignRoleResponse(
        data=RoleMessageData(
            message=f"Role '{body.role_name.value}' assigned to user {body.user_id}."
        )
    )


@router.post(
    "/remove",
    response_model=RemoveRoleResponse,
    responses=error_responses(403, 404)
)
async def remove_role(
    request: Request,
    body: RoleAssignRequest,
    _admin: User = Depends(require_any_role(RoleName.ADMIN, RoleName.TENANT_ADMIN)),
    svc: RoleService = Depends(get_role_service),
    db: AsyncSession = Depends(get_db),
):
    """Remove a role from a user.

    Tenant admins may only act on users in their own tenant. Requires ADMIN
    or TENANT_ADMIN. Returns 404 if the user does not have that role.
    """
    await enforce_target_user_same_tenant(
        request, _admin, body.user_id, db, bypass_roles=(RoleName.ADMIN, RoleName.MODERATOR)
    )
    await svc.remove_role(body.user_id, body.role_name)
    return RemoveRoleResponse(
        data=RoleMessageData(
            message=f"Role '{body.role_name.value}' removed from user {body.user_id}."
        )
    )


@router.get(
    "/user/{user_id}",
    response_model=GetUserRolesResponse,
    responses=error_responses(403),
)
async def get_user_roles(
    request: Request,
    user_id: UUID,
    _admin: User = Depends(require_any_role(RoleName.ADMIN, RoleName.TENANT_ADMIN)),
    svc: RoleService = Depends(get_role_service),
    db: AsyncSession = Depends(get_db),
):
    """Return the role names assigned to the given user.

    Tenant admins may only query users in their own tenant. Platform ADMIN
    bypasses tenant scope. Requires ADMIN or TENANT_ADMIN.
    """
    await enforce_target_user_same_tenant(
        request, _admin, user_id, db, bypass_roles=(RoleName.ADMIN,)
    )
    roles = await svc.get_user_roles(user_id)
    return GetUserRolesResponse(
        data=GetUserRolesData(user_id=str(user_id), roles=roles)
    )


@router.post(
    "/assign/guest/services",
    response_model=AssignGuestServicesResponse,
    responses=error_responses(403)
)
async def assign_guest_services(
    body: GuestServicesAssignRequest,
    _admin: User = Depends(require_any_role(RoleName.ADMIN, RoleName.MODERATOR)),
    svc: RoleService = Depends(get_role_service),
):
    """Set which inference services the GUEST role may use.

    Replaces prior managed inference links. Requires ADMIN or MODERATOR.
    """
    assigned = await svc.assign_guest_inference_services(body.services)
    return AssignGuestServicesResponse(data=GuestServicesData(services=assigned))


@router.get(
    "/list/guest/services",
    response_model=ListGuestServicesResponse
)
async def list_guest_services(
    _current_user: User = Depends(get_current_user),
    svc: RoleService = Depends(get_role_service),
):
    """List inference services currently allowed for the GUEST role.

    Any authenticated user may call this.
    """
    services = await svc.list_guest_inference_services()
    return ListGuestServicesResponse(data=GuestServicesData(services=services))
