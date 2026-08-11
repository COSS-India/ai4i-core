"""
Role and permission management routes.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.exceptions import EntityNotFoundError
from app.core.responses import success_response, to_response
from app.dependencies.auth import get_current_user
from app.dependencies.permissions import require_any_role
from app.dependencies.services import get_role_service
from app.dependencies.tenant_scope import enforce_target_user_same_tenant
from app.models.role_name import RoleName
from app.models.user import User
from app.repositories.tenant_repository import TenantRepository
from app.repositories.user_repository import UserRepository
from app.schemas.role import GuestServicesAssignRequest, RoleAssignRequest, RoleResponse
from app.services.role_service import RoleService
from app.services.tenant_lifecycle import assert_tenant_admin_assignable

router = APIRouter(prefix="/auth/roles", tags=["Roles"])


@router.get("/list")
async def list_roles(
    _admin: User = Depends(require_any_role(RoleName.ADMIN, RoleName.TENANT_ADMIN)),
    svc: RoleService = Depends(get_role_service),
):
    roles = await svc.list_roles()
    items = [to_response(r, RoleResponse, json_mode=False) for r in roles]
    return success_response(data=items)


@router.post("/assign")
async def assign_role(
    request: Request,
    body: RoleAssignRequest,
    _admin: User = Depends(require_any_role(RoleName.ADMIN, RoleName.TENANT_ADMIN)),
    svc: RoleService = Depends(get_role_service),
    db: AsyncSession = Depends(get_db),
):
    await enforce_target_user_same_tenant(
        request, _admin, body.user_id, db, bypass_roles=(RoleName.ADMIN, RoleName.MODERATOR)
    )
    if body.role_name == RoleName.TENANT_ADMIN:
        target = await UserRepository(db).get_by_id(body.user_id)
        if not target:
            raise EntityNotFoundError(f"User {body.user_id}")
        await assert_tenant_admin_assignable(TenantRepository(db), target.tenant_id)
    await svc.assign_role(body.user_id, body.role_name)
    return success_response(data={"message": f"Role '{body.role_name.value}' assigned to user {body.user_id}."})


@router.post("/remove")
async def remove_role(
    request: Request,
    body: RoleAssignRequest,
    _admin: User = Depends(require_any_role(RoleName.ADMIN, RoleName.TENANT_ADMIN)),
    svc: RoleService = Depends(get_role_service),
    db: AsyncSession = Depends(get_db),
):
    await enforce_target_user_same_tenant(
        request, _admin, body.user_id, db, bypass_roles=(RoleName.ADMIN, RoleName.MODERATOR)
    )
    await svc.remove_role(body.user_id, body.role_name)
    return success_response(data={"message": f"Role '{body.role_name.value}' removed from user {body.user_id}."})


@router.get("/user/{user_id}")
async def get_user_roles(
    request: Request,
    user_id: UUID,
    _admin: User = Depends(require_any_role(RoleName.ADMIN, RoleName.TENANT_ADMIN)),
    svc: RoleService = Depends(get_role_service),
    db: AsyncSession = Depends(get_db),
):
    await enforce_target_user_same_tenant(
        request, _admin, user_id, db, bypass_roles=(RoleName.ADMIN,)
    )
    roles = await svc.get_user_roles(user_id)
    return success_response(data={"user_id": str(user_id), "roles": roles})


@router.post("/assign/guest/services")
async def assign_guest_services(
    body: GuestServicesAssignRequest,
    _admin: User = Depends(require_any_role(RoleName.ADMIN, RoleName.MODERATOR)),
    svc: RoleService = Depends(get_role_service),
):
    """Set which inference services the GUEST role may use (replaces prior managed inference links)."""
    assigned = await svc.assign_guest_inference_services(body.services)
    return success_response(data={"services": assigned})


@router.get("/list/guest/services")
async def list_guest_services(
    _current_user: User = Depends(get_current_user),
    svc: RoleService = Depends(get_role_service),
):
    """List GUEST-role inference services."""
    services = await svc.list_guest_inference_services()
    return success_response(data={"services": services})
