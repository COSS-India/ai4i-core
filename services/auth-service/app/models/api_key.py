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

    key_id = Column(Integer, primary_key=True, index=True)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.user_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    key_name = Column(String(100), nullable=False)
    # Stores the token_id UUID used as the JWT token_id claim for revocation lookups.
    api_key = Column(String(500), unique=True, index=True, nullable=False)
    # JSON: {"permission": [1, 2, 3]} — permission IDs from the permissions table.
    permissions = Column(JSON, default=dict, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    created_by = Column(String(255), nullable=True)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    updated_by = Column(String(255), nullable=True)

    user = relationship("User", back_populates="api_keys")
