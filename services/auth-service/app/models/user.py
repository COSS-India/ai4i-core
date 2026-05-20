"""
User ORM model.
"""

import enum
import uuid

from sqlalchemy import Boolean, Column, DateTime, Enum, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.models import Base


class CreationType(str, enum.Enum):
    """Python-only enum; persisted as VARCHAR (``native_enum=False``)."""

    DEFAULT = "default"
    GOOGLE = "google"


class UserSuspensionTag(str, enum.Enum):
    """Why a user is suspended — used to restore selectively on tenant reactivation."""

    TENANT_SUSPENDED = "TENANT_SUSPENDED"
    ADMIN_SUSPENDED = "ADMIN_SUSPENDED"


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True, index=True, nullable=False)
    username = Column(String(100), unique=True, index=True, nullable=False)
    full_name = Column(String(255), nullable=True)
    is_active = Column(Boolean, default=False, nullable=False, server_default="false")
    tenant_id = Column(
        Integer,
        ForeignKey("tenants.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    last_login = Column(DateTime(timezone=True), nullable=True)
    avatar_url = Column(String(500), nullable=True)
    phone_number = Column(String(20), nullable=True)
    timezone = Column(String(50), server_default="UTC")
    is_delete = Column(Boolean, default=False, nullable=True)
    is_tenant_active = Column(Boolean, default=True, nullable=True)
    suspension_tag = Column(
        Enum(
            UserSuspensionTag,
            values_callable=lambda x: [e.value for e in x],
            native_enum=False,
            length=32,
        ),
        nullable=True,
    )
    creation_type = Column(
        Enum(
            CreationType,
            values_callable=lambda x: [e.value for e in x],
            native_enum=False,
            length=32,
        ),
        nullable=True,
        server_default=CreationType.DEFAULT.value,
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    created_by = Column(UUID(as_uuid=True), nullable=True)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    updated_by = Column(UUID(as_uuid=True), nullable=True)

    # Relationships
    tenant = relationship("Tenant", back_populates="users")
    user_roles = relationship("UserRole", back_populates="user", cascade="all, delete-orphan")
    credentials = relationship("UserCredentials", back_populates="user", uselist=False, cascade="all, delete-orphan")
    api_keys = relationship("APIKey", back_populates="user", cascade="all, delete-orphan")
    refresh_tokens = relationship("RefreshToken", back_populates="user", cascade="all, delete-orphan")

    def is_accessible(self) -> bool:
        """Account can be logged into: active and not soft-deleted."""
        return bool(self.is_active and not self.is_delete)

    def soft_delete(self) -> None:
        self.is_delete = True
        self.is_active = False

    def activate(self) -> None:
        self.is_active = True
        self.is_delete = False

    def __repr__(self) -> str:
        return f"<User id={self.id} email={self.email!r} active={self.is_active}>"
