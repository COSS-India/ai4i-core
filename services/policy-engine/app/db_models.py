import uuid

from sqlalchemy import Column, DateTime, ForeignKey, Integer, Numeric, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import declarative_base, relationship


Base = declarative_base()


class TenantPolicy(Base):
    __tablename__ = "smr_tenant_policies"

    tenant_id = Column(String(50), primary_key=True)
    latency_policy = Column(String(20), nullable=False, server_default="medium")
    cost_policy = Column(String(20), nullable=False, server_default="tier_2")
    accuracy_policy = Column(String(20), nullable=False, server_default="standard")
    created_at = Column(DateTime(timezone=False), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=False), nullable=False, server_default=func.now())


class QuotaConfig(Base):
    __tablename__ = "quota_configs"
    __table_args__ = (UniqueConstraint("name", name="uq_quota_configs_name"),)

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False, unique=True, index=True)
    requests_per_hour = Column(Integer, nullable=False)
    created_at = Column(DateTime(timezone=False), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=False), nullable=False, server_default=func.now(), onupdate=func.now())

    service_limit_rows = relationship(
        "QuotaServiceLimit",
        back_populates="quota_config",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class QuotaServiceLimit(Base):
    __tablename__ = "quota_service_limits"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    quota_config_id = Column(
        UUID(as_uuid=True),
        ForeignKey("quota_configs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    service_type = Column(String(64), nullable=False)
    unit_type = Column(String(64), nullable=False)
    limit_value = Column(Integer, nullable=False)
    created_at = Column(DateTime(timezone=False), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=False), nullable=False, server_default=func.now(), onupdate=func.now())

    quota_config = relationship("QuotaConfig", back_populates="service_limit_rows")


class RateLimitConfig(Base):
    __tablename__ = "rate_limit_configs"
    __table_args__ = (UniqueConstraint("name", name="uq_rate_limit_configs_name"),)

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False, unique=True, index=True)
    requests_per_hour_per_api_key = Column(Integer, nullable=False)
    requests_per_hour_per_tenant = Column(Integer, nullable=False)
    created_at = Column(DateTime(timezone=False), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=False), nullable=False, server_default=func.now(), onupdate=func.now())


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
    rate_limit_config_id = Column(UUID(as_uuid=True), ForeignKey("rate_limit_configs.id"), nullable=False)
    created_at = Column(DateTime(timezone=False), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=False), nullable=False, server_default=func.now(), onupdate=func.now())
