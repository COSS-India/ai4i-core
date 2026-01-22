"""
Authentication & Authorization Service - Identity management and access control
"""
import os
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from fastapi import FastAPI, Request, HTTPException, Depends, status, Query
from fastapi.openapi.utils import get_openapi
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.responses import RedirectResponse
import redis.asyncio as redis
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select, text

from models import (
    User, UserSession, APIKey, UserCreate, UserResponse, UserUpdate,
    LoginRequest, LoginResponse, TokenRefreshRequest, TokenRefreshResponse,
    TokenValidationResponse, PasswordChangeRequest, PasswordResetRequest,
    PasswordResetConfirm, LogoutRequest, LogoutResponse, APIKeyCreate,
    APIKeyUpdate, APIKeyResponse, OAuth2Provider, OAuth2Callback, Role, UserRole,
    APIKeyValidationRequest, APIKeyValidationResponse, Permission,
    UserDetailResponse, PermissionResponse, UserListResponse,
    AdminAPIKeyWithUserResponse,
)
from pydantic import BaseModel
from auth_utils import AuthUtils, ACCESS_TOKEN_EXPIRE_MINUTES
from oauth_utils import OAuthUtils
from casbin_enforcer import load_policies_from_db, check_roles_permission

# Refresh token lifetimes
REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7"))
REFRESH_TOKEN_EXPIRE_HOURS = int(os.getenv("REFRESH_TOKEN_EXPIRE_HOURS", "24"))

# Import error constants
try:
    from services.constants.error_messages import (
        AUTHENTICATION_REQUIRED,
        AUTHENTICATION_REQUIRED_MESSAGE,
        INVALID_CREDENTIALS,
        INVALID_CREDENTIALS_MESSAGE,
        SESSION_EXPIRED,
        SESSION_EXPIRED_MESSAGE,
        UNAUTHORIZED,
        UNAUTHORIZED_MESSAGE,
    )
except ImportError:
    # Fallback if constants not available
    AUTHENTICATION_REQUIRED = "AUTHENTICATION_REQUIRED"
    AUTHENTICATION_REQUIRED_MESSAGE = "Authentication is required to access this service. Please log in."
    INVALID_CREDENTIALS = "INVALID_CREDENTIALS"
    INVALID_CREDENTIALS_MESSAGE = "Invalid credentials provided. Please log in again."
    SESSION_EXPIRED = "SESSION_EXPIRED"
    SESSION_EXPIRED_MESSAGE = "Your session has expired. Please log in again."
    UNAUTHORIZED = "UNAUTHORIZED"
    UNAUTHORIZED_MESSAGE = "You don't have permission to access this service. Please contact your administrator."

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="Authentication & Authorization Service",
    version="1.0.0",
    description="Identity management and access control for microservices"
)

# Override OpenAPI server URL for Swagger UI (e.g., localhost)
swagger_server_url = os.getenv("SWAGGER_SERVER_URL")
if swagger_server_url:
    def custom_openapi():
        if app.openapi_schema:
            return app.openapi_schema
        openapi_schema = get_openapi(
            title=app.title,
            version=app.version,
            description=app.description,
            routes=app.routes,
            servers=[{"url": swagger_server_url}],
        )
        app.openapi_schema = openapi_schema
        return app.openapi_schema
    app.openapi = custom_openapi

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
multi_tenant_db_engine = None
multi_tenant_db_session = None

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

# Dependency to get multi-tenant database session
async def get_multi_tenant_db():
    """Get multi-tenant database session"""
    if multi_tenant_db_session is None:
        yield None
        return
    async with multi_tenant_db_session() as session:
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
            detail={"code": INVALID_CREDENTIALS, "message": INVALID_CREDENTIALS_MESSAGE},
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    user_id = payload.get("sub")
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": INVALID_CREDENTIALS, "message": INVALID_CREDENTIALS_MESSAGE},
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    user = await AuthUtils.get_user_by_id(db, int(user_id))
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": INVALID_CREDENTIALS, "message": INVALID_CREDENTIALS_MESSAGE},
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": INVALID_CREDENTIALS, "message": INVALID_CREDENTIALS_MESSAGE},
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

# Helper function to get tenant information for a user
# Checks both tenants table (tenant admin) and tenant_users table (tenant user)
async def get_tenant_info(user_id: int, multi_tenant_db: Optional[AsyncSession], is_tenant: bool) -> Optional[Dict[str, Any]]:
    """
    Get tenant information for a user from multi-tenant database.
    """
    if multi_tenant_db is None:
        return None
    
    try:
        if is_tenant:
            tenant_admin_query = text("""
                SELECT 
                    t.tenant_id,
                    t.id as tenant_uuid,
                    t.schema_name,
                    t.subscriptions as tenant_subscriptions,
                    t.status
                FROM tenants t
                WHERE t.user_id = :user_id
                AND t.status = 'ACTIVE'
                LIMIT 1
            """)

            result = await multi_tenant_db.execute(tenant_admin_query, {"user_id": user_id})
            row = result.fetchone()

            if row:
                # User is a tenant admin
                return {
                    "tenant_id": row[0],
                    "tenant_uuid": str(row[1]),
                    "schema_name": row[2],
                    "subscriptions": row[3] if row[3] else [],
                    "user_subscriptions": row[4] if row[4] else [],
                }
        else:
            tenant_user_query = text("""
                SELECT 
                    t.tenant_id,
                    t.id as tenant_uuid,
                    t.schema_name,
                    t.subscriptions as tenant_subscriptions,
                    tu.subscriptions as user_subscriptions,
                    t.status
                FROM tenant_users tu
                JOIN tenants t ON tu.tenant_uuid = t.id
                WHERE tu.user_id = :user_id
                AND t.status = 'ACTIVE'
                AND tu.status = 'ACTIVE'
                LIMIT 1
            """)

            result = await multi_tenant_db.execute(tenant_user_query, {"user_id": user_id})
            row = result.fetchone()

            if row:
                # User is a tenant user
                return {
                    "tenant_id": row[0],
                    "tenant_uuid": str(row[1]),
                    "schema_name": row[2],
                    "subscriptions": row[3] if row[3] else [],
                    "user_subscriptions": row[4] if row[4] else [],
                }
        
        # User not found in either table
        return None
        
    except Exception as e:
        logger.error(f"Error getting tenant info for user {user_id}: {e}", exc_info=True)
        return None

@app.on_event("startup")
async def startup_event():
    """Initialize connections on startup"""
    global redis_client, db_engine, db_session, multi_tenant_db_engine, multi_tenant_db_session
    
    try:
        # Initialize Redis connection
        redis_host = os.getenv('REDIS_HOST', 'redis')
        redis_port = os.getenv('REDIS_PORT', '6379')
        redis_password = os.getenv('REDIS_PASSWORD', '')
        
        # Build Redis URL - only include password if it's set
        if redis_password:
            redis_url = f"redis://:{redis_password}@{redis_host}:{redis_port}"
        else:
            redis_url = f"redis://{redis_host}:{redis_port}"
        
        redis_client = redis.from_url(
            redis_url,
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=5,
            retry_on_timeout=True
        )
        
        # Try to connect with retries
        max_retries = 3
        for attempt in range(max_retries):
            try:
                await redis_client.ping()
                logger.info("Connected to Redis")
                break
            except Exception as e:
                if attempt < max_retries - 1:
                    logger.warning(f"Redis ping attempt {attempt + 1}/{max_retries} failed: {e}, retrying...")
                    await asyncio.sleep(2)
                else:
                    logger.warning(f"Redis connection failed after {max_retries} attempts: {e}")
                    logger.warning("Proceeding without Redis (session management disabled)")
                    redis_client = None
                    break
        
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
        
        # Initialize multi-tenant database connection
        multi_tenant_db_url = os.getenv(
            'MULTI_TENANT_DB_URL',
            'postgresql+asyncpg://dhruva_user:dhruva_password@postgres:5434/multi_tenant_db'
        )
        try:
            multi_tenant_db_engine = create_async_engine(
                multi_tenant_db_url,
                pool_size=int(os.getenv('MULTI_TENANT_DB_POOL_SIZE', '20')),
                max_overflow=int(os.getenv('MULTI_TENANT_DB_MAX_OVERFLOW', '10')),
                echo=False
            )
            multi_tenant_db_session = sessionmaker(
                multi_tenant_db_engine,
                class_=AsyncSession,
                expire_on_commit=False
            )
            # Test connection
            async with multi_tenant_db_session() as test_session:
                await test_session.execute(text("SELECT 1"))
            logger.info("Connected to multi-tenant PostgreSQL database")
        except Exception as e:
            logger.warning(f"Failed to connect to multi-tenant database: {e}")
            logger.warning("JWT tokens will not include tenant information (fallback to API resolution)")
            multi_tenant_db_engine = None
            multi_tenant_db_session = None
        
        # Load Casbin policies from database
        try:
            async with db_session() as session:
                await load_policies_from_db(session)
                logger.info("Loaded Casbin policies from database")
        except Exception as e:
            logger.warning(f"Failed to load Casbin policies from database: {e}")
            logger.warning("Casbin will use empty policies (may cause permission checks to fail)")
        
    except Exception as e:
        logger.error(f"Failed to initialize connections: {e}")
        raise

@app.on_event("shutdown")
async def shutdown_event():
    """Clean up connections on shutdown"""
    global redis_client, db_engine, multi_tenant_db_engine
    
    if redis_client:
        await redis_client.close()
        logger.info("Redis connection closed")
    
    if db_engine:
        await db_engine.dispose()
        logger.info("PostgreSQL connection closed")
    
    if multi_tenant_db_engine:
        await multi_tenant_db_engine.dispose()
        logger.info("Multi-tenant PostgreSQL connection closed")

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

@app.get("/ready")
async def readiness_check():
    """Readiness check endpoint for Kubernetes probes"""
    try:
        # Check PostgreSQL connectivity (required for readiness)
        if db_engine:
            try:
                async with db_engine.begin() as conn:
                    await conn.execute(text("SELECT 1"))
                return {
                    "status": "ready",
                    "service": "auth-service"
                }
            except Exception as e:
                logger.error(f"PostgreSQL readiness check failed: {e}")
                raise HTTPException(status_code=503, detail="Service not ready")
        else:
            raise HTTPException(status_code=503, detail="Database not initialized")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Readiness check failed: {e}")
        raise HTTPException(status_code=503, detail="Service not ready")

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
        language=user_data.language,
        # Flag indicating whether this user is a tenant admin or regular user.
        # Multi-tenant service sets this explicitly when creating tenant admins / users.
        is_tenant=user_data.is_tenant or None,
    )
    
    db.add(db_user)
    await db.flush()  # Flush to ensure the user is added to the session
    
    # Check if user already has any role (shouldn't happen for new users, but safety check)
    existing_roles = await db.execute(
        select(UserRole).where(UserRole.user_id == db_user.id)
    )
    existing_role = existing_roles.scalar_one_or_none()
    if existing_role:
        logger.warning(f"User {user_data.email} already has a role assigned. Skipping default role assignment.")
    else:
        # Assign default USER role to new users (only if no role exists)
        result = await db.execute(select(Role).where(Role.name == 'USER'))
        user_role_obj = result.scalar_one_or_none()
        if user_role_obj:
            user_role = UserRole(user_id=db_user.id, role_id=user_role_obj.id)
            db.add(user_role)
            logger.info(f"Assigned default USER role to new user: {user_data.email}")
        else:
            logger.warning(f"USER role not found in database. User {user_data.email} registered without default role.")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="System configuration error: Default USER role not found. Please contact administrator."
            )
    
    await db.commit()
    await db.refresh(db_user)
    
    # Get user roles directly (query immediately after commit to ensure we get the role)
    role_result = await db.execute(
        select(Role.name)
        .join(UserRole, Role.id == UserRole.role_id)
        .where(UserRole.user_id == db_user.id)
        .order_by(UserRole.assigned_at.desc())
        .limit(1)
    )
    user_roles = list(role_result.scalars().all())
    
    logger.info(f"New user registered: {user_data.email} with roles: {user_roles}")
    
    # Create response dict with roles
    user_dict = {
        "id": db_user.id,
        "email": db_user.email,
        "username": db_user.username,
        "full_name": db_user.full_name,
        "phone_number": db_user.phone_number,
        "timezone": db_user.timezone,
        "language": db_user.language,
        "is_active": db_user.is_active,
        "is_verified": db_user.is_verified,
        "is_superuser": db_user.is_superuser,
        "created_at": db_user.created_at,
        "updated_at": db_user.updated_at,
        "last_login": db_user.last_login,
        "avatar_url": db_user.avatar_url,
        "roles": user_roles
    }
    
    return user_dict

@app.post("/api/v1/auth/login", response_model=LoginResponse)
async def login(
    login_data: LoginRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    multi_tenant_db: Optional[AsyncSession] = Depends(get_multi_tenant_db)
):
    """Authenticate user and return tokens"""
    # Get user by email
    user = await AuthUtils.get_user_by_email(db, login_data.email)
    if not user or not AuthUtils.verify_password(login_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": INVALID_CREDENTIALS, "message": INVALID_CREDENTIALS_MESSAGE},
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": INVALID_CREDENTIALS, "message": INVALID_CREDENTIALS_MESSAGE},
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Get user roles
    user_roles = await AuthUtils.get_user_roles(db, user.id)
    
    # Get tenant information
    tenant_info = await get_tenant_info(user.id, multi_tenant_db , user.is_tenant)

    token_data = {
        "sub": str(user.id),
        "email": user.email,
        "username": user.username
    }
    
    # Add tenant info if available
    if tenant_info:
        token_data.update({
            "tenant_id": tenant_info["tenant_id"],
            "tenant_uuid": tenant_info["tenant_uuid"],
            "schema_name": tenant_info["schema_name"],
            "subscriptions": tenant_info.get("subscriptions", []),
            "user_subscriptions": tenant_info.get("user_subscriptions", []),
        })
        logger.info(f"Added tenant info to JWT for user {user.id}: tenant_id={tenant_info['tenant_id']}, schema={tenant_info['schema_name']}")
    
    # Generate tokens
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    refresh_token_expires = (
        timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
        if login_data.remember_me
        else timedelta(hours=REFRESH_TOKEN_EXPIRE_HOURS)
    )
    
    access_token = AuthUtils.create_access_token(
        data=token_data,
        expires_delta=access_token_expires,
        roles=user_roles
    )
    
    refresh_token = AuthUtils.create_refresh_token(
        data=token_data,  # Include tenant info in refresh token too
        expires_delta=refresh_token_expires,
        roles=user_roles
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
    now = datetime.utcnow()
    expires_at = now + refresh_token_expires
    await db.execute(
        sa_insert(UserSession.__table__).values(
            user_id=user.id,
            session_token=session_token,
            refresh_token=refresh_token,
            device_info=device_info,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
            is_active=True,
            expires_at=expires_at
        )
    )
    user.last_login = now
    
    await db.commit()
    # Refresh to avoid expired attributes after commit (async DB)
    await db.refresh(user)
    
    logger.info(f"User logged in: {user.email}")

    # Build user response with roles (same shape as /auth/me)
    user_dict = {
        "id": user.id,
        "email": user.email,
        "username": user.username,
        "full_name": user.full_name,
        "phone_number": user.phone_number,
        "timezone": user.timezone,
        "language": user.language,
        "is_active": user.is_active,
        "is_verified": user.is_verified,
        "is_superuser": user.is_superuser,
        "created_at": user.created_at,
        "updated_at": user.updated_at,
        "last_login": user.last_login,
        "avatar_url": user.avatar_url,
        "roles": user_roles,
    }
    
    return LoginResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        expires_in=int(access_token_expires.total_seconds()),
        user=user_dict,
    )

@app.post("/api/v1/auth/refresh", response_model=TokenRefreshResponse)
async def refresh_token(
    refresh_data: TokenRefreshRequest,
    db: AsyncSession = Depends(get_db),
    multi_tenant_db: Optional[AsyncSession] = Depends(get_multi_tenant_db)
):
    """Refresh access token using refresh token"""
    payload = AuthUtils.verify_refresh_token(refresh_data.refresh_token)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": INVALID_CREDENTIALS, "message": INVALID_CREDENTIALS_MESSAGE},
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    user_id = payload.get("sub")
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": INVALID_CREDENTIALS, "message": INVALID_CREDENTIALS_MESSAGE},
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
            detail={"code": SESSION_EXPIRED, "message": SESSION_EXPIRED_MESSAGE},
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Sliding window: extend session expiry on successful refresh
    remember_me = False
    if getattr(session, "device_info", None):
        try:
            remember_me = bool(session.device_info.get("remember_me"))
        except Exception:
            remember_me = False
    session.expires_at = (
        datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
        if remember_me
        else datetime.utcnow() + timedelta(hours=REFRESH_TOKEN_EXPIRE_HOURS)
    )
    
    # Get user
    user = await AuthUtils.get_user_by_id(db, int(user_id))
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": INVALID_CREDENTIALS, "message": INVALID_CREDENTIALS_MESSAGE},
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Get user roles
    user_roles = await AuthUtils.get_user_roles(db, user.id)
    
    # Get tenant information
    tenant_info = await get_tenant_info(user.id, multi_tenant_db, user.is_tenant)
    
    # Build JWT payload with tenant info
    token_data = {
        "sub": str(user.id),
        "email": user.email,
        "username": user.username
    }
    
    # Add tenant info if available
    if tenant_info:
        token_data.update({
            "tenant_id": tenant_info["tenant_id"],
            "tenant_uuid": tenant_info["tenant_uuid"],
            "schema_name": tenant_info["schema_name"],
            "subscriptions": tenant_info.get("subscriptions", []),
            "user_subscriptions": tenant_info.get("user_subscriptions", []),
        })
    
    # Generate new access token
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = AuthUtils.create_access_token(
        data=token_data,
        expires_delta=access_token_expires,
        roles=user_roles
    )
    
    # Update session last accessed
    session.last_accessed = datetime.utcnow()
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
@app.post("/api/v1/auth/validate", response_model=TokenValidationResponse)
async def validate_token(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Validate token and return user info (supports both GET and POST for Kong introspection)"""
    permissions = await AuthUtils.get_user_permissions(db, current_user.id)
    roles = await AuthUtils.get_user_roles(db, current_user.id)
    
    return TokenValidationResponse(
        valid=True,
        user_id=current_user.id,
        username=current_user.username,
        permissions=permissions,
        roles=roles
    )

@app.post("/api/v1/auth/validate-api-key", response_model=APIKeyValidationResponse)
async def validate_api_key(
    validation_data: APIKeyValidationRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Validate API key with permission checking for service and action
    
    This endpoint validates:
    1. API key exists and is active
    2. API key has not expired
    3. API key has the required permission (e.g., asr.inference)
    4. If action is 'inference' but key only has 'read', returns appropriate error
    
    Examples:
    - API key with ['asr.read', 'asr.inference'] can access asr.read and asr.inference
    - API key with ['asr.read'] can only access asr.read, not asr.inference
    - API key with ['asr.read', 'nmt.read', 'nmt.inference'] can access both ASR and NMT services
    """
    # Normalize service name (handle variations)
    service = validation_data.service.lower().strip()
    action = validation_data.action.lower().strip()
    
    # Validate service name
    valid_services = [
        'asr', 'tts', 'nmt', 'pipeline', 'model-management', 'llm',
        'audio-lang-detection', 'language-detection', 'language-diarization',
        'ner', 'ocr', 'speaker-diarization', 'transliteration'
    ]
    if service not in valid_services:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid service name. Must be one of: {', '.join(valid_services)}"
        )
    
    # Validate action
    valid_actions = ['read', 'inference']
    if action not in valid_actions:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid action. Must be one of: {', '.join(valid_actions)}"
        )
    
    # Map service names to permission resource names (for compatibility)
    # Permissions use resource names like "audio-lang" but services may send "audio-lang-detection"
    service_to_resource = {
        'audio-lang-detection': 'audio-lang',
        'language-detection': 'language-detection',
        'language-diarization': 'language-diarization',
        'ner': 'ner',
        'ocr': 'ocr',
        'speaker-diarization': 'speaker-diarization',
        'transliteration': 'transliteration',
        'asr': 'asr',
        'tts': 'tts',
        'nmt': 'nmt',
        'pipeline': 'pipeline',
        'model-management': 'model-management',
        'llm': 'llm'
    }
    # Use mapped resource name for permission checking
    resource_name = service_to_resource.get(service, service)
    
    # Validate API key
    is_valid, api_key_obj, error_message = await AuthUtils.validate_api_key(
        db=db,
        api_key=validation_data.api_key,
        service=resource_name,
        action=action
    )
    
    if not is_valid:
        return APIKeyValidationResponse(
            valid=False,
            message=error_message,
            permissions=[]
        )
    
    # Return success with permissions
    return APIKeyValidationResponse(
        valid=True,
        message="API key is valid and has required permissions",
        user_id=api_key_obj.user_id,
        permissions=api_key_obj.permissions or []
    )

@app.get("/api/v1/auth/me", response_model=UserResponse)
async def get_current_user_info(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Get current user information"""
    user_roles = await AuthUtils.get_user_roles(db, current_user.id)
    # Create response dict with roles
    user_dict = {
        "id": current_user.id,
        "email": current_user.email,
        "username": current_user.username,
        "full_name": current_user.full_name,
        "phone_number": current_user.phone_number,
        "timezone": current_user.timezone,
        "language": current_user.language,
        "is_active": current_user.is_active,
        "is_verified": current_user.is_verified,
        "is_superuser": current_user.is_superuser,
        "created_at": current_user.created_at,
        "updated_at": current_user.updated_at,
        "last_login": current_user.last_login,
        "avatar_url": current_user.avatar_url,
        "roles": user_roles
    }
    return user_dict

@app.put("/api/v1/auth/me", response_model=UserResponse)
async def update_current_user(
    user_update: UserUpdate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Update current user information and return updated details including roles."""
    update_data = user_update.dict(exclude_unset=True)
    
    for field, value in update_data.items():
        setattr(current_user, field, value)
    
    current_user.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(current_user)
    
    logger.info(f"User updated: {current_user.email}")

    # Include roles in the response, similar to GET /api/v1/auth/me
    user_roles = await AuthUtils.get_user_roles(db, current_user.id)
    user_dict = {
        "id": current_user.id,
        "email": current_user.email,
        "username": current_user.username,
        "full_name": current_user.full_name,
        "phone_number": current_user.phone_number,
        "timezone": current_user.timezone,
        "language": current_user.language,
        "is_active": current_user.is_active,
        "is_verified": current_user.is_verified,
        "is_superuser": current_user.is_superuser,
        "created_at": current_user.created_at,
        "updated_at": current_user.updated_at,
        "last_login": current_user.last_login,
        "avatar_url": current_user.avatar_url,
        "roles": user_roles,
    }

    return user_dict

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


def require_permission(resource: str, action: str):
    """
    Dependency factory: ensure current user (by roles) has given permission
    using Casbin policies loaded from role_permissions.

    Example:
        current_user: User = Depends(require_permission("apiKey", "create"))
    """

    async def _dep(
        current_user: User = Depends(get_current_active_user),
        db: AsyncSession = Depends(get_db),
    ) -> User:
        user_roles = await AuthUtils.get_user_roles(db, current_user.id)
        allowed = await check_roles_permission(
            roles=user_roles,
            obj=resource,
            act=action,
            tenant="default",
        )
        if not allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"code": UNAUTHORIZED, "message": f"Insufficient permissions: requires '{resource}.{action}'"},
            )
        return current_user

    return _dep


# Backwards-compatible admin helper (still used by some admin endpoints)
async def require_admin(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
) -> User:
    """Dependency to ensure current user is an admin role (ADMIN or superuser)."""
    user_roles = await AuthUtils.get_user_roles(db, current_user.id)
    if "ADMIN" not in user_roles and not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": UNAUTHORIZED, "message": "Only administrators can access this endpoint"}
        )
    return current_user


# API Key Management

@app.post("/api/v1/auth/api-keys", response_model=APIKeyResponse)
async def create_api_key(
    api_key_data: APIKeyCreate,
    current_user: User = Depends(require_permission("apiKey", "create")),
    db: AsyncSession = Depends(get_db)
):
    """
    Create a new API key.

    Access control:
    - Any role that has the `apiKey.create` permission (via Casbin/role_permissions)
      can create API keys.
    - The same permission applies whether the key is for the current user or for
      another user (when `user_id` is provided).
    """
    # Determine target user ID
    target_user_id = current_user.id
    target_user = current_user
    
    # If user_id is provided, verify target user exists
    if api_key_data.user_id is not None:
        # Verify target user exists
        target_user = await AuthUtils.get_user_by_id(db, api_key_data.user_id)
        if not target_user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User with ID {api_key_data.user_id} not found"
            )
        
        target_user_id = api_key_data.user_id
    
    # Expand permissions if pipeline.inference is selected
    requested_permissions = list(api_key_data.permissions or [])
    if "pipeline.inference" in requested_permissions:
        for perm in ["asr.inference", "nmt.inference", "tts.inference"]:
            if perm not in requested_permissions:
                requested_permissions.append(perm)
    # Ensure pipeline.inference is present when any service inference is requested
    if any(perm in requested_permissions for perm in ["asr.inference", "nmt.inference", "tts.inference"]):
        if "pipeline.inference" not in requested_permissions:
            requested_permissions.append("pipeline.inference")

    # Generate API key
    api_key_value = AuthUtils.generate_api_key()
    api_key_hash = AuthUtils.hash_api_key(api_key_value)
    api_key_encrypted = AuthUtils.encrypt_api_key(api_key_value)
    
    # Set expiration
    expires_at = None
    if api_key_data.expires_days:
        expires_at = datetime.utcnow() + timedelta(days=api_key_data.expires_days)
    
    # Create API key record
    db_api_key = APIKey(
        user_id=target_user_id,
        key_name=api_key_data.key_name,
        key_hash=api_key_hash,
        key_value_encrypted=api_key_encrypted,
        permissions=requested_permissions,
        expires_at=expires_at
    )
    
    db.add(db_api_key)
    await db.commit()
    await db.refresh(db_api_key)
    
    logger.info(f"API key created for user: {target_user.email} (created by: {current_user.email})")
    
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
    """
    List the current user's API keys.

    By default this returns only **active** keys (is_active = true),
    so revoked keys stay in the database for audit but are not shown
    in the standard listing.
    """
    result = await db.execute(
        select(APIKey).where(
            APIKey.user_id == current_user.id,
            APIKey.is_active.is_(True),
        )
    )
    api_keys = result.scalars().all()
    
    return [
        APIKeyResponse(
            id=key.id,
            key_name=key.key_name,
            key_value=AuthUtils.decrypt_api_key(key.key_value_encrypted) or "***",  # Decrypt and return actual value
            permissions=key.permissions,
            is_active=key.is_active,
            created_at=key.created_at,
            expires_at=key.expires_at,
            last_used=key.last_used
        )
        for key in api_keys
    ]


@app.get(
    "/api/v1/auth/api-keys/all",
    response_model=List[AdminAPIKeyWithUserResponse],
    tags=["Admin"],
)
async def list_all_api_keys_with_users(
    current_user: User = Depends(require_permission("apiKey", "read")),
    db: AsyncSession = Depends(get_db),
):
    """
    List **all** API keys in the system (active and inactive), including basic
    user details (user_id, email) for each key.

    Intended for admin/moderator dashboards and audits.
    """
    result = await db.execute(
        select(APIKey, User)
        .join(User, APIKey.user_id == User.id)
        .order_by(APIKey.created_at.desc())
    )
    rows = result.all()

    api_keys: List[AdminAPIKeyWithUserResponse] = []
    for api_key, user in rows:
        api_keys.append(
            AdminAPIKeyWithUserResponse(
                id=api_key.id,
                key_name=api_key.key_name,
                key_value=AuthUtils.decrypt_api_key(api_key.key_value_encrypted) or "***",
                permissions=api_key.permissions,
                is_active=api_key.is_active,
                created_at=api_key.created_at,
                expires_at=api_key.expires_at,
                last_used=api_key.last_used,
                user_id=user.id,
                user_email=user.email,
                username=user.username,
            )
        )

    return api_keys

@app.delete("/api/v1/auth/api-keys/{key_id}")
async def revoke_api_key(
    key_id: int,
    current_user: User = Depends(require_permission("apiKey", "delete")),
    db: AsyncSession = Depends(get_db)
):
    """
    Revoke an API key.
    
    - Requires `apiKey.delete` permission (e.g. ADMIN, MODERATOR).
    - Users with this permission can delete any API key.
    """
    result = await db.execute(
        select(APIKey).where(APIKey.id == key_id)
    )
    api_key = result.scalar_one_or_none()
    
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found"
        )
    
    api_key.is_active = False
    await db.commit()
    
    logger.info(f"API key revoked: {key_id} by user: {current_user.email}")
    return {"message": "API key revoked successfully"}


@app.patch("/api/v1/auth/api-keys/{key_id}", response_model=APIKeyResponse, tags=["Admin"])
async def update_api_key(
    key_id: int,
    update_data: APIKeyUpdate,
    current_user: User = Depends(require_permission("apiKey", "update")),
    db: AsyncSession = Depends(get_db),
):
    """
    Partially update an existing API key.

    - Requires `apiKey.update` permission (e.g. ADMIN, MODERATOR).
    - Allows changing `key_name` and `permissions`.
    - Keeps key value unchanged; only metadata is updated.
    """
    result = await db.execute(
        select(APIKey).where(APIKey.id == key_id)
    )
    api_key = result.scalar_one_or_none()

    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found",
        )
    # Apply updates if provided
    if update_data.key_name is not None:
        api_key.key_name = update_data.key_name
    if update_data.permissions is not None:
        updated_permissions = list(update_data.permissions or [])
        if "pipeline.inference" in updated_permissions:
            for perm in ["asr.inference", "nmt.inference", "tts.inference"]:
                if perm not in updated_permissions:
                    updated_permissions.append(perm)
        # Ensure pipeline.inference is present when any service inference is requested
        if any(perm in updated_permissions for perm in ["asr.inference", "nmt.inference", "tts.inference"]):
            if "pipeline.inference" not in updated_permissions:
                updated_permissions.append("pipeline.inference")
        api_key.permissions = updated_permissions
    # Allow toggling active status (soft-enable/soft-disable)
    if update_data.is_active is not None:
        api_key.is_active = update_data.is_active

    await db.commit()
    await db.refresh(api_key)

    logger.info(f"API key updated: {key_id} by user: {current_user.email}")

    # For security, we do not re‑expose the raw key value here; use "***"
    return APIKeyResponse(
        id=api_key.id,
        key_name=api_key.key_name,
        key_value="***",
        permissions=api_key.permissions,
        is_active=api_key.is_active,
        created_at=api_key.created_at,
        expires_at=api_key.expires_at,
        last_used=api_key.last_used,
    )

# OAuth2 Endpoints

@app.get("/api/v1/auth/oauth2/providers", response_model=List[OAuth2Provider], tags=["OAuth2"])
async def get_oauth2_providers():
    """Get available OAuth2 providers"""
    providers = []
    
    google_client_id = os.getenv("GOOGLE_CLIENT_ID")
    if google_client_id:
        providers.append(
            OAuth2Provider(
                provider="google",
                client_id=google_client_id,
                authorization_url="/api/v1/auth/oauth2/google/authorize",
                scope=["openid", "email", "profile"]
            )
        )
    
    github_client_id = os.getenv("GITHUB_CLIENT_ID")
    if github_client_id:
        providers.append(
            OAuth2Provider(
                provider="github",
                client_id=github_client_id,
                authorization_url="/api/v1/auth/oauth2/github/authorize",
                scope=["user:email"]
            )
        )
    
    return providers

@app.get("/api/v1/auth/oauth2/google/authorize", tags=["OAuth2"])
async def google_authorize(request: Request):
    """Initiate Google OAuth flow - redirects to Google"""
    if not redis_client:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Redis connection not available"
        )
    
    try:
        # Generate state token for CSRF protection
        state = await OAuthUtils.generate_state_token(redis_client)
        
        # Get redirect URI
        redirect_uri = os.getenv("GOOGLE_REDIRECT_URI")
        if not redirect_uri:
            # Construct from request if not set
            base_url = str(request.base_url).rstrip('/')
            redirect_uri = f"{base_url}/api/v1/auth/oauth2/google/callback"
        
        # Generate authorization URL
        auth_url = OAuthUtils.get_google_authorization_url(state, redirect_uri)
        
        logger.info(f"Redirecting to Google OAuth: {redirect_uri}")
        return RedirectResponse(url=auth_url)
    
    except ValueError as e:
        logger.error(f"Google OAuth configuration error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Google OAuth not properly configured"
        )
    except Exception as e:
        logger.error(f"Error initiating Google OAuth: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to initiate OAuth flow"
        )

@app.get("/api/v1/auth/oauth2/google/callback", tags=["OAuth2"])
async def google_callback(
    request: Request,
    code: str = Query(..., description="Authorization code from Google"),
    state: str = Query(..., description="State token for CSRF protection"),
    db: AsyncSession = Depends(get_db),
    multi_tenant_db: Optional[AsyncSession] = Depends(get_multi_tenant_db)
):
    """Handle Google OAuth callback - exchange code for tokens and create/login user"""
    if not redis_client:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Redis connection not available"
        )
    
    try:
        # 1. Validate state token (CSRF protection)
        if not await OAuthUtils.validate_state_token(redis_client, state):
            logger.warning(f"Invalid OAuth state token: {state[:16]}...")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid or expired state token. Please try again."
            )
        
        # 2. Get redirect URI
        redirect_uri = os.getenv("GOOGLE_REDIRECT_URI")
        if not redirect_uri:
            base_url = str(request.base_url).rstrip('/')
            redirect_uri = f"{base_url}/api/v1/auth/oauth2/google/callback"
        
        # 3. Exchange authorization code for tokens
        oauth_tokens = await OAuthUtils.exchange_google_code_for_tokens(code, redirect_uri)
        access_token = oauth_tokens.get("access_token")
        
        if not access_token:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to obtain access token from Google"
            )
        
        # 4. Get user info from Google
        user_info = await OAuthUtils.get_google_user_info(access_token)
        email = user_info.get("email")
        provider_user_id = user_info.get("id")
        
        if not email or not provider_user_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to retrieve user information from Google"
            )
        
        # 5. Create or link user account
        user = await AuthUtils.create_user_from_oauth(
            db=db,
            email=email,
            full_name=user_info.get("name"),
            avatar_url=user_info.get("picture"),
            provider_name="google",
            provider_user_id=provider_user_id,
            oauth_tokens=oauth_tokens
        )
        
        # 6. Get user roles
        user_roles = await AuthUtils.get_user_roles(db, user.id)
        
        # 6.5. Get tenant information
        tenant_info = await get_tenant_info(user.id, multi_tenant_db, user.is_tenant)
        
        # Build JWT payload with tenant info
        token_data = {
            "sub": str(user.id),
            "email": user.email,
            "username": user.username
        }
        
        # Add tenant info if available
        if tenant_info:
            token_data.update({
                "tenant_id": tenant_info["tenant_id"],
                "tenant_uuid": tenant_info["tenant_uuid"],
                "schema_name": tenant_info["schema_name"],
                "subscriptions": tenant_info.get("subscriptions", []),
                "user_subscriptions": tenant_info.get("user_subscriptions", []),
            })
        
        # 7. Generate JWT tokens
        access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        refresh_token_expires = timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
        
        jwt_access_token = AuthUtils.create_access_token(
            data=token_data,
            expires_delta=access_token_expires,
            roles=user_roles
        )
        
        jwt_refresh_token = AuthUtils.create_refresh_token(
            data=token_data,  # Include tenant info in refresh token too
            expires_delta=refresh_token_expires,
            roles=user_roles
        )
        
        # 8. Create session
        session_token = AuthUtils.generate_session_token()
        device_info = {
            "ip_address": request.client.host if request.client else None,
            "user_agent": request.headers.get("user-agent"),
            "oauth_provider": "google"
        }
        
        from sqlalchemy import insert as sa_insert
        now = datetime.utcnow()
        expires_at = now + refresh_token_expires
        await db.execute(
            sa_insert(UserSession.__table__).values(
                user_id=user.id,
                session_token=session_token,
                refresh_token=jwt_refresh_token,
                device_info=device_info,
                ip_address=request.client.host if request.client else None,
                user_agent=request.headers.get("user-agent"),
                is_active=True,
                expires_at=expires_at
            )
        )
        user.last_login = now
        await db.commit()
        
        logger.info(f"OAuth login successful for user: {email} via Google")
        
        # 9. Redirect to frontend with tokens (or return JSON)
        frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")
        redirect_url = (
            f"{frontend_url}/auth/callback?"
            f"access_token={jwt_access_token}&"
            f"refresh_token={jwt_refresh_token}&"
            f"token_type=bearer"
        )
        
        return RedirectResponse(url=redirect_url)
    
    except HTTPException:
        raise
    except ValueError as e:
        logger.error(f"Google OAuth configuration error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Google OAuth not properly configured"
        )
    except Exception as e:
        logger.error(f"Error in Google OAuth callback: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to complete OAuth authentication"
        )

# Role Management Endpoints (Admin only)

class AssignRoleRequest(BaseModel):
    user_id: int
    role_name: str

class RemoveRoleRequest(BaseModel):
    user_id: int
    role_name: str

class UserRolesResponse(BaseModel):
    user_id: int
    username: str
    email: str
    roles: List[str]

@app.post("/api/v1/auth/roles/assign", response_model=dict, tags=["Role Management"])
async def assign_role(
    role_data: AssignRoleRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Assign a role to a user (Admin only)"""
    # Check if current user is admin
    user_roles = await AuthUtils.get_user_roles(db, current_user.id)
    if "ADMIN" not in user_roles and not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": UNAUTHORIZED, "message": "Only administrators can assign roles"}
        )
    
    # Get target user
    target_user = await AuthUtils.get_user_by_id(db, role_data.user_id)
    if not target_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    # Get role
    result = await db.execute(select(Role).where(Role.name == role_data.role_name))
    role = result.scalar_one_or_none()
    if not role:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Role '{role_data.role_name}' not found"
        )
    
    # Check if user already has this exact role
    result = await db.execute(
        select(UserRole).where(
            UserRole.user_id == role_data.user_id,
            UserRole.role_id == role.id
        )
    )
    existing_same_role = result.scalar_one_or_none()
    if existing_same_role:
        return {"message": f"User already has role '{role_data.role_name}'"}
    
    # Check if user has any other roles (only one role per user allowed)
    result = await db.execute(
        select(UserRole).where(UserRole.user_id == role_data.user_id)
    )
    existing_roles = list(result.scalars().all())
    
    if existing_roles:
        # Get role names for logging
        role_ids = [r.role_id for r in existing_roles]
        if role_ids:
            role_result = await db.execute(
                select(Role.name).where(Role.id.in_(role_ids))
            )
            existing_role_names = list(role_result.scalars().all())
        else:
            existing_role_names = []
        
        # Remove ALL existing roles before assigning new one (only one role per user)
        for existing_role in existing_roles:
            await db.delete(existing_role)
        
        if existing_role_names:
            logger.warning(
                f"User {target_user.email} had {len(existing_roles)} role(s) [{', '.join(existing_role_names)}]. "
                f"Removed all existing roles before assigning new role '{role_data.role_name}'"
            )
        else:
            logger.warning(
                f"User {target_user.email} had {len(existing_roles)} role(s). "
                f"Removed all existing roles before assigning new role '{role_data.role_name}'"
            )
    
    # Assign the new role (only one role per user)
    user_role = UserRole(user_id=role_data.user_id, role_id=role.id)
    db.add(user_role)
    await db.commit()
    
    logger.info(f"Role '{role_data.role_name}' assigned to user {target_user.email} by {current_user.email}")
    
    # Prepare response message
    if existing_roles:
        response_message = f"Role '{role_data.role_name}' assigned successfully. Previous role(s) were replaced."
    else:
        response_message = f"Role '{role_data.role_name}' assigned successfully."
    
    return {
        "message": response_message,
        "user_id": role_data.user_id,
        "new_role": role_data.role_name
    }

@app.post("/api/v1/auth/roles/remove", response_model=dict, tags=["Role Management"])
async def remove_role(
    role_data: RemoveRoleRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Remove a role from a user (Admin only)"""
    # Check if current user is admin
    user_roles = await AuthUtils.get_user_roles(db, current_user.id)
    if "ADMIN" not in user_roles and not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": UNAUTHORIZED, "message": "Only administrators can remove roles"}
        )
    
    # Get target user
    target_user = await AuthUtils.get_user_by_id(db, role_data.user_id)
    if not target_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    # Get role
    result = await db.execute(select(Role).where(Role.name == role_data.role_name))
    role = result.scalar_one_or_none()
    if not role:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Role '{role_data.role_name}' not found"
        )
    
    # Remove role
    result = await db.execute(
        select(UserRole).where(
            UserRole.user_id == role_data.user_id,
            UserRole.role_id == role.id
        )
    )
    user_role = result.scalar_one_or_none()
    if not user_role:
        return {"message": f"User does not have role '{role_data.role_name}'"}
    
    await db.delete(user_role)
    await db.commit()
    
    logger.info(f"Role '{role_data.role_name}' removed from user {target_user.email} by {current_user.email}")
    return {"message": f"Role '{role_data.role_name}' removed successfully"}

@app.get("/api/v1/auth/roles/user/{user_id}", response_model=UserRolesResponse, tags=["Role Management"])
async def get_user_roles_endpoint(
    user_id: int,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Get roles for a user (Admin or self)"""
    try:
        # Check if current user is admin or viewing own profile
        user_roles = await AuthUtils.get_user_roles(db, current_user.id)
        if user_id != current_user.id and "ADMIN" not in user_roles and not current_user.is_superuser:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"code": UNAUTHORIZED, "message": "Only administrators can view other users' roles"}
            )
        
        target_user = await AuthUtils.get_user_by_id(db, user_id)
        if not target_user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        # Clean up duplicate roles before getting roles (ensure only one role per user)
        user_roles_result = await db.execute(
            select(UserRole)
            .where(UserRole.user_id == user_id)
            .order_by(UserRole.assigned_at.desc())
        )
        all_user_roles = list(user_roles_result.scalars().all())
        
        logger.info(f"[GET_ROLES] Found {len(all_user_roles)} role(s) for user {user_id} (email: {target_user.email})")
        
        if len(all_user_roles) > 1:
            # Get role names for logging
            role_ids = [ur.role_id for ur in all_user_roles]
            role_names_result = await db.execute(
                select(Role).where(Role.id.in_(role_ids))
            )
            roles_list = list(role_names_result.scalars().all())
            role_map = {r.id: r.name for r in roles_list}
            old_role_names = [role_map.get(ur.role_id, "UNKNOWN") for ur in all_user_roles[1:]]
            most_recent_role_name = role_map.get(all_user_roles[0].role_id, "UNKNOWN")
            
            # Keep only the most recent role, delete all others
            deleted_count = 0
            for old_role in all_user_roles[1:]:
                await db.delete(old_role)
                deleted_count += 1
            
            await db.flush()
            await db.commit()
            
            logger.warning(
                f"Cleaned up {deleted_count} duplicate role(s) [{', '.join(old_role_names)}] "
                f"for user {user_id} (email: {target_user.email}). Kept only: {most_recent_role_name}"
            )
        
        # Refresh the session to ensure we see the latest data after cleanup
        await db.refresh(target_user)
        
        # Now get the roles (should be only one after cleanup)
        # Query directly to ensure we get the current state
        if len(all_user_roles) > 1:
            # After cleanup, query again to get only the remaining role
            remaining_role_result = await db.execute(
                select(Role.name)
                .join(UserRole, Role.id == UserRole.role_id)
                .where(UserRole.user_id == user_id)
                .order_by(UserRole.assigned_at.desc())
                .limit(1)
            )
            roles = list(remaining_role_result.scalars().all())
        else:
            # Use the utility function if no cleanup was needed
            roles = await AuthUtils.get_user_roles(db, user_id)
        
        logger.info(f"Returning {len(roles)} role(s) for user {user_id}: {roles}")
        return UserRolesResponse(
            user_id=target_user.id,
            username=target_user.username,
            email=target_user.email,
            roles=roles
        )
    except Exception as e:
        logger.error(f"Error in get_user_roles_endpoint for user {user_id}: {str(e)}", exc_info=True)
        raise

@app.get("/api/v1/auth/roles/list", response_model=List[dict], tags=["Role Management"])
async def list_roles(
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """List all available roles (Admin only)"""
    result = await db.execute(select(Role))
    roles = result.scalars().all()
    return [{"id": role.id, "name": role.name, "description": role.description} for role in roles]


# Admin endpoints
@app.get("/api/v1/auth/users/{user_id}", response_model=UserDetailResponse, tags=["Admin"])
async def get_user_details(
    user_id: int,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Get user details by user ID (Admin only)
    
    Returns user information including:
    - userid
    - username
    - emailid
    - phonenumber
    - full_name
    - is_active
    - is_verified
    - is_superuser
    - created_at
    - last_login
    """
    user = await AuthUtils.get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User with ID {user_id} not found"
        )
    
    return UserDetailResponse(
        id=user.id,
        username=user.username,
        email=user.email,
        phone_number=user.phone_number,
        full_name=user.full_name,
        is_active=user.is_active,
        is_verified=user.is_verified,
        is_superuser=user.is_superuser,
        created_at=user.created_at,
        last_login=user.last_login
    )


@app.get("/api/v1/auth/permissions", response_model=List[PermissionResponse], tags=["Admin"])
async def get_all_permissions(
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Get all permissions from the permissions table (Admin only)
    
    Returns a list of all permissions with:
    - id
    - name
    - resource
    - action
    - created_at
    """
    result = await db.execute(select(Permission).order_by(Permission.name))
    permissions = result.scalars().all()
    
    return [
        PermissionResponse(
            id=perm.id,
            name=perm.name,
            resource=perm.resource,
            action=perm.action,
            created_at=perm.created_at
        )
        for perm in permissions
    ]


@app.get("/api/v1/auth/permission/list", response_model=List[str], tags=["Role Management"])
async def get_permission_list(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get list of inference permissions only (for API keys).
    
    Returns only inference permissions that can be assigned to API keys:
    - asr.inference
    - tts.inference
    - nmt.inference
    - audio-lang.inference
    - language-detection.inference
    - language-diarization.inference
    - ner.inference
    - ocr.inference
    - speaker-diarization.inference
    - transliteration.inference
    - pipeline.inference
    - llm.inference
    """
    # Define allowed inference permissions for API keys
    allowed_permissions = [
        "asr.inference",
        "tts.inference",
        "nmt.inference",
        "audio-lang.inference",
        "language-detection.inference",
        "language-diarization.inference",
        "ner.inference",
        "ocr.inference",
        "speaker-diarization.inference",
        "transliteration.inference",
        "pipeline.inference",
        "llm.inference"
    ]
    
    return allowed_permissions


@app.get("/api/v1/auth/users", response_model=List[UserListResponse], tags=["Admin"])
async def get_all_users(
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Get all users (Admin only)
    
    Returns a list of all users with:
    - userid
    - username
    - emailid
    - phonenumber
    """
    result = await db.execute(select(User).order_by(User.id))
    users = result.scalars().all()
    
    return [
        UserListResponse(
            id=user.id,
            username=user.username,
            email=user.email,
            phone_number=user.phone_number
        )
        for user in users
    ]


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8081)

