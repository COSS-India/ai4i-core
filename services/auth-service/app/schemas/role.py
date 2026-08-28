"""
Role, Permission, UserRole, and RolePermission schemas.
"""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import AliasChoices, ConfigDict, Field

from app.core.constants import RoleName
from app.schemas.base import BaseSchema
from app.schemas.common import MessageData, SuccessResponse


class RoleResponse(BaseSchema):
    role_id: int = Field(validation_alias=AliasChoices("role_id", "id"))
    name: RoleName
    description: Optional[str] = None
    created_at: datetime
    created_by: Optional[UUID] = None
    updated_at: Optional[datetime] = None
    updated_by: Optional[UUID] = None


class PermissionResponse(BaseSchema):
    permission_id: int = Field(validation_alias=AliasChoices("permission_id", "id"), serialization_alias="id")
    name: str
    resource: str
    action: str
    created_at: datetime
    created_by: Optional[UUID] = None
    updated_at: Optional[datetime] = None
    updated_by: Optional[UUID] = None


def permission_display_label(name: str) -> str:
    """Human-readable label for a stable permission name (e.g. nmt.inference → NMT.INFERENCE)."""
    return name.upper()


class InferencePermissionResponse(BaseSchema):
    """Slim catalog entry for API-key create UI — no internal DB fields."""
    name: str
    label: str


_ROLE_ASSIGN_REQUEST_EXAMPLE = {
    "user_id": "<place your uuid here>",
    "role_name": "USER",
}


class RoleAssignRequest(BaseSchema):
    model_config = ConfigDict(json_schema_extra={"example": _ROLE_ASSIGN_REQUEST_EXAMPLE})

    user_id: UUID
    role_name: RoleName


_GUEST_SERVICES_ASSIGN_REQUEST_EXAMPLE = {
    "services": ["nmt.inference", "asr.inference"],
}


class GuestServicesAssignRequest(BaseSchema):
    """Replace GUEST role inference permissions; other GUEST permissions are unchanged."""

    model_config = ConfigDict(json_schema_extra={"example": _GUEST_SERVICES_ASSIGN_REQUEST_EXAMPLE})

    services: list[str] = Field(default_factory=list)


class GetUserRolesData(BaseSchema):
    user_id: str
    roles: list[str]


class GuestServicesData(BaseSchema):
    services: list[str]


class ListRolesResponse(SuccessResponse):
    """GET /auth/roles/list"""

    data: list[RoleResponse]


class AssignRoleResponse(SuccessResponse):
    """POST /auth/roles/assign"""

    data: MessageData


class RemoveRoleResponse(SuccessResponse):
    """POST /auth/roles/remove"""

    data: MessageData


class GetUserRolesResponse(SuccessResponse):
    """GET /auth/roles/user/{user_id}"""

    data: GetUserRolesData


class AssignGuestServicesResponse(SuccessResponse):
    """POST /auth/roles/assign/guest/services"""

    data: GuestServicesData


class ListGuestServicesResponse(SuccessResponse):
    """GET /auth/roles/list/guest/services"""

    data: GuestServicesData



class ListPermissionsResponse(SuccessResponse):
    """GET /auth/permissions/"""

    data: list[PermissionResponse]


class ListInferencePermissionsResponse(SuccessResponse):
    """GET /auth/inference/permissions"""

    data: list[InferencePermissionResponse]
