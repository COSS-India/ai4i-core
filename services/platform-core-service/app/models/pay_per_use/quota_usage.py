import uuid

from sqlalchemy import Column, DateTime, Integer, Numeric, String, func
from sqlalchemy.dialects.postgresql import UUID

from app.models import Base


class QuotaUsage(Base):
    __tablename__ = "quota_usage"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(String(64), nullable=False, index=True)
    service_id = Column(String(128), nullable=False, index=True)
    period = Column(String(16), nullable=False)
    requests_used = Column(Integer, nullable=False, default=0)
    units_used = Column(Numeric(20, 6), nullable=False, default=0)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
