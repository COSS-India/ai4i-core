"""
Permission listing routes.
"""

from fastapi import APIRouter, Depends

from app.core.responses import to_response
from app.dependencies.permissions import require_any_role
from app.dependencies.services import get_role_service
from app.core.constants import RoleName
from app.models.user import User
from app.schemas.common import error_responses
from app.schemas.role import (
    InferencePermissionResponse,
    ListInferencePermissionsResponse,
    ListPermissionsResponse,
    PermissionResponse,
    permission_display_label,
)
from app.services.role_service import RoleService

router = APIRouter(
    prefix="/auth/permissions",
    tags=["Permissions"],
    responses=error_responses(401),
)
inference_router = APIRouter(
    prefix="/auth/inference",
    tags=["Permissions"],
    responses=error_responses(401),
)


@router.get(
    "/",
    response_model=ListPermissionsResponse,
    responses=error_responses(403)
)
async def list_permissions(
    _admin: User = Depends(require_any_role(RoleName.ADMIN, RoleName.MODERATOR, RoleName.TENANT_ADMIN)),
    svc: RoleService = Depends(get_role_service),
):
    """Return the full permission catalog.

    Requires ADMIN, MODERATOR, or TENANT_ADMIN.
    """
    permissions = await svc.list_permissions()
    items = [to_response(p, PermissionResponse, json_mode=False) for p in permissions]
    return ListPermissionsResponse(data=items)


@inference_router.get(
    "/permissions",
    response_model=ListInferencePermissionsResponse,
    responses=error_responses(403)
)
async def list_inference_permissions(
    _admin: User = Depends(require_any_role(RoleName.ADMIN, RoleName.MODERATOR, RoleName.TENANT_ADMIN)),
    svc: RoleService = Depends(get_role_service),
):
    """Return slim inference-permission entries for the API-key create UI.

    Each item is `{name, label}` only — no internal DB fields. Requires
    ADMIN, MODERATOR, or TENANT_ADMIN.
    """
    permissions = await svc.list_inference_permissions()
    items = [
        InferencePermissionResponse(name=p.name, label=permission_display_label(p.name))
        for p in permissions
    ]
    return ListInferencePermissionsResponse(data=items)
