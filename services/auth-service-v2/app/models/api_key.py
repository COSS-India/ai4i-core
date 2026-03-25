"""
APIKey ORM model — JWT-based API keys with token_id.
"""

from sqlalchemy import Boolean, Column, DateTime, Integer, JSON, String
from sqlalchemy.sql import func

from app.models import Base


class APIKey(Base):
    __tablename__ = "api_keys"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=False, index=True)
    key_name = Column(String(100), nullable=False)
    token_id = Column(String(36), unique=True, index=True, nullable=False)
    permissions = Column(JSON, default=list)
    is_active = Column(Boolean, default=True)
    is_revoked = Column(Boolean, default=False)
    status = Column(String(20), default="active")
    last_used = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    expires_at = Column(DateTime(timezone=True), nullable=True)
