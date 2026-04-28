"""
TokenVerification ORM model.
"""

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.models import Base


class TokenVerification(Base):
    __tablename__ = "token_verification"

    id = Column(Integer, primary_key=True, autoincrement=True, index=True)
    token = Column(Text, unique=True, index=True, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    created_by = Column(UUID(as_uuid=True), nullable=True)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    updated_by = Column(UUID(as_uuid=True), nullable=True)
