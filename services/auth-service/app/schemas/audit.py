"""
AuditLog request/response schemas.
"""

from datetime import datetime
from enum import Enum
from typing import Optional

from app.schemas.base import BaseSchema


class AuditEntityType(str, Enum):
    USER = "USER"
    ROLE = "ROLE"
    TENANT = "TENANT"
    API_KEY = "API_KEY"


class AuditEntityAction(str, Enum):
    CREATE = "CREATE"
    UPDATE = "UPDATE"
    DELETE = "DELETE"


class AuditLogResponse(BaseSchema):
    id: int
    entity_type: AuditEntityType
    entity_action: AuditEntityAction
    details: Optional[dict] = None
    subject: Optional[str] = None
    created_at: datetime
    created_by: Optional[str] = None


class AuditLogCreate(BaseSchema):
    entity_type: AuditEntityType
    entity_action: AuditEntityAction
    subject: Optional[str] = None
    details: Optional[dict] = None
