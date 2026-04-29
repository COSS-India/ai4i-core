"""
Tenant ORM model.
"""

import enum
from sqlalchemy import Column, DateTime, Enum, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.models import Base


class TenantStatus(str, enum.Enum):
    ACTIVATED = "activated"
    DEACTIVATED = "deactivated"
    SUSPENDED = "suspended"


class Tenant(Base):
    __tablename__ = "tenants"

    id = Column(Integer, primary_key=True, autoincrement=True, index=True)
    name = Column(String(255), nullable=False)
    organisation = Column(String(255), nullable=False)
    email = Column(String(255), nullable=False)
    phone_number = Column(String(20), nullable=True)
    status = Column(
        Enum(TenantStatus, name="tenant_status_enum", values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        server_default=TenantStatus.ACTIVATED.value,
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    created_by = Column(UUID(as_uuid=True), nullable=True)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    updated_by = Column(UUID(as_uuid=True), nullable=True)

    # Relationships
    users = relationship("User", back_populates="tenant")
