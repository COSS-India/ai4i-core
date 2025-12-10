from sqlalchemy import Column, Integer, String, Boolean, Text, DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import INET
from sqlalchemy.orm import relationship
from models.database_models import Base


class UserDB(Base):
    """User model for authentication database."""
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    username = Column(String(100), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    is_verified = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    
    # Relationships
    api_keys = relationship("ApiKeyDB", back_populates="user", cascade="all, delete-orphan")
    sessions = relationship("SessionDB", back_populates="user", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<UserDB(id={self.id}, email='{self.email}', username='{self.username}', is_active={self.is_active})>"


class RoleDB(Base):
    """Role model for user roles."""
    __tablename__ = "roles"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, index=True, nullable=False)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    
    def __repr__(self):
        return f"<RoleDB(id={self.id}, name='{self.name}')>"


class PermissionDB(Base):
    """Permission model for role-based access control."""
    __tablename__ = "permissions"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, index=True, nullable=False)
    resource = Column(String(100), nullable=False)
    action = Column(String(50), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    
    def __repr__(self):
        return f"<PermissionDB(id={self.id}, name='{self.name}', resource='{self.resource}', action='{self.action}')>"


class ApiKeyDB(Base):
    """API Key model for authentication."""
    __tablename__ = "api_keys"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    key_hash = Column(String(255), unique=True, index=True, nullable=False)
    name = Column("key_name", String(100), nullable=False)  # Maps to 'key_name' column in database
    is_active = Column(Boolean, default=True, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    last_used_at = Column("last_used", DateTime(timezone=True), nullable=True)  # Maps to 'last_used' column in database
    
    # Relationships
    user = relationship("UserDB", back_populates="api_keys")
    
    def __repr__(self):
        return f"<ApiKeyDB(id={self.id}, user_id={self.user_id}, name='{self.name}', is_active={self.is_active})>"


class SessionDB(Base):
    """Session model for user sessions."""
    __tablename__ = "sessions"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    session_token = Column(String(255), unique=True, index=True, nullable=False)
    ip_address = Column(INET, nullable=True)
    user_agent = Column(Text, nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    
    # Relationships
    user = relationship("UserDB", back_populates="sessions")
    
    def __repr__(self):
        return f"<SessionDB(id={self.id}, user_id={self.user_id}, expires_at={self.expires_at})>"
