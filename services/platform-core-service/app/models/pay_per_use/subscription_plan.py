import uuid

from sqlalchemy import Column, DateTime, ForeignKey, Numeric, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID

from app.models import Base


class SubscriptionPlan(Base):
    """Subscription plan (policy): unique tier, links quota + rate configs by matching name."""

    __tablename__ = "subscription_plans"
    __table_args__ = (
        UniqueConstraint("plan_name", name="uq_subscription_plans_plan_name"),
        UniqueConstraint("tier", name="uq_subscription_plans_tier"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    plan_name = Column(String(128), nullable=False)
    cost = Column(Numeric(12, 2), nullable=False, server_default="100.00")
    tier = Column(String(20), nullable=False, index=True)
    quota_config_id = Column(UUID(as_uuid=True), ForeignKey("quota_configs.id"), nullable=False)
    rate_limit_config_id = Column(
        UUID(as_uuid=True), ForeignKey("rate_limit_configs.id"), nullable=False
    )
    created_at = Column(DateTime(timezone=False), nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime(timezone=False),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
