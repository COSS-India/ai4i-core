import uuid

from sqlalchemy import Column, DateTime, ForeignKey, Integer, Numeric, String, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.models import Base


class TenantPlan(Base):
    __tablename__ = "tenant_plans"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, nullable=False)
    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    plan_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    plan_name = Column(String(128), nullable=False)
    tier = Column(String(32), nullable=False)
    plan_cost = Column(Numeric(12, 2), nullable=True)
    quota_config = Column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    rate_limit_config = Column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    allowed_services = Column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    assigned_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    tenant = relationship("Tenant", back_populates="tenant_plans")
