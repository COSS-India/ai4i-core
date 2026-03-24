"""
Role and permission management routes.
"""

from fastapi import APIRouter, Depends

from app.core.responses import success_response
from app.dependencies.permissions import require_any_role
from app.dependencies.services import get_role_service
from app.models.user import User
from app.schemas.role import PermissionResponse, RoleAssignRequest, RoleResponse
from app.services.role_service import RoleService

router = APIRouter(prefix="/auth/roles", tags=["Roles"])


@router.get("/list")
async def list_roles(
    _admin: User = Depends(require_any_role("ADMIN", "MODERATOR")),
    svc: RoleService = Depends(get_role_service),
):
    roles = await svc.list_roles()
    items = [RoleResponse.model_validate(r, from_attributes=True).model_dump() for r in roles]
    return success_response(data=items)


@router.post("/assign")
async def assign_role(
    body: RoleAssignRequest,
    _admin: User = Depends(require_any_role("ADMIN")),
    svc: RoleService = Depends(get_role_service),
):
    await svc.assign_role(body.user_id, body.role_name)
    return success_response(data={"message": f"Role '{body.role_name}' assigned to user {body.user_id}."})


@router.post("/remove")
async def remove_role(
    body: RoleAssignRequest,
    _admin: User = Depends(require_any_role("ADMIN")),
    svc: RoleService = Depends(get_role_service),
):
    await svc.remove_role(body.user_id, body.role_name)
    return success_response(data={"message": f"Role '{body.role_name}' removed from user {body.user_id}."})


@router.get("/user/{user_id}")
async def get_user_roles(
    user_id: int,
    _admin: User = Depends(require_any_role("ADMIN", "MODERATOR")),
    svc: RoleService = Depends(get_role_service),
):
    roles = await svc.get_user_roles(user_id)
    return success_response(data={"user_id": user_id, "roles": roles})
