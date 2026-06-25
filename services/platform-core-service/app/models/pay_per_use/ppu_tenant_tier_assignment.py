import uuid

from sqlalchemy import Column, DateTime, ForeignKey, Numeric, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.models import Base


class PPUTenantTierAssignment(Base):
    __tablename__ = "ppu_tenant_tier_assignments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(String(255), nullable=False, index=True)
    tier_id = Column(
        UUID(as_uuid=True),
        ForeignKey("ppu_tiers.id"),
        nullable=False,
        index=True,
    )
    budget_limit = Column(Numeric(15, 4), nullable=False)
    available_balance = Column(Numeric(15, 4), nullable=False)
    effective_from = Column(DateTime(timezone=True), nullable=False)
    effective_to = Column(DateTime(timezone=True), nullable=False)
    created_by = Column(String(255), nullable=True)
    updated_by = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    tier = relationship("PPUTier", back_populates="tenant_assignments")
