"""
Tenant ORM model.
"""

import uuid

from sqlalchemy import Column, DateTime, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.models import Base


class Tenant(Base):
    __tablename__ = "tenants"

    tenant_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    organisation = Column(String(255), nullable=False)
    org_email = Column(String(255), nullable=False)
    org_phone_number = Column(String(20), nullable=True)
    status = Column(String(50), nullable=False, server_default="active")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    created_by = Column(String(255), nullable=True)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    updated_by = Column(String(255), nullable=True)

    # Relationships
    users = relationship("User", back_populates="tenant")
    api_keys = relationship("APIKey", back_populates="tenant", cascade="all, delete-orphan")
