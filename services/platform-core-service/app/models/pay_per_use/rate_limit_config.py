import uuid

from sqlalchemy import Column, DateTime, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID

from app.models import Base


class RateLimitConfig(Base):
    __tablename__ = "rate_limit_configs"
    __table_args__ = (UniqueConstraint("name", name="uq_rate_limit_configs_name"),)

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False, unique=True, index=True)
    requests_per_hour_per_api_key = Column(Integer, nullable=False)
    requests_per_hour_per_tenant = Column(Integer, nullable=False)
    created_at = Column(DateTime(timezone=False), nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime(timezone=False),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
