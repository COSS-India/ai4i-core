import uuid

from sqlalchemy import Column, DateTime, Numeric, String, func
from sqlalchemy.dialects.postgresql import UUID

from app.models import Base


class UsageRecord(Base):
    __tablename__ = "usage_records"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(String(64), nullable=False, index=True)
    api_key_id = Column(String(64), nullable=False, index=True)
    service_id = Column(String(128), nullable=False, index=True)
    units_consumed = Column(Numeric(20, 6), nullable=False)
    cost = Column(Numeric(20, 6), nullable=False)
    rate_used = Column(Numeric(20, 8), nullable=True)
    tier = Column(String(32), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
