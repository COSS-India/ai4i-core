"""
Permission listing routes.
"""

from fastapi import APIRouter, Depends

from app.core.responses import success_response
from app.dependencies.permissions import require_any_role
from app.dependencies.services import get_role_service
from app.models.user import User
from app.schemas.role import PermissionResponse
from app.services.role_service import RoleService

router = APIRouter(prefix="/auth/permissions", tags=["Permissions"])
inference_router = APIRouter(prefix="/auth/inference", tags=["Permissions"])


@router.get("/")
async def list_permissions(
    _admin: User = Depends(require_any_role("ADMIN", "MODERATOR", "TENANT ADMIN")),
    svc: RoleService = Depends(get_role_service),
):
    permissions = await svc.list_permissions()
    items = [PermissionResponse.model_validate(p, from_attributes=True).model_dump() for p in permissions]
    return success_response(data=items)


@inference_router.get("/permissions")
async def list_inference_permissions(
    _admin: User = Depends(require_any_role("ADMIN", "MODERATOR", "TENANT ADMIN")),
    svc: RoleService = Depends(get_role_service),
):
    permissions = await svc.list_inference_permissions()
    items = [PermissionResponse.model_validate(p, from_attributes=True).model_dump() for p in permissions]
    return success_response(data=items)
