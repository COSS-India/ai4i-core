"""
Authentication utilities and JWT handling
"""
import os
import secrets
import hashlib
import logging
import base64
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, List, Tuple
from jose import JWTError, jwt
from passlib.context import CryptContext
from passlib.hash import argon2
import redis.asyncio as redis
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from cryptography.fernet import Fernet
from models import User, UserSession, APIKey, Role, Permission, UserRole, RolePermission, OAuthProvider
from casbin_enforcer import check_apikey_permission

logger = logging.getLogger(__name__)

# Password hashing context
pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")

# JWT Configuration
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "dhruva-jwt-secret-key-2024-super-secure")
JWT_REFRESH_SECRET_KEY = os.getenv("JWT_REFRESH_SECRET_KEY", "dhruva-refresh-secret-key-2024-super-secure")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "15"))
REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7"))

# API Key Encryption Configuration
API_KEY_ENCRYPTION_KEY = os.getenv("API_KEY_ENCRYPTION_KEY", None)

def _get_encryption_key() -> bytes:
    """Get or generate encryption key for API key encryption (Fernet key format)"""
    if API_KEY_ENCRYPTION_KEY:
        # If provided, use it (must be a valid Fernet key - 44-byte base64 string)
        try:
            # Validate it's a valid Fernet key by trying to create a Fernet instance
            Fernet(API_KEY_ENCRYPTION_KEY.encode())
            return API_KEY_ENCRYPTION_KEY.encode()
        except Exception:
            logger.warning("Invalid API_KEY_ENCRYPTION_KEY format, generating new key")
    
    # Generate a key from JWT_SECRET_KEY if available (for consistency)
    # This ensures the same key is used across restarts if JWT_SECRET_KEY is set
    if JWT_SECRET_KEY and JWT_SECRET_KEY != "dhruva-jwt-secret-key-2024-super-secure":
        # Derive a Fernet-compatible key from JWT_SECRET_KEY
        # Fernet needs exactly 32 bytes of key material
        key_material = hashlib.sha256(JWT_SECRET_KEY.encode()).digest()[:32]
        # Base64 encode to get a valid Fernet key (44 bytes)
        fernet_key = base64.urlsafe_b64encode(key_material)
        return fernet_key
    
    # Fallback: generate a key (WARNING: this will change on restart)
    logger.warning("No API_KEY_ENCRYPTION_KEY set, using generated key (will change on restart)")
    return Fernet.generate_key()

# Initialize Fernet cipher
try:
    _fernet = Fernet(_get_encryption_key())
except Exception as e:
    logger.error(f"Failed to initialize Fernet cipher: {e}")
    # Fallback to a generated key
    _fernet = Fernet(Fernet.generate_key())

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
    def create_access_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None, roles: Optional[List[str]] = None) -> str:
        """Create a JWT access token"""
        to_encode = data.copy()
        if expires_delta:
            expire = datetime.utcnow() + expires_delta
        else:
            expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        
        to_encode.update({"exp": expire, "type": "access"})
        if roles:
            to_encode.update({"roles": roles})
        encoded_jwt = jwt.encode(to_encode, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
        return encoded_jwt
    
    @staticmethod
    def create_refresh_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None, roles: Optional[List[str]] = None) -> str:
        """Create a JWT refresh token"""
        to_encode = data.copy()
        if expires_delta:
            expire = datetime.utcnow() + expires_delta
        else:
            expire = datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
        
        to_encode.update({"exp": expire, "type": "refresh"})
        if roles:
            to_encode.update({"roles": roles})
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
    def encrypt_api_key(api_key: str) -> str:
        """Encrypt an API key for storage"""
        try:
            encrypted = _fernet.encrypt(api_key.encode())
            return encrypted.decode()
        except Exception as e:
            logger.error(f"Error encrypting API key: {e}")
            raise ValueError("Failed to encrypt API key")
    
    @staticmethod
    def decrypt_api_key(encrypted_key: str) -> Optional[str]:
        """Decrypt an API key from storage"""
        try:
            if not encrypted_key:
                return None
            decrypted = _fernet.decrypt(encrypted_key.encode())
            return decrypted.decode()
        except Exception as e:
            logger.error(f"Error decrypting API key: {e}")
            return None
    
    @staticmethod
    async def validate_api_key(
        db: AsyncSession,
        api_key: str,
        service: str,
        action: str
    ) -> Tuple[bool, Optional[APIKey], Optional[str]]:
        """
        Validate API key and check permissions for service and action
        
        Args:
            db: Database session
            api_key: The API key to validate
            service: Service name (asr, tts, nmt, pipeline, model-management)
            action: Action type (read, inference)
        
        Returns:
            Tuple of (is_valid, api_key_obj, error_message)
        """
        # Hash the API key
        api_key_hash = AuthUtils.hash_api_key(api_key)
        
        # Find API key in database
        result = await db.execute(
            select(APIKey).where(APIKey.key_hash == api_key_hash)
        )
        api_key_obj = result.scalar_one_or_none()
        
        if not api_key_obj:
            return False, None, "Invalid API key"
        
        # Check if API key is active
        if not api_key_obj.is_active:
            return False, None, "API key has been revoked"
        
        # Check if API key has expired (use timezone-aware comparison)
        now_utc = datetime.now(timezone.utc)
        if api_key_obj.expires_at and api_key_obj.expires_at < now_utc:
            # Automatically deactivate expired keys for data consistency
            if api_key_obj.is_active:
                api_key_obj.is_active = False
                await db.commit()
            return False, None, "API key has expired"
        
        # Update last_used timestamp
        api_key_obj.last_used = now_utc
        await db.commit()
        
        # Get permissions
        permissions = api_key_obj.permissions or []

        # Build required permission string (e.g., "asr.inference", "tts.read")
        required_permission = f"{service}.{action}"

        # Use Casbin to evaluate permissions in a tenant-ready way.
        # Domain/tenant is "default" for now; this can be made dynamic later
        # without changing this call site.
        allowed = await check_apikey_permission(
            api_key_id=api_key_obj.id,
            permissions=permissions,
            obj=service,
            act=action,
            tenant="default",
        )

        if not allowed:
            # Preserve existing detailed error semantics for callers
            service_permissions = [p for p in permissions if p.startswith(f"{service}.")]

            if not service_permissions:
                # No permissions for this service at all
                return False, None, f"Invalid API key: This key does not have access to {service.upper()} service"

            # Check if it's a read-only key trying to access inference
            if action == "inference" and f"{service}.read" in permissions:
                return False, None, (
                    f"API key is restricted for read-only access. Inference operations "
                    f"require '{required_permission}' permission"
                )

            # Has some permissions for service but not the required one
            return False, None, (
                f"Invalid API key: This key does not have '{required_permission}' permission. "
                f"Available permissions: {', '.join(service_permissions)}"
            )

        # Valid API key with required permission
        return True, api_key_obj, None
    
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
        
        # Role-based permissions: Query permissions through user roles
        result = await db.execute(
            select(Permission.name)
            .join(RolePermission, Permission.id == RolePermission.permission_id)
            .join(Role, RolePermission.role_id == Role.id)
            .join(UserRole, Role.id == UserRole.role_id)
            .where(UserRole.user_id == user_id)
        )
        role_permissions = result.scalars().all()
        permissions.extend(role_permissions)
        
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
    async def get_user_roles(db: AsyncSession, user_id: int) -> list:
        """Get user roles - returns only the current role (one role per user)
        Also cleans up any duplicate roles, keeping only the most recently assigned one
        """
        # Get all user roles ordered by most recent first
        user_roles_result = await db.execute(
            select(UserRole)
            .where(UserRole.user_id == user_id)
            .order_by(UserRole.assigned_at.desc())
        )
        all_user_roles = list(user_roles_result.scalars().all())
        
        logger.debug(f"Found {len(all_user_roles)} role(s) for user {user_id}")
        
        if not all_user_roles:
            return []
        
        # If multiple roles exist, keep only the most recent one and delete others
        if len(all_user_roles) > 1:
            logger.warning(f"User {user_id} has {len(all_user_roles)} roles. Cleaning up duplicates...")
            # Get the most recent role (first one) to get its name
            most_recent_user_role = all_user_roles[0]
            role_result = await db.execute(
                select(Role.name).where(Role.id == most_recent_user_role.role_id)
            )
            most_recent_role_name = role_result.scalar_one()
            
            # Get role names of roles to be deleted for logging
            old_role_ids = [ur.role_id for ur in all_user_roles[1:]]
            if old_role_ids:
                old_roles_result = await db.execute(
                    select(Role.name).where(Role.id.in_(old_role_ids))
                )
                old_role_names = list(old_roles_result.scalars().all())
            else:
                old_role_names = []
            
            # Delete all roles except the most recent one
            for user_role in all_user_roles[1:]:  # Skip the first (most recent) one
                await db.delete(user_role)
            
            await db.flush()  # Flush before commit to ensure deletes are executed
            await db.commit()
            
            logger.warning(
                f"Cleaned up {len(all_user_roles) - 1} duplicate role(s) [{', '.join(old_role_names)}] "
                f"for user {user_id}. Kept only role: {most_recent_role_name}"
            )
            
            return [most_recent_role_name]
        else:
            # Only one role exists, get its name and return it
            role_result = await db.execute(
                select(Role.name).where(Role.id == all_user_roles[0].role_id)
            )
            role_name = role_result.scalar_one()
            return [role_name]
    
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
    
    @staticmethod
    async def get_oauth_provider(
        db: AsyncSession,
        provider_name: str,
        provider_user_id: str
    ) -> Optional[OAuthProvider]:
        """Get OAuth provider account by provider name and user ID"""
        result = await db.execute(
            select(OAuthProvider).where(
                OAuthProvider.provider_name == provider_name,
                OAuthProvider.provider_user_id == provider_user_id
            )
        )
        return result.scalar_one_or_none()
    
    @staticmethod
    async def get_user_oauth_providers(
        db: AsyncSession,
        user_id: int
    ) -> List[OAuthProvider]:
        """Get all OAuth providers linked to a user"""
        result = await db.execute(
            select(OAuthProvider).where(OAuthProvider.user_id == user_id)
        )
        return list(result.scalars().all())
    
    @staticmethod
    async def create_user_from_oauth(
        db: AsyncSession,
        email: str,
        full_name: Optional[str],
        avatar_url: Optional[str],
        provider_name: str,
        provider_user_id: str,
        oauth_tokens: Dict[str, Any],
        username: Optional[str] = None
    ) -> User:
        """Create a new user from OAuth provider data"""
        # Generate username from email if not provided
        if not username:
            username = email.split("@")[0]
            # Ensure username is unique
            base_username = username
            counter = 1
            while await AuthUtils.get_user_by_username(db, username):
                username = f"{base_username}{counter}"
                counter += 1
        
        # Check if user with this email already exists
        existing_user = await AuthUtils.get_user_by_email(db, email)
        if existing_user:
            # User exists, link OAuth account
            return await AuthUtils.link_oauth_to_user(
                db, existing_user.id, provider_name, provider_user_id, oauth_tokens
            )
        
        # Create new user (no password for OAuth users)
        new_user = User(
            email=email,
            username=username,
            hashed_password=None,  # OAuth users don't have passwords
            full_name=full_name,
            avatar_url=avatar_url,
            is_verified=True,  # OAuth emails are pre-verified
            is_active=True
        )
        
        db.add(new_user)
        await db.flush()  # Get user ID
        
        # Check if user already has any role (shouldn't happen for new users, but safety check)
        existing_roles = await db.execute(
            select(UserRole).where(UserRole.user_id == new_user.id)
        )
        existing_role = existing_roles.scalar_one_or_none()
        if not existing_role:
            # Assign default USER role (only if no role exists - one role per user)
            result = await db.execute(select(Role).where(Role.name == 'USER'))
            user_role_obj = result.scalar_one_or_none()
            if user_role_obj:
                user_role = UserRole(
                    user_id=new_user.id,
                    role_id=user_role_obj.id
                )
                db.add(user_role)
        
        # Create OAuth provider record
        oauth_provider = OAuthProvider(
            user_id=new_user.id,
            provider_name=provider_name,
            provider_user_id=provider_user_id,
            access_token=oauth_tokens.get("access_token"),
            refresh_token=oauth_tokens.get("refresh_token")
        )
        db.add(oauth_provider)
        
        await db.commit()
        await db.refresh(new_user)
        
        logger.info(f"Created new user from OAuth: {email} via {provider_name}")
        return new_user
    
    @staticmethod
    async def link_oauth_to_user(
        db: AsyncSession,
        user_id: int,
        provider_name: str,
        provider_user_id: str,
        oauth_tokens: Dict[str, Any]
    ) -> User:
        """Link OAuth account to existing user"""
        # Check if OAuth account already linked
        existing_oauth = await AuthUtils.get_oauth_provider(db, provider_name, provider_user_id)
        if existing_oauth:
            # Update tokens
            existing_oauth.access_token = oauth_tokens.get("access_token")
            existing_oauth.refresh_token = oauth_tokens.get("refresh_token")
            await db.commit()
            await db.refresh(existing_oauth)
            user = await AuthUtils.get_user_by_id(db, user_id)
            logger.info(f"Updated OAuth tokens for user {user_id} via {provider_name}")
            return user
        
        # Create new OAuth provider link
        oauth_provider = OAuthProvider(
            user_id=user_id,
            provider_name=provider_name,
            provider_user_id=provider_user_id,
            access_token=oauth_tokens.get("access_token"),
            refresh_token=oauth_tokens.get("refresh_token")
        )
        db.add(oauth_provider)
        await db.commit()
        
        user = await AuthUtils.get_user_by_id(db, user_id)
        logger.info(f"Linked OAuth account {provider_name} to user {user_id}")
        return user
