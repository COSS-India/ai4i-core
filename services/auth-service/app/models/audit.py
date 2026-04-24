"""
AuditLog ORM model.
"""

import enum

from sqlalchemy import Column, DateTime, Enum, Integer, JSON, String
from sqlalchemy.sql import func

from app.models import Base


class AuditEntityType(str, enum.Enum):
    USER = "USER"
    ROLE = "ROLE"
    TENANT = "TENANT"
    API_KEY = "API_KEY"


class AuditEntityAction(str, enum.Enum):
    CREATE = "CREATE"
    UPDATE = "UPDATE"
    DELETE = "DELETE"


class AuditLog(Base):
    __tablename__ = "audit"

    id = Column(Integer, primary_key=True, index=True)
    entity_type = Column(
        Enum(AuditEntityType, name="audit_entity_type_enum"),
        nullable=False,
        index=True,
    )
    entity_action = Column(
        Enum(AuditEntityAction, name="audit_entity_action_enum"),
        nullable=False,
        index=True,
    )
    details = Column(JSON, nullable=True)
    subject = Column(String(255), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    created_by = Column(String(255), nullable=True)
