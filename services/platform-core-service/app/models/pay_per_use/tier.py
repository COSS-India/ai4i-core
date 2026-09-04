import uuid

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.models import Base


class Tier(Base):
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
        "TierQuota",
        back_populates="tier",
        cascade="all, delete-orphan",
    )


class TierQuota(Base):
    __tablename__ = "tier_quotas"
    # Both constraints are listed on purpose. The id-keyed one is what the
    # consumer now conflicts on; the name-keyed one is still on the table until
    # inference_name is dropped, and autogenerate would propose removing whichever
    # it could not see here.
    __table_args__ = (
        UniqueConstraint("tier_id", "inference_name", name="uq_tier_quotas_tier_inference"),
        UniqueConstraint("tier_id", "inference_type_id", name="uq_tier_quotas_tier_inference_type"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tier_id = Column(
        UUID(as_uuid=True),
        ForeignKey("tiers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    inference_name = Column(String(64), nullable=False)
    # NOT NULL from phase 2 on. UNIQUE (tier_id, inference_type_id) would be
    # toothless against a nullable column, since NULL never equals NULL in a
    # unique index. A NULL row would also be a dead quota — the consumer's join
    # cannot match it, so the tier would silently grant nothing.
    inference_type_id = Column(
        Integer,
        ForeignKey("inference_types.id"),
        nullable=False,
        index=True,
    )
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

    tier = relationship("Tier", back_populates="tier_quotas")
