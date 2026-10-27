"""
APIKey ORM model.
"""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, Integer, JSON, Numeric, String, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.models import Base


class APIKey(Base):
    __tablename__ = "api_key"
    __table_args__ = (
        Index("ix_api_key_cached_data_gin", "cached_data", postgresql_using="gin"),
        Index(
            "uq_api_key_rotated_key",
            "rotated_key",
            unique=True,
            postgresql_where=text("rotated_key IS NOT NULL"),
        ),
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
    # The value api_key held before the last rotation. It keeps authenticating
    # as this same row (same id, budget, permissions) until
    # rotated_key_expires_at, or until the whole key is revoked.
    rotated_key = Column(String(32), nullable=True)
    rotated_key_expires_at = Column(DateTime(timezone=True), nullable=True)
    # When api_key last got a new value, i.e. when the current value was issued.
    rotated_at = Column(DateTime(timezone=True), nullable=True)

    application = relationship("Application", back_populates="api_keys")

    def is_expired(self) -> bool:
        """True when ``expires_at`` is in the past. Revocation uses ``is_active``."""
        if self.expires_at is None:
            return False
        return datetime.now(timezone.utc) > self.expires_at

    def live_rotated_key(self) -> Optional[str]:
        """The previous key value while it still authenticates, else None."""
        if (
            self.rotated_key
            and self.rotated_key_expires_at is not None
            and self.rotated_key_expires_at > datetime.now(timezone.utc)
        ):
            return self.rotated_key
        return None

    def live_rotated_key_expires_at(self) -> Optional[datetime]:
        """When the previous value stops, only while it actually still works:
        the key itself must be active and unexpired too. None otherwise —
        a revoked or expired key has no live value at all."""
        if self.is_active and not self.is_expired() and self.live_rotated_key():
            return self.rotated_key_expires_at
        return None

    def cache_key_values(self) -> list[str]:
        """Every key value with a Redis entry to keep in step: api_key, plus
        the rotated key while it is live."""
        rotated = self.live_rotated_key()
        return [self.api_key, rotated] if rotated else [self.api_key]

    def __repr__(self) -> str:
        return f"<APIKey id={self.id} name={self.key_name!r} expired={self.is_expired()}>"
