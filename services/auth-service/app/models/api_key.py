"""
APIKey ORM model.
"""

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, JSON, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.models import Base


class APIKey(Base):
    __tablename__ = "api_key"

    id = Column(Integer, primary_key=True, autoincrement=True, index=True)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    key_name = Column(String(100), nullable=False)
    # 32-char hex string — unique identifier returned to the caller.
    api_key = Column(String(32), unique=True, index=True, nullable=False)
    # Flat list of permission IDs: [1, 2, 3]
    permissions = Column(JSON, default=list, nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    created_by = Column(UUID(as_uuid=True), nullable=True)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    updated_by = Column(UUID(as_uuid=True), nullable=True)

    user = relationship("User", back_populates="api_keys")
