"""
Role, Permission, UserRole, and RolePermission schemas.
"""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import AliasChoices, Field

from app.schemas.base import BaseSchema


class RoleCreate(BaseSchema):
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None


class RoleUpdate(BaseSchema):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = None


class RoleResponse(BaseSchema):
    role_id: int = Field(validation_alias=AliasChoices("role_id", "id"))
    name: str
    description: Optional[str] = None
    created_at: datetime
    created_by: Optional[UUID] = None
    updated_at: Optional[datetime] = None
    updated_by: Optional[UUID] = None


class PermissionResponse(BaseSchema):
    permission_id: int = Field(validation_alias=AliasChoices("permission_id", "id"))
    name: str
    resource: str
    action: str
    created_at: datetime
    created_by: Optional[UUID] = None
    updated_at: Optional[datetime] = None
    updated_by: Optional[UUID] = None


class UserRoleResponse(BaseSchema):
    id: int
    user_id: UUID
    role_id: int
    created_at: datetime
    created_by: Optional[UUID] = None
    updated_at: Optional[datetime] = None
    updated_by: Optional[UUID] = None


class RolePermissionResponse(BaseSchema):
    id: int
    role_id: int
    permission_id: int
    created_at: datetime
    created_by: Optional[UUID] = None
    updated_at: Optional[datetime] = None
    updated_by: Optional[UUID] = None


class RoleAssignRequest(BaseSchema):
    user_id: UUID
    role_name: str = Field(..., min_length=1, max_length=100)


class RoleRemoveRequest(BaseSchema):
    user_id: UUID
    role_name: str


class RolePermissionAssignRequest(BaseSchema):
    role_id: int
    permission_id: int


class GuestServicesAssignRequest(BaseSchema):
    """Replace GUEST role inference permissions; other GUEST permissions are unchanged."""
    services: list[str] = Field(default_factory=list)
