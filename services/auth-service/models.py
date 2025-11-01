"""
Authentication models and schemas
"""
from datetime import datetime, timedelta
from typing import Optional, List
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, JSON
from sqlalchemy.orm import declarative_base
from sqlalchemy.sql import func

Base = declarative_base()

# Database Models
class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    username = Column(String(100), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(255), nullable=True)
    is_active = Column(Boolean, default=True)
    is_verified = Column(Boolean, default=False)
    is_superuser = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    last_login = Column(DateTime(timezone=True), nullable=True)
    
    # User preferences and metadata
    preferences = Column(JSON, default=dict)
    avatar_url = Column(String(500), nullable=True)
    phone_number = Column(String(20), nullable=True)
    timezone = Column(String(50), default="UTC")
    language = Column(String(10), default="en")

class UserSession(Base):
    __tablename__ = "user_sessions"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=False, index=True)
    session_token = Column(String(255), unique=True, index=True, nullable=False)
    refresh_token = Column(String(255), unique=True, index=True, nullable=True)
    device_info = Column(JSON, nullable=True)
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    expires_at = Column(DateTime(timezone=True), nullable=False)
    last_accessed = Column(DateTime(timezone=True), server_default=func.now())

class APIKey(Base):
    __tablename__ = "api_keys"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=False, index=True)
    key_name = Column(String(100), nullable=False)
    key_hash = Column(String(255), unique=True, index=True, nullable=False)
    permissions = Column(JSON, default=list)
    is_active = Column(Boolean, default=True)
    last_used = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    expires_at = Column(DateTime(timezone=True), nullable=True)

# Pydantic Models for API
class UserBase(BaseModel):
    email: EmailStr
    username: str = Field(..., min_length=3, max_length=100)
    full_name: Optional[str] = Field(None, max_length=255)
    phone_number: Optional[str] = Field(None, max_length=20)
    timezone: str = Field(default="UTC", max_length=50)
    language: str = Field(default="en", max_length=10)

class UserCreate(UserBase):
    password: str = Field(..., min_length=8, max_length=100)
    confirm_password: str = Field(..., min_length=8, max_length=100)

class UserUpdate(BaseModel):
    full_name: Optional[str] = Field(None, max_length=255)
    phone_number: Optional[str] = Field(None, max_length=20)
    timezone: Optional[str] = Field(None, max_length=50)
    language: Optional[str] = Field(None, max_length=10)
    preferences: Optional[dict] = None

class UserResponse(UserBase):
    id: int
    is_active: bool
    is_verified: bool
    is_superuser: bool
    created_at: datetime
    updated_at: Optional[datetime]
    last_login: Optional[datetime]
    avatar_url: Optional[str]
    
    class Config:
        from_attributes = True

class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    remember_me: bool = False

class LoginResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user: Optional[UserResponse] = None

class TokenRefreshRequest(BaseModel):
    refresh_token: str

class TokenRefreshResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int

class TokenValidationResponse(BaseModel):
    valid: bool
    user_id: Optional[int] = None
    username: Optional[str] = None
    permissions: List[str] = []

class PasswordChangeRequest(BaseModel):
    current_password: str
    new_password: str = Field(..., min_length=8, max_length=100)
    confirm_password: str = Field(..., min_length=8, max_length=100)

class PasswordResetRequest(BaseModel):
    email: EmailStr

class PasswordResetConfirm(BaseModel):
    token: str
    new_password: str = Field(..., min_length=8, max_length=100)
    confirm_password: str = Field(..., min_length=8, max_length=100)

class LogoutRequest(BaseModel):
    refresh_token: Optional[str] = None

class LogoutResponse(BaseModel):
    message: str
    logged_out: bool

class APIKeyCreate(BaseModel):
    key_name: str = Field(..., min_length=1, max_length=100)
    permissions: List[str] = Field(default_factory=list)
    expires_days: Optional[int] = Field(None, ge=1, le=365)

class APIKeyResponse(BaseModel):
    id: int
    key_name: str
    key_value: str  # Only returned on creation
    permissions: List[str]
    is_active: bool
    created_at: datetime
    expires_at: Optional[datetime]
    last_used: Optional[datetime]
    
    class Config:
        from_attributes = True

class OAuth2Provider(BaseModel):
    provider: str
    client_id: str
    authorization_url: str
    scope: List[str] = []

class OAuth2Callback(BaseModel):
    code: str
    state: str
    provider: str
