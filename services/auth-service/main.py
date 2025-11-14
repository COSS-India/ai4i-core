"""
Authentication & Authorization Service - Identity management and access control
"""
import os
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from fastapi import FastAPI, Request, HTTPException, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import redis.asyncio as redis
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select, text, insert

from models import (
    User, UserSession, APIKey, UserCreate, UserResponse, UserUpdate,
    LoginRequest, LoginResponse, TokenRefreshRequest, TokenRefreshResponse,
    TokenValidationResponse, PasswordChangeRequest, PasswordResetRequest,
    PasswordResetConfirm, LogoutRequest, LogoutResponse, APIKeyCreate,
    APIKeyResponse, OAuth2Provider, OAuth2Callback
)
from auth_utils import AuthUtils

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="Authentication & Authorization Service",
    version="1.0.0",
    description="Identity management and access control for microservices"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global variables for connections
redis_client = None
db_engine = None
db_session = None

# Security
security = HTTPBearer()

# Dependency to get database session
async def get_db() -> AsyncSession:
    """Get database session"""
    async with db_session() as session:
        try:
            yield session
        finally:
            await session.close()

# Dependency to get current user from token
async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db)
) -> User:
    """Get current user from JWT token"""
    token = credentials.credentials
    payload = AuthUtils.verify_access_token(token)
    
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    user_id = payload.get("sub")
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    user = await AuthUtils.get_user_by_id(db, int(user_id))
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Inactive user",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    return user

# Dependency to get current active user
async def get_current_active_user(
    current_user: User = Depends(get_current_user)
) -> User:
    """Get current active user"""
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inactive user"
        )
    return current_user

@app.on_event("startup")
async def startup_event():
    """Initialize connections on startup"""
    global redis_client, db_engine, db_session
    
    try:
        # Initialize Redis connection
        redis_client = redis.from_url(
            f"redis://:{os.getenv('REDIS_PASSWORD', 'redis_secure_password_2024')}@"
            f"{os.getenv('REDIS_HOST', 'redis')}:{os.getenv('REDIS_PORT', '6379')}"
        )
        await redis_client.ping()
        logger.info("Connected to Redis")
        
        # Initialize PostgreSQL connection
        database_url = os.getenv(
            'DATABASE_URL', 
            'postgresql+asyncpg://dhruva_user:dhruva_secure_password_2024@postgres:5432/auth_db'
        )
        db_engine = create_async_engine(
            database_url,
            pool_size=int(os.getenv('DB_POOL_SIZE', '20')),
            max_overflow=int(os.getenv('DB_MAX_OVERFLOW', '10')),
            echo=False
        )
        db_session = sessionmaker(
            db_engine, 
            class_=AsyncSession, 
            expire_on_commit=False
        )
        logger.info("Connected to PostgreSQL")
        
    except Exception as e:
        logger.error(f"Failed to initialize connections: {e}")
        raise

@app.on_event("shutdown")
async def shutdown_event():
    """Clean up connections on shutdown"""
    global redis_client, db_engine
    
    if redis_client:
        await redis_client.close()
        logger.info("Redis connection closed")
    
    if db_engine:
        await db_engine.dispose()
        logger.info("PostgreSQL connection closed")

@app.get("/")
async def root():
    """Root endpoint with service information"""
    return {
        "service": "Authentication & Authorization Service",
        "version": "1.0.0",
        "status": "running",
        "description": "Identity management and access control for microservices"
    }

@app.get("/health")
async def health_check():
    """Health check endpoint for Docker health checks"""
    try:
        # Check Redis connectivity
        if redis_client:
            await redis_client.ping()
            redis_status = "healthy"
        else:
            redis_status = "unhealthy"
        
        # Check PostgreSQL connectivity
        if db_engine:
            try:
                async with db_engine.begin() as conn:
                    await conn.execute(text("SELECT 1"))
                postgres_status = "healthy"
            except Exception as e:
                logger.error(f"PostgreSQL health check failed: {e}")
                postgres_status = "unhealthy"
        else:
            postgres_status = "unhealthy"
        
        return {
            "status": "healthy" if redis_status == "healthy" and postgres_status == "healthy" else "unhealthy",
            "service": "auth-service",
            "redis": redis_status,
            "postgres": postgres_status,
            "timestamp": asyncio.get_event_loop().time()
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(status_code=503, detail="Service unhealthy")

@app.get("/api/v1/auth/status")
async def auth_status():
    """Authentication service status"""
    return {
        "service": "auth-service",
        "version": "v1",
        "status": "operational",
        "features": [
            "JWT token generation",
            "OAuth2 provider integration",
            "Role-based access control",
            "API key management",
            "Session management"
        ]
    }

# Authentication Endpoints

@app.post("/api/v1/auth/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(user_data: UserCreate, db: AsyncSession = Depends(get_db)):
    """Register a new user"""
    # Validate password confirmation
    if user_data.password != user_data.confirm_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Passwords do not match"
        )
    
    # Validate password strength
    is_valid, errors = AuthUtils.validate_password_strength(user_data.password)
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Password validation failed: {', '.join(errors)}"
        )
    
    # Check if user already exists
    existing_user = await AuthUtils.get_user_by_email(db, user_data.email)
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    
    existing_username = await AuthUtils.get_user_by_username(db, user_data.username)
    if existing_username:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already taken"
        )
    
    # Create new user
    hashed_password = AuthUtils.get_password_hash(user_data.password)
    db_user = User(
        email=user_data.email,
        username=user_data.username,
        hashed_password=hashed_password,
        full_name=user_data.full_name,
        phone_number=user_data.phone_number,
        timezone=user_data.timezone,
        language=user_data.language
    )
    
    db.add(db_user)
    await db.commit()
    await db.refresh(db_user)
    
    logger.info(f"New user registered: {user_data.email}")
    return db_user

@app.post("/api/v1/auth/login", response_model=LoginResponse)
async def login(
    login_data: LoginRequest,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """Authenticate user and return tokens"""
    # Get user by email
    user = await AuthUtils.get_user_by_email(db, login_data.email)
    if not user or not AuthUtils.verify_password(login_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Account is deactivated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Generate tokens
    access_token_expires = timedelta(minutes=15)
    refresh_token_expires = timedelta(days=7) if login_data.remember_me else timedelta(hours=24)
    
    access_token = AuthUtils.create_access_token(
        data={"sub": str(user.id), "email": user.email, "username": user.username},
        expires_delta=access_token_expires
    )
    
    refresh_token = AuthUtils.create_refresh_token(
        data={"sub": str(user.id), "email": user.email},
        expires_delta=refresh_token_expires
    )
    
    # Create session using raw SQL to avoid async ORM issues
    session_token = AuthUtils.generate_session_token()
    device_info = {
        "ip_address": request.client.host if request.client else None,
        "user_agent": request.headers.get("user-agent"),
        "remember_me": login_data.remember_me
    }
    
    # Insert session row (Core insert) and update last_login in same commit
    from sqlalchemy import insert as sa_insert
    expires_at = datetime.utcnow() + refresh_token_expires
    await db.execute(
        sa_insert(UserSession.__table__).values(
            user_id=user.id,
            session_token=session_token,
            refresh_token=refresh_token,
            device_info=device_info,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
            token_type="access",
            is_active=True,
            expires_at=expires_at
        )
    )
    user.last_login = datetime.utcnow()
    
    await db.commit()
    
    logger.info(f"User logged in: {user.email}")
    
    return LoginResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=int(access_token_expires.total_seconds())
    )

@app.post("/api/v1/auth/refresh", response_model=TokenRefreshResponse)
async def refresh_token(
    refresh_data: TokenRefreshRequest,
    db: AsyncSession = Depends(get_db)
):
    """Refresh access token using refresh token"""
    payload = AuthUtils.verify_refresh_token(refresh_data.refresh_token)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    user_id = payload.get("sub")
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token payload",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Verify session exists and is active
    result = await db.execute(
        select(UserSession).where(
            UserSession.refresh_token == refresh_data.refresh_token,
            UserSession.is_active == True,
            UserSession.expires_at > datetime.utcnow()
        )
    )
    session = result.scalar_one_or_none()
    
    if not session:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Get user
    user = await AuthUtils.get_user_by_id(db, int(user_id))
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Generate new access token
    access_token_expires = timedelta(minutes=15)
    access_token = AuthUtils.create_access_token(
        data={"sub": str(user.id), "email": user.email, "username": user.username},
        expires_delta=access_token_expires
    )
    
    # Update session last accessed and mark type as refresh
    session.last_accessed = datetime.utcnow()
    session.token_type = "refresh"
    await db.commit()
    
    return TokenRefreshResponse(
        access_token=access_token,
        expires_in=int(access_token_expires.total_seconds())
    )

@app.post("/api/v1/auth/logout", response_model=LogoutResponse)
async def logout(
    logout_data: LogoutRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Logout user and invalidate session"""
    if logout_data.refresh_token:
        # Invalidate specific session
        await AuthUtils.invalidate_session(db, logout_data.refresh_token)
        message = "Logged out successfully"
    else:
        # Invalidate all user sessions
        await AuthUtils.invalidate_user_sessions(db, current_user.id)
        message = "Logged out from all devices"
    
    logger.info(f"User logged out: {current_user.email}")
    
    return LogoutResponse(
        message=message,
        logged_out=True
    )

@app.get("/api/v1/auth/validate", response_model=TokenValidationResponse)
async def validate_token(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Validate token and return user info"""
    permissions = await AuthUtils.get_user_permissions(db, current_user.id)
    
    return TokenValidationResponse(
        valid=True,
        user_id=current_user.id,
        username=current_user.username,
        permissions=permissions
    )

@app.get("/api/v1/auth/me", response_model=UserResponse)
async def get_current_user_info(
    current_user: User = Depends(get_current_active_user)
):
    """Get current user information"""
    return current_user

@app.put("/api/v1/auth/me", response_model=UserResponse)
async def update_current_user(
    user_update: UserUpdate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Update current user information"""
    update_data = user_update.dict(exclude_unset=True)
    
    for field, value in update_data.items():
        setattr(current_user, field, value)
    
    current_user.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(current_user)
    
    logger.info(f"User updated: {current_user.email}")
    return current_user

@app.post("/api/v1/auth/change-password")
async def change_password(
    password_data: PasswordChangeRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Change user password"""
    # Validate current password
    if not AuthUtils.verify_password(password_data.current_password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect"
        )
    
    # Validate new password confirmation
    if password_data.new_password != password_data.confirm_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New passwords do not match"
        )
    
    # Validate password strength
    is_valid, errors = AuthUtils.validate_password_strength(password_data.new_password)
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Password validation failed: {', '.join(errors)}"
        )
    
    # Update password
    current_user.hashed_password = AuthUtils.get_password_hash(password_data.new_password)
    current_user.updated_at = datetime.utcnow()
    await db.commit()
    
    # Invalidate all sessions except current
    await AuthUtils.invalidate_user_sessions(db, current_user.id)
    
    logger.info(f"Password changed for user: {current_user.email}")
    return {"message": "Password changed successfully"}

@app.post("/api/v1/auth/request-password-reset")
async def request_password_reset(
    reset_data: PasswordResetRequest,
    db: AsyncSession = Depends(get_db)
):
    """Request password reset (placeholder - would send email in production)"""
    user = await AuthUtils.get_user_by_email(db, reset_data.email)
    if not user:
        # Don't reveal if email exists
        return {"message": "If the email exists, a password reset link has been sent"}
    
    # In production, generate reset token and send email
    # For now, just return success message
    logger.info(f"Password reset requested for: {reset_data.email}")
    return {"message": "If the email exists, a password reset link has been sent"}

@app.post("/api/v1/auth/reset-password")
async def reset_password(
    reset_data: PasswordResetConfirm,
    db: AsyncSession = Depends(get_db)
):
    """Reset password with token (placeholder - would validate token in production)"""
    # In production, validate reset token
    # For now, just return success message
    logger.info(f"Password reset attempted with token: {reset_data.token[:10]}...")
    return {"message": "Password reset functionality would be implemented with email verification"}

# API Key Management

@app.post("/api/v1/auth/api-keys", response_model=APIKeyResponse)
async def create_api_key(
    api_key_data: APIKeyCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Create a new API key"""
    # Generate API key
    api_key_value = AuthUtils.generate_api_key()
    api_key_hash = AuthUtils.hash_api_key(api_key_value)
    
    # Set expiration
    expires_at = None
    if api_key_data.expires_days:
        expires_at = datetime.utcnow() + timedelta(days=api_key_data.expires_days)
    
    # Create API key record
    db_api_key = APIKey(
        user_id=current_user.id,
        key_name=api_key_data.key_name,
        key_hash=api_key_hash,
        permissions=api_key_data.permissions,
        expires_at=expires_at
    )
    
    db.add(db_api_key)
    await db.commit()
    await db.refresh(db_api_key)
    
    logger.info(f"API key created for user: {current_user.email}")
    
    return APIKeyResponse(
        id=db_api_key.id,
        key_name=db_api_key.key_name,
        key_value=api_key_value,  # Only returned on creation
        permissions=db_api_key.permissions,
        is_active=db_api_key.is_active,
        created_at=db_api_key.created_at,
        expires_at=db_api_key.expires_at,
        last_used=db_api_key.last_used
    )

@app.get("/api/v1/auth/api-keys", response_model=List[APIKeyResponse])
async def list_api_keys(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """List user's API keys"""
    result = await db.execute(
        select(APIKey).where(APIKey.user_id == current_user.id)
    )
    api_keys = result.scalars().all()
    
    return [
        APIKeyResponse(
            id=key.id,
            key_name=key.key_name,
            key_value="***",  # Never return actual key value
            permissions=key.permissions,
            is_active=key.is_active,
            created_at=key.created_at,
            expires_at=key.expires_at,
            last_used=key.last_used
        )
        for key in api_keys
    ]

@app.delete("/api/v1/auth/api-keys/{key_id}")
async def revoke_api_key(
    key_id: int,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Revoke an API key"""
    result = await db.execute(
        select(APIKey).where(
            APIKey.id == key_id,
            APIKey.user_id == current_user.id
        )
    )
    api_key = result.scalar_one_or_none()
    
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found"
        )
    
    api_key.is_active = False
    await db.commit()
    
    logger.info(f"API key revoked: {key_id} for user: {current_user.email}")
    return {"message": "API key revoked successfully"}

# OAuth2 Endpoints (Placeholders)

@app.get("/api/v1/auth/oauth2/providers", response_model=List[OAuth2Provider])
async def get_oauth2_providers():
    """Get available OAuth2 providers"""
    return [
        OAuth2Provider(
            provider="google",
            client_id=os.getenv("GOOGLE_CLIENT_ID", ""),
            authorization_url="https://accounts.google.com/oauth/authorize",
            scope=["openid", "email", "profile"]
        ),
        OAuth2Provider(
            provider="github",
            client_id=os.getenv("GITHUB_CLIENT_ID", ""),
            authorization_url="https://github.com/login/oauth/authorize",
            scope=["user:email"]
        )
    ]

@app.post("/api/v1/auth/oauth2/callback")
async def oauth2_callback(
    callback_data: OAuth2Callback,
    db: AsyncSession = Depends(get_db)
):
    """Handle OAuth2 callback (placeholder)"""
    # In production, exchange code for tokens and create/login user
    logger.info(f"OAuth2 callback received for provider: {callback_data.provider}")
    return {"message": "OAuth2 callback functionality would be implemented with provider integration"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8081)
