"""
APIKey ORM model.
"""

from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, Integer, JSON, Numeric, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.models import Base


class APIKey(Base):
    __tablename__ = "api_key"
    __table_args__ = (
        Index("ix_api_key_cached_data_gin", "cached_data", postgresql_using="gin"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True, index=True)
    application_id = Column(
        Integer,
        ForeignKey("applications.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    key_name = Column(String(100), nullable=False)
    # 32-char hex string — unique identifier returned to the caller.
    api_key = Column(String(32), unique=True, index=True, nullable=False)
    allocated_percentage = Column(Numeric(5, 2), nullable=True)
    allocated_budget = Column(Numeric(15, 2), nullable=True)
    # Flat list of permission IDs: [1, 2, 3]
    permissions = Column(JSON, default=list, nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    created_by = Column(UUID(as_uuid=True), nullable=True)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    updated_by = Column(UUID(as_uuid=True), nullable=True)
    cached_data = Column(JSONB, nullable=True)

    application = relationship("Application", back_populates="api_keys")

    def is_expired(self) -> bool:
        """True when ``expires_at`` is in the past. Revocation uses ``is_active``."""
        if self.expires_at is None:
            return False
        return datetime.now(timezone.utc) > self.expires_at

    def __repr__(self) -> str:
        return f"<APIKey id={self.id} name={self.key_name!r} expired={self.is_expired()}>"
