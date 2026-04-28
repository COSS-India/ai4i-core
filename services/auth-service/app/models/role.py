"""
Role, Permission, UserRole, and RolePermission ORM models.
"""

from sqlalchemy import Column, DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.models import Base
from app.models.permission_enums import PermissionName


class Role(Base):
    __tablename__ = "roles"

    id = Column(Integer, primary_key=True, autoincrement=True, index=True)
    name = Column(String(100), unique=True, index=True, nullable=False)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    created_by = Column(UUID(as_uuid=True), nullable=True)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    updated_by = Column(UUID(as_uuid=True), nullable=True)

    user_roles = relationship("UserRole", back_populates="role", cascade="all, delete-orphan")
    role_permissions = relationship("RolePermission", back_populates="role", cascade="all, delete-orphan")


class Permission(Base):
    __tablename__ = "permissions"

    id = Column(Integer, primary_key=True, autoincrement=True, index=True)
    name = Column(
        Enum(PermissionName, name="permission_name_enum", values_callable=lambda x: [e.value for e in x]),
        unique=True,
        index=True,
        nullable=False,
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    created_by = Column(UUID(as_uuid=True), nullable=True)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    updated_by = Column(UUID(as_uuid=True), nullable=True)

    role_permissions = relationship("RolePermission", back_populates="permission", cascade="all, delete-orphan")


class UserRole(Base):
    __tablename__ = "user_role"

    id = Column(Integer, primary_key=True, autoincrement=True, index=True)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role_id = Column(
        Integer,
        ForeignKey("roles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    created_by = Column(UUID(as_uuid=True), nullable=True)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    updated_by = Column(UUID(as_uuid=True), nullable=True)

    user = relationship("User", back_populates="user_roles")
    role = relationship("Role", back_populates="user_roles")


class RolePermission(Base):
    __tablename__ = "role_permission"

    id = Column(Integer, primary_key=True, autoincrement=True, index=True)
    role_id = Column(
        Integer,
        ForeignKey("roles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    permission_id = Column(
        Integer,
        ForeignKey("permissions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    created_by = Column(UUID(as_uuid=True), nullable=True)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    updated_by = Column(UUID(as_uuid=True), nullable=True)

    role = relationship("Role", back_populates="role_permissions")
    permission = relationship("Permission", back_populates="role_permissions")
