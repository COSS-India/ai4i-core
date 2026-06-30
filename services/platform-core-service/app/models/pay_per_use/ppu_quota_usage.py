import uuid

from sqlalchemy import BigInteger, Column, DateTime, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.models import Base


class PPUQuotaUsage(Base):
    __tablename__ = "ppu_quota_usage"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "inference_name",
            "billing_month",
            name="uq_ppu_quota_usage_tenant_inference_month",
        ),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(String(255), nullable=False, index=True)
    inference_name = Column(String(64), nullable=False, index=True)
    billing_month = Column(String(7), nullable=False)
    monthly_quota_snap = Column(BigInteger, nullable=True)
    units_used = Column(BigInteger, nullable=False, default=0, server_default="0")
    created_by = Column(String(255), nullable=True)
    updated_by = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
