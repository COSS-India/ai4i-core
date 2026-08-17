"""
Role, Permission, UserRole, and RolePermission schemas.
"""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import AliasChoices, Field

from app.models.role_name import RoleName
from app.schemas.base import BaseSchema
from app.schemas.common import SuccessResponse


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


class RoleAssignRequest(BaseSchema):
    user_id: UUID
    role_name: RoleName


class GuestServicesAssignRequest(BaseSchema):
    """Replace GUEST role inference permissions; other GUEST permissions are unchanged."""
    services: list[str] = Field(default_factory=list)


class ListPermissionsResponse(SuccessResponse):
    """GET /auth/permissions/"""

    data: list[PermissionResponse]


class ListInferencePermissionsResponse(SuccessResponse):
    """GET /auth/inference/permissions"""

    data: list[InferencePermissionResponse]
