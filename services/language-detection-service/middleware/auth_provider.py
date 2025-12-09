"""
Authentication provider for FastAPI routes with API key validation and Redis caching.
"""
import os
from fastapi import Request, Header, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, Dict, Any, Tuple
import hashlib
import json
import logging
from jose import JWTError, jwt
import httpx

from repositories.api_key_repository import APIKeyRepository
from repositories.user_repository import UserRepository
from repositories.language_detection_repository import get_db_session
from models.auth_models import APIKey, User
from middleware.exceptions import AuthenticationError, InvalidAPIKeyError, ExpiredAPIKeyError

logger = logging.getLogger(__name__)

# JWT Configuration
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "dhruva-jwt-secret-key-2024-super-secure")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
AUTH_SERVICE_URL = os.getenv("AUTH_SERVICE_URL", "http://auth-service:8081")


def get_api_key_from_header(authorization: Optional[str] = Header(None)) -> Optional[str]:
    """Extract API key from Authorization header."""
    if not authorization:
        return None
    
    # Support formats: "Bearer <key>", "<key>", "ApiKey <key>"
    if authorization.startswith("Bearer "):
        return authorization[7:]
    elif authorization.startswith("ApiKey "):
        return authorization[7:]
    else:
        return authorization


def hash_api_key(api_key: str) -> str:
    """Hash API key using SHA256."""
    return hashlib.sha256(api_key.encode()).hexdigest()


async def validate_jwt_token(token: str, request: Request) -> Optional[Tuple[int, str]]:
    """Validate JWT token and return (user_id, email) or None."""
    try:
        # First try to verify locally
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        if payload.get("type") == "access":
            user_id = int(payload.get("sub", 0))
            email = payload.get("email", "")
            return (user_id, email)
    except JWTError:
        pass
    
    # If local verification fails, check with auth service
    try:
        http_client = getattr(request.app.state, "http_client", None)
        if not http_client:
            http_client = httpx.AsyncClient(timeout=10.0)
        
        response = await http_client.post(
            f"{AUTH_SERVICE_URL}/api/v1/auth/validate",
            headers={"Authorization": f"Bearer {token}"}
        )
        if response.status_code == 200:
            data = response.json()
            user_id = data.get("user_id")
            email = data.get("email", "")
            return (user_id, email)
    except Exception as e:
        logger.warning(f"Auth service validation failed: {e}")
    
    return None


async def validate_api_key(api_key: str, db: AsyncSession, redis_client) -> Tuple[APIKey, User]:
    """Validate API key and return user and API key data."""
    try:
        # Hash the API key
        key_hash = hash_api_key(api_key)
        
        # First check Redis cache
        cache_key = f"api_key:{key_hash}"
        cached_data = await redis_client.get(cache_key)
        
        if cached_data:
            try:
                cache_data = json.loads(cached_data)
                api_key_id = cache_data.get("api_key_id")
                user_id = cache_data.get("user_id")
                is_active = cache_data.get("is_active", False)
                
                if is_active:
                    # Get fresh data from database
                    api_key_repo = APIKeyRepository(db)
                    api_key_db = await api_key_repo.find_by_id(api_key_id)
                    
                    if api_key_db and await api_key_repo.is_key_valid(api_key_db):
                        # Update last used
                        await api_key_repo.update_last_used(api_key_id)
                        return api_key_db, api_key_db.user
            except (json.JSONDecodeError, KeyError) as e:
                logger.warning(f"Invalid cache data for API key: {e}")
        
        # If not in cache or invalid, query database
        api_key_repo = APIKeyRepository(db)
        api_key_db = await api_key_repo.find_by_key_hash(key_hash)
        
        if not api_key_db:
            raise InvalidAPIKeyError("API key not found")
        
        # Validate API key
        if not await api_key_repo.is_key_valid(api_key_db):
            if not api_key_db.is_active:
                raise InvalidAPIKeyError("API key is inactive")
            else:
                raise ExpiredAPIKeyError("API key has expired")
        
        # Cache the result
        cache_data = {
            "api_key_id": api_key_db.id,
            "user_id": api_key_db.user_id,
            "is_active": api_key_db.is_active
        }
        await redis_client.setex(cache_key, 300, json.dumps(cache_data))  # 5 minute TTL
        
        # Update last used
        await api_key_repo.update_last_used(api_key_db.id)
        
        return api_key_db, api_key_db.user
        
    except (InvalidAPIKeyError, ExpiredAPIKeyError):
        raise
    except Exception as e:
        logger.error(f"Error validating API key: {e}")
        raise AuthenticationError("Failed to validate API key")


async def AuthProvider(
    request: Request,
    authorization: Optional[str] = Header(None, alias="Authorization"),
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    x_auth_source: str = Header(default="API_KEY", alias="X-Auth-Source"),
    db: AsyncSession = Depends(get_db_session)
) -> Dict[str, Any]:
    """Authentication provider dependency for FastAPI routes."""
    try:
        # Check if Authorization header contains Bearer token (JWT)
        is_bearer_token = authorization and authorization.startswith("Bearer ")
        
        if is_bearer_token:
            # Extract JWT token
            token = authorization[7:]  # Remove "Bearer " prefix
            
            # Validate JWT token
            jwt_result = await validate_jwt_token(token, request)
            if jwt_result:
                user_id, email = jwt_result
                
                # Get user from database
                user_repo = UserRepository(db)
                user_db = await user_repo.find_by_id(user_id)
                
                if not user_db:
                    raise AuthenticationError("User not found")
                
                # Populate request state with auth context
                request.state.user_id = user_db.id
                request.state.api_key_id = None
                request.state.api_key_name = None
                request.state.user_email = user_db.email
                request.state.is_authenticated = True
                
                # Return auth context
                return {
                    "user_id": user_db.id,
                    "api_key_id": None,
                    "user": user_db,
                    "api_key": None
                }
            else:
                raise AuthenticationError("Invalid or expired token")
        
        # If not Bearer token, treat as API key
        # Extract API key from authorization header
        api_key = get_api_key_from_header(authorization)
        
        # If not in Authorization header, check X-API-Key header (for gateway compatibility)
        if not api_key:
            # Check X-API-Key header parameter first
            if x_api_key:
                api_key = x_api_key
            # Fallback to direct header access (case-insensitive)
            else:
                api_key = request.headers.get("X-API-Key") or request.headers.get("x-api-key")
        
        if not api_key:
            raise AuthenticationError("Missing API key")
        
        # Get Redis client from app state
        redis_client = request.app.state.redis_client
        
        # Validate API key
        api_key_db, user_db = await validate_api_key(api_key, db, redis_client)
        
        # Populate request state with auth context
        request.state.user_id = user_db.id
        request.state.api_key_id = api_key_db.id
        request.state.api_key_name = api_key_db.name
        request.state.user_email = user_db.email
        request.state.is_authenticated = True
        
        # Return auth context
        return {
            "user_id": user_db.id,
            "api_key_id": api_key_db.id,
            "user": user_db,
            "api_key": api_key_db
        }
        
    except (AuthenticationError, InvalidAPIKeyError, ExpiredAPIKeyError):
        raise
    except Exception as e:
        logger.error(f"Authentication error: {e}")
        raise AuthenticationError("Authentication failed")


async def OptionalAuthProvider(
    request: Request,
    authorization: Optional[str] = Header(None, alias="Authorization"),
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    x_auth_source: str = Header(default="API_KEY", alias="X-Auth-Source"),
    db: AsyncSession = Depends(get_db_session)
) -> Optional[Dict[str, Any]]:
    """Optional authentication provider that doesn't raise exception if no auth provided."""
    try:
        return await AuthProvider(request, authorization, x_api_key, x_auth_source, db)
    except AuthenticationError:
        # Return None for optional auth
        return None
