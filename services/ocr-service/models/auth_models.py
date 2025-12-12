"""
Auth models for OCR service.

Mirrors the structure used in ASR/NMT services so shared auth tables
(`users`, `api_keys`, `sessions`) can be reused for API key validation.
"""

from sqlalchemy import Column, String, Integer, Boolean, DateTime, ForeignKey, Text, func
from sqlalchemy.orm import relationship

from .database_models import Base


class UserDB(Base):
    """User database model.

    Note: the underlying column name in Postgres is `hashed_password`
    (as created by the auth-service), so we map to that explicitly to
    avoid column-not-found errors when loading relationships.
    """

    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    email = Column(String(255), unique=True, nullable=False)
    username = Column(String(100), unique=True, nullable=False)
    hashed_password = Column("hashed_password", String(255), nullable=False)
    is_active = Column(Boolean, default=True)
    is_verified = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    api_keys = relationship("ApiKeyDB", back_populates="user", cascade="all, delete-orphan")
    sessions = relationship("SessionDB", back_populates="user", cascade="all, delete-orphan")


class ApiKeyDB(Base):
    """API key database model."""

    __tablename__ = "api_keys"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    key_hash = Column(String(255), unique=True, nullable=False)
    name = Column("key_name", String(100), nullable=False)  # Maps to `key_name` column
    is_active = Column(Boolean, default=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    last_used_at = Column("last_used", DateTime(timezone=True), nullable=True)

    # Relationships
    user = relationship("UserDB", back_populates="api_keys")


class SessionDB(Base):
    """Session database model."""

    __tablename__ = "sessions"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    session_token = Column(String(255), unique=True, nullable=False)
    ip_address = Column(String(45), nullable=True)  # IPv6 can be up to 45 chars
    user_agent = Column(Text, nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    user = relationship("UserDB", back_populates="sessions")
