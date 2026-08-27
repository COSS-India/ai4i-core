import uuid

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.models import Base


class PPUTier(Base):
    __tablename__ = "tiers"
    __table_args__ = (
        UniqueConstraint("name", name="uq_tiers_name"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True, server_default="true")
    created_by = Column(String(255), nullable=True)
    updated_by = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    tier_quotas = relationship(
        "PPUTierQuota",
        back_populates="tier",
        cascade="all, delete-orphan",
    )
    tenant_assignments = relationship("PPUTenantTierAssignment", back_populates="tier")


class PPUTierQuota(Base):
    __tablename__ = "tier_quotas"
    __table_args__ = (
        UniqueConstraint("tier_id", "inference_name", name="uq_tier_quotas_tier_inference"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tier_id = Column(
        UUID(as_uuid=True),
        ForeignKey("tiers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    inference_name = Column(String(64), nullable=False)
    monthly_quota = Column(Numeric(15, 4), nullable=False)
    pending_monthly_quota = Column(Numeric(15, 4), nullable=True)
    created_by = Column(String(255), nullable=True)
    updated_by = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    tier = relationship("PPUTier", back_populates="tier_quotas")
