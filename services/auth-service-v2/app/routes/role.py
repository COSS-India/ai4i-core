"""
Role and permission management routes.
"""

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.responses import success_response
from app.dependencies.permissions import require_any_role
from app.dependencies.services import get_role_service
from app.dependencies.tenant_scope import enforce_target_user_same_tenant
from app.models.user import User
from app.schemas.role import GuestServicesAssignRequest, RoleAssignRequest, RoleResponse
from app.services.role_service import RoleService

router = APIRouter(prefix="/auth/roles", tags=["Roles"])


@router.get("/list")
async def list_roles(
    _admin: User = Depends(require_any_role("ADMIN", "MODERATOR", "TENANT ADMIN")),
    svc: RoleService = Depends(get_role_service),
):
    roles = await svc.list_roles()
    items = [RoleResponse.model_validate(r, from_attributes=True).model_dump() for r in roles]
    return success_response(data=items)


@router.post("/assign")
async def assign_role(
    request: Request,
    body: RoleAssignRequest,
    _admin: User = Depends(require_any_role("ADMIN", "TENANT ADMIN")),
    svc: RoleService = Depends(get_role_service),
    db: AsyncSession = Depends(get_db),
):
    await enforce_target_user_same_tenant(
        request, _admin, body.user_id, db, bypass_roles=("ADMIN","MODERATOR")
    )
    await svc.assign_role(body.user_id, body.role_name)
    return success_response(data={"message": f"Role '{body.role_name}' assigned to user {body.user_id}."})


@router.post("/remove")
async def remove_role(
    request: Request,
    body: RoleAssignRequest,
    _admin: User = Depends(require_any_role("ADMIN","TENANT ADMIN")),
    svc: RoleService = Depends(get_role_service),
    db: AsyncSession = Depends(get_db),
):
    await enforce_target_user_same_tenant(
        request, _admin, body.user_id, db, bypass_roles=("ADMIN","MODERATOR")
    )
    await svc.remove_role(body.user_id, body.role_name)
    return success_response(data={"message": f"Role '{body.role_name}' removed from user {body.user_id}."})


@router.get("/user/{user_id}")
async def get_user_roles(
    request: Request,
    user_id: int,
    _admin: User = Depends(require_any_role("ADMIN", "MODERATOR", "TENANT ADMIN")),
    svc: RoleService = Depends(get_role_service),
    db: AsyncSession = Depends(get_db),
):
    await enforce_target_user_same_tenant(
        request, _admin, user_id, db, bypass_roles=("ADMIN", "MODERATOR")
    )
    roles = await svc.get_user_roles(user_id)
    return success_response(data={"user_id": user_id, "roles": roles})


@router.post("/assign/guest/services")
async def assign_guest_services(
    body: GuestServicesAssignRequest,
    _admin: User = Depends(require_any_role("ADMIN", "MODERATOR")),
    svc: RoleService = Depends(get_role_service),
):
    """Set which inference services the GUEST role may use (replaces prior managed inference links)."""
    assigned = await svc.assign_guest_inference_services(body.services)
    return success_response(data={"services": assigned})


@router.get("/list/guest/services")
async def list_guest_services(
    _admin: User = Depends(require_any_role("ADMIN", "MODERATOR")),
    svc: RoleService = Depends(get_role_service),
):
    """List inference service resources currently linked to the GUEST role."""
    services = await svc.list_guest_inference_services()
    return success_response(data={"services": services})
