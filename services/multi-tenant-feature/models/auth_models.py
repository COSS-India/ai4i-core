"""
Auth Models
SQLAlchemy ORM models for authentication-related database tables
"""

from sqlalchemy import Column, String, Integer, Boolean, DateTime, ForeignKey, Text, func, PrimaryKeyConstraint
from sqlalchemy.orm import relationship
from db_connection import AuthDBBase


class UserDB(AuthDBBase):
    """User database model - matches auth_db schema"""
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True)
    email = Column(String(255), unique=True, nullable=False)
    username = Column(String(100), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=True)  # Matches database column name (nullable for OAuth users)
    is_active = Column(Boolean, default=True)
    is_verified = Column(Boolean, default=False)
    is_tenant = Column(Boolean, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Relationships
    api_keys = relationship("ApiKeyDB", back_populates="user", cascade="all, delete-orphan")
    sessions = relationship("SessionDB", back_populates="user", cascade="all, delete-orphan")


class ApiKeyDB(AuthDBBase):
    """API Key database model - matches auth_db schema"""
    __tablename__ = "api_keys"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    key_hash = Column(String(255), unique=True, nullable=False)
    key_name = Column(String(100), nullable=True)  # Matches database column name
    is_active = Column(Boolean, default=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    last_used = Column(DateTime(timezone=True), nullable=True)  # Matches database column name
    permissions = Column(Text, nullable=True)  # JSONB in database, stored as text
    
    # Relationships
    user = relationship("UserDB", back_populates="api_keys")


class SessionDB(AuthDBBase):
    """Session database model"""
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


class Role(AuthDBBase):
    """Role database model for RBAC"""
    __tablename__ = "roles"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, index=True, nullable=False)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    user_roles = relationship("UserRole", back_populates="role", cascade="all, delete-orphan")


class UserRole(AuthDBBase):
    """User-Role mapping for RBAC"""
    __tablename__ = "user_roles"
    
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    role_id = Column(Integer, ForeignKey("roles.id", ondelete="CASCADE"), nullable=False, index=True)
    assigned_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Composite primary key
    __table_args__ = (
        PrimaryKeyConstraint("user_id", "role_id"),
    )
    
    # Relationships
    user = relationship("UserDB")
    role = relationship("Role", back_populates="user_roles")