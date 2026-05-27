import uuid

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.models import Base


class QuotaConfig(Base):
    __tablename__ = "quota_configs"
    __table_args__ = (UniqueConstraint("name", name="uq_quota_configs_name"),)

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False, unique=True, index=True)
    requests_per_hour = Column(Integer, nullable=False)
    created_at = Column(DateTime(timezone=False), nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime(timezone=False),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

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
    updated_at = Column(
        DateTime(timezone=False),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    quota_config = relationship("QuotaConfig", back_populates="service_limit_rows")
