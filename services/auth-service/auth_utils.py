"""
Authentication utilities and JWT handling
"""
import os
import secrets
import hashlib
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from jose import JWTError, jwt
from passlib.context import CryptContext
from passlib.hash import argon2
import redis.asyncio as redis
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from models import User, UserSession, APIKey

# Password hashing context
pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")

# JWT Configuration
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "dhruva-jwt-secret-key-2024-super-secure")
JWT_REFRESH_SECRET_KEY = os.getenv("JWT_REFRESH_SECRET_KEY", "dhruva-refresh-secret-key-2024-super-secure")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "15"))
REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7"))

class AuthUtils:
    """Authentication utility functions"""
    
    @staticmethod
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        """Verify a password against its hash"""
        return pwd_context.verify(plain_password, hashed_password)
    
    @staticmethod
    def get_password_hash(password: str) -> str:
        """Hash a password"""
        return pwd_context.hash(password)
    
    @staticmethod
    def create_access_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
        """Create a JWT access token"""
        to_encode = data.copy()
        if expires_delta:
            expire = datetime.utcnow() + expires_delta
        else:
            expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        
        to_encode.update({"exp": expire, "type": "access"})
        encoded_jwt = jwt.encode(to_encode, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
        return encoded_jwt
    
    @staticmethod
    def create_refresh_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
        """Create a JWT refresh token"""
        to_encode = data.copy()
        if expires_delta:
            expire = datetime.utcnow() + expires_delta
        else:
            expire = datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
        
        to_encode.update({"exp": expire, "type": "refresh"})
        encoded_jwt = jwt.encode(to_encode, JWT_REFRESH_SECRET_KEY, algorithm=JWT_ALGORITHM)
        return encoded_jwt
    
    @staticmethod
    def verify_access_token(token: str) -> Optional[Dict[str, Any]]:
        """Verify and decode an access token"""
        try:
            payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
            if payload.get("type") != "access":
                return None
            return payload
        except JWTError:
            return None
    
    @staticmethod
    def verify_refresh_token(token: str) -> Optional[Dict[str, Any]]:
        """Verify and decode a refresh token"""
        try:
            payload = jwt.decode(token, JWT_REFRESH_SECRET_KEY, algorithms=[JWT_ALGORITHM])
            if payload.get("type") != "refresh":
                return None
            return payload
        except JWTError:
            return None
    
    @staticmethod
    def generate_session_token() -> str:
        """Generate a secure session token"""
        return secrets.token_urlsafe(32)
    
    @staticmethod
    def generate_api_key() -> str:
        """Generate a secure API key"""
        return f"ak_{secrets.token_urlsafe(32)}"
    
    @staticmethod
    def hash_api_key(api_key: str) -> str:
        """Hash an API key for storage"""
        return hashlib.sha256(api_key.encode()).hexdigest()
    
    @staticmethod
    async def get_user_by_email(db: AsyncSession, email: str) -> Optional[User]:
        """Get user by email"""
        result = await db.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()
    
    @staticmethod
    async def get_user_by_username(db: AsyncSession, username: str) -> Optional[User]:
        """Get user by username"""
        result = await db.execute(select(User).where(User.username == username))
        return result.scalar_one_or_none()
    
    @staticmethod
    async def get_user_by_id(db: AsyncSession, user_id: int) -> Optional[User]:
        """Get user by ID"""
        result = await db.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()
    
    @staticmethod
    async def create_user_session(
        db: AsyncSession, 
        user_id: int, 
        session_token: str, 
        refresh_token: str,
        device_info: Optional[Dict] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        expires_delta: Optional[timedelta] = None,
        auto_commit: bool = True
    ) -> UserSession:
        """Create a new user session"""
        if expires_delta:
            expires_at = datetime.utcnow() + expires_delta
        else:
            expires_at = datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
        
        session = UserSession(
            user_id=user_id,
            session_token=session_token,
            refresh_token=refresh_token,
            device_info=device_info,
            ip_address=ip_address,
            user_agent=user_agent,
            expires_at=expires_at
        )
        
        db.add(session)
        await db.flush()  # Flush to get the session ID
        if auto_commit:
            await db.commit()
        # Return session - no refresh needed as flush already gives us the ID
        return session
    
    @staticmethod
    async def get_active_session(
        db: AsyncSession, 
        session_token: str
    ) -> Optional[UserSession]:
        """Get active session by token"""
        result = await db.execute(
            select(UserSession).where(
                UserSession.session_token == session_token,
                UserSession.is_active == True,
                UserSession.expires_at > datetime.utcnow()
            )
        )
        return result.scalar_one_or_none()
    
    @staticmethod
    async def invalidate_session(
        db: AsyncSession, 
        session_token: str
    ) -> bool:
        """Invalidate a session"""
        result = await db.execute(
            select(UserSession).where(UserSession.session_token == session_token)
        )
        session = result.scalar_one_or_none()
        
        if session:
            session.is_active = False
            await db.commit()
            return True
        return False
    
    @staticmethod
    async def invalidate_user_sessions(
        db: AsyncSession, 
        user_id: int, 
        keep_current: Optional[str] = None
    ) -> int:
        """Invalidate all user sessions except the current one"""
        query = select(UserSession).where(
            UserSession.user_id == user_id,
            UserSession.is_active == True
        )
        
        if keep_current:
            query = query.where(UserSession.session_token != keep_current)
        
        result = await db.execute(query)
        sessions = result.scalars().all()
        
        for session in sessions:
            session.is_active = False
        
        await db.commit()
        return len(sessions)
    
    @staticmethod
    async def cleanup_expired_sessions(db: AsyncSession) -> int:
        """Clean up expired sessions"""
        result = await db.execute(
            select(UserSession).where(
                UserSession.expires_at < datetime.utcnow(),
                UserSession.is_active == True
            )
        )
        sessions = result.scalars().all()
        
        for session in sessions:
            session.is_active = False
        
        await db.commit()
        return len(sessions)
    
    @staticmethod
    async def get_user_permissions(db: AsyncSession, user_id: int) -> list:
        """Get user permissions based on roles and API keys"""
        user = await AuthUtils.get_user_by_id(db, user_id)
        if not user:
            return []
        
        permissions = []
        
        # Basic user permissions
        permissions.extend(["read:profile", "update:profile"])
        
        # Superuser permissions
        if user.is_superuser:
            permissions.extend([
                "admin:users", "admin:roles", "admin:settings",
                "read:all", "write:all", "delete:all"
            ])
        
        # API key permissions
        result = await db.execute(
            select(APIKey).where(
                APIKey.user_id == user_id,
                APIKey.is_active == True,
                APIKey.expires_at > datetime.utcnow()
            )
        )
        api_keys = result.scalars().all()
        
        for api_key in api_keys:
            permissions.extend(api_key.permissions or [])
        
        return list(set(permissions))  # Remove duplicates
    
    @staticmethod
    def validate_password_strength(password: str) -> tuple[bool, list[str]]:
        """Validate password strength"""
        errors = []
        
        if len(password) < 8:
            errors.append("Password must be at least 8 characters long")
        
        if not any(c.isupper() for c in password):
            errors.append("Password must contain at least one uppercase letter")
        
        if not any(c.islower() for c in password):
            errors.append("Password must contain at least one lowercase letter")
        
        if not any(c.isdigit() for c in password):
            errors.append("Password must contain at least one number")
        
        if not any(c in "!@#$%^&*()_+-=[]{}|;:,.<>?" for c in password):
            errors.append("Password must contain at least one special character")
        
        return len(errors) == 0, errors
