import uuid

from sqlalchemy import Column, DateTime, ForeignKey, Index, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.models import Base


class QuotaUsage(Base):
    __tablename__ = "quota_usage"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "inference_name",
            "billing_month",
            "tier_id",
            name="uq_quota_usage_tenant_inference_month_tier",
        ),
        Index(
            "ix_quota_usage_billing_month_tenant",
            "billing_month", "tenant_id",
        ),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(String(255), nullable=False, index=True)
    inference_name = Column(String(64), nullable=False, index=True)
    billing_month = Column(String(7), nullable=False)
    monthly_quota_snap = Column(Numeric(15, 4), nullable=True)
    monthly_quota_used = Column(Numeric(15, 4), nullable=False, default=0, server_default="0")
    tier_id = Column(
        UUID(as_uuid=True),
        ForeignKey("tiers.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_by = Column(String(255), nullable=True)
    updated_by = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
