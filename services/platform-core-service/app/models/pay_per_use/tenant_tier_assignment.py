import uuid

from sqlalchemy import Column, DateTime, ForeignKey, Index, Numeric, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.models import Base


class TenantTierAssignment(Base):
    __tablename__ = "ppu_tenant_tier_assignments"  # ppu_ prefix kept intentionally; billing writes this table (_upsert_ppu_tenant_tier_assignment, #1488) — do not rename
    __table_args__ = (
        Index(
            "ix_ppu_tenant_tier_assignments_tenant_effective",
            "tenant_id", "effective_from", "effective_to",
        ),
        Index(
            "ix_ppu_tenant_tier_assignments_effective_window",
            "effective_from", "effective_to",
        ),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(String(255), nullable=False)
    tier_id = Column(
        UUID(as_uuid=True),
        ForeignKey("tiers.id"),
        nullable=False,
        index=True,
    )
    budget_limit = Column(Numeric(15, 8), nullable=False)
    available_balance = Column(Numeric(15, 8), nullable=False)
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

    tier = relationship("Tier", back_populates="tenant_assignments")
