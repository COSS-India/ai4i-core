"""
Role and permission schemas.
"""

from datetime import datetime
from typing import Optional

from pydantic import Field

from app.schemas.base import BaseSchema


class RoleResponse(BaseSchema):
    id: int
    name: str
    description: Optional[str] = None
    created_at: datetime


class PermissionResponse(BaseSchema):
    id: int
    name: str
    resource: str
    action: str
    created_at: datetime


class RoleAssignRequest(BaseSchema):
    user_id: int
    role_name: str = Field(..., min_length=1, max_length=100)


class RoleRemoveRequest(BaseSchema):
    user_id: int
    role_name: str


class GuestServicesAssignRequest(BaseSchema):
    """Replace GUEST role inference permissions; other GUEST permissions are unchanged."""

    services: list[str] = Field(default_factory=list)
