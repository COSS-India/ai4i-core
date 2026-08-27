"""
Tenant ORM model.
"""

import enum
from sqlalchemy import Column, DateTime, Enum, Index, Integer, Numeric, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.models import Base
from app.models.types import EncryptedEmail, EncryptedPhone


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
    email = Column(EncryptedEmail(), nullable=False)
    phone_number = Column(EncryptedPhone(), nullable=True)
    status = Column(
        Enum(
            TenantStatus,
            name="tenant_status_enum",
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
        server_default=TenantStatus.PENDING.value,
    )
    tier_id = Column(UUID(as_uuid=True), nullable=True)
    allocated_budget = Column(Numeric(15, 8), nullable=True)
    budget_effective_from = Column(DateTime(timezone=True), nullable=True)
    budget_effective_to = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    created_by = Column(UUID(as_uuid=True), nullable=True)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    updated_by = Column(UUID(as_uuid=True), nullable=True)

    # Case-insensitive uniqueness on organisation (created by migration
    # d4e5f6a7b8c9). Email is now stored as deterministic, lower-normalised
    # ciphertext, so uniqueness is enforced by a plain unique index on the
    # encrypted value (the expression index uq_tenants_email_lower was replaced
    # by uq_tenants_email — see the encrypt-pii migration). Both are declared
    # here so alembic autogenerate treats them as the source of truth.
    __table_args__ = (
        Index("uq_tenants_organisation_lower", func.lower(organisation), unique=True),
        Index("uq_tenants_email", email, unique=True),
    )

    # Relationships
    users = relationship("User", back_populates="tenant")
    tenant_plans = relationship("TenantPlan", back_populates="tenant", cascade="all, delete-orphan")
    applications = relationship("Application", back_populates="tenant", cascade="save-update, merge")
