"""
Tenant ORM model.
"""

import enum
from sqlalchemy import Column, DateTime, Enum, Index, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.models import Base


class TenantStatus(str, enum.Enum):
    PENDING = "PENDING"
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    DEACTIVATED = "DEACTIVATED"


class Tenant(Base):
    __tablename__ = "tenants"

    id = Column(Integer, primary_key=True, autoincrement=True, index=True)
    name = Column(String(255), nullable=False)
    organisation = Column(String(255), nullable=False)
    email = Column(String(255), nullable=False)
    phone_number = Column(String(20), nullable=True)
    status = Column(
        Enum(
            TenantStatus,
            name="tenant_status_enum",
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
        server_default=TenantStatus.PENDING.value,
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    created_by = Column(UUID(as_uuid=True), nullable=True)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    updated_by = Column(UUID(as_uuid=True), nullable=True)

    # Case-insensitive uniqueness on organisation and email, declared so
    # alembic autogenerate treats these indexes as the model's source of truth
    # (created by migrations d4e5f6a7b8c9 and e5f6a7b8c9d0). Without these the
    # drift check would generate a migration to drop them.
    __table_args__ = (
        Index("uq_tenants_organisation_lower", func.lower(organisation), unique=True),
        Index("uq_tenants_email_lower", func.lower(email), unique=True),
    )

    # Relationships
    users = relationship("User", back_populates="tenant")
    tenant_plans = relationship("TenantPlan", back_populates="tenant", cascade="all, delete-orphan")
