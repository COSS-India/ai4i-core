"""
Auth Models
SQLAlchemy ORM models for authentication-related database tables
"""

from sqlalchemy import Column, String, Integer, Boolean, DateTime, ForeignKey, Text, func
from sqlalchemy.orm import relationship
from db_connection import AuthDBBase


class UserDB(AuthDBBase):
    """User database model - matches auth_db schema"""
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True)
    email = Column(String(255), unique=True, nullable=False)
    username = Column(String(100), unique=True, nullable=False)
    hashed_password = Column(String(255), nullable=True)  # Matches database column name (nullable for OAuth users)
    is_active = Column(Boolean, default=True)
    is_verified = Column(Boolean, default=False)
    is_tenant = Column(Boolean, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Relationships
    api_keys = relationship("ApiKeyDB", back_populates="user", cascade="all, delete-orphan")
    sessions = relationship("SessionDB", back_populates="user", cascade="all, delete-orphan")
    
    # Compatibility property for code that uses 'password_hash'
    @property
    def password_hash(self):
        """Get password_hash (alias for hashed_password)"""
        return self.hashed_password
    
    @password_hash.setter
    def password_hash(self, value):
        """Set password_hash (alias for hashed_password)"""
        self.hashed_password = value


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
    
    # Compatibility properties for code that uses 'name' and 'last_used_at'
    @property
    def name(self):
        """Get name (alias for key_name)"""
        return self.key_name
    
    @name.setter
    def name(self, value):
        """Set name (alias for key_name)"""
        self.key_name = value
    
    @property
    def last_used_at(self):
        """Get last_used_at (alias for last_used)"""
        return self.last_used
    
    @last_used_at.setter
    def last_used_at(self, value):
        """Set last_used_at (alias for last_used)"""
        self.last_used = value


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