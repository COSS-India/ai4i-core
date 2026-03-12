from sqlalchemy import Column, DateTime, String, func
from sqlalchemy.orm import declarative_base


Base = declarative_base()


class TenantPolicy(Base):
    __tablename__ = "smr_tenant_policies"

    tenant_id = Column(String(50), primary_key=True)
    latency_policy = Column(String(20), nullable=False, server_default="medium")
    cost_policy = Column(String(20), nullable=False, server_default="tier_2")
    accuracy_policy = Column(String(20), nullable=False, server_default="standard")
    created_at = Column(DateTime(timezone=False), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=False), nullable=False, server_default=func.now())
