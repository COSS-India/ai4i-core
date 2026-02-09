"""
Authentication provider for FastAPI routes with API key validation and Redis caching.
"""
from fastapi import Request, Header, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, Dict, Any, Tuple
import hashlib
import json
import os

import httpx

from repositories.api_key_repository import ApiKeyRepository
from repositories.user_repository import UserRepository
from models.auth_models import ApiKeyDB, UserDB
from middleware.exceptions import AuthenticationError, InvalidAPIKeyError, ExpiredAPIKeyError

from db_connection import get_auth_db_session
from logger import logger

AUTH_SERVICE_URL = str(os.getenv("AUTH_SERVICE_URL", "http://auth-service:8081"))
AUTH_HTTP_TIMEOUT = float(os.getenv("AUTH_HTTP_TIMEOUT", "10"))



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


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


async def validate_api_key(api_key: str, db: AsyncSession, redis_client) -> Tuple[ApiKeyDB, UserDB]:
    """Validate API key and return user and API key data."""
    try:
        # Hash the API key
        key_hash = hash_api_key(api_key)
        
        # First check Redis cache
        cache_key = f"api_key:{key_hash}"
        cached_data = None
        if redis_client:
            # cached_data = await redis_client.get(cache_key)
            cached_data = redis_client.get(cache_key)
        
        if cached_data:
            try:
                cache_data = json.loads(cached_data)
                api_key_id = cache_data.get("api_key_id")
                user_id = cache_data.get("user_id")
                is_active = cache_data.get("is_active", False)
                
                if is_active:
                    # Get fresh data from database
                    api_key_repo = ApiKeyRepository(db)
                    api_key_db = await api_key_repo.find_by_id(api_key_id)
                    
                    if api_key_db and await api_key_repo.is_key_valid(api_key_db):
                        # Update last used
                        await api_key_repo.update_last_used(api_key_id)
                        return api_key_db, api_key_db.user
            except (json.JSONDecodeError, KeyError) as e:
                logger.warning(f"Invalid cache data for API key: {e}")
        
        # If not in cache or invalid, query database
        api_key_repo = ApiKeyRepository(db)
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
        if redis_client:
            cache_data = {
                "api_key_id": api_key_db.id,
                "user_id": api_key_db.user_id,
                "is_active": api_key_db.is_active
            }
            # await redis_client.setex(cache_key, 300, json.dumps(cache_data))

            redis_client.setex(cache_key, 300, json.dumps(cache_data))
        
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
    x_auth_source: Optional[str] = Header(default=None, alias="X-Auth-Source"),
    db: AsyncSession = Depends(get_auth_db_session)
) -> Dict[str, Any]:
    """Authentication provider for multi-tenant routes. Uses AUTH_TOKEN (Bearer JWT) by default; API key not required."""
    auth_enabled = _env_bool("AUTH_ENABLED", True)
    require_api_key = _env_bool("REQUIRE_API_KEY", False)  # Multi-tenant: auth token only by default
    allow_anonymous = _env_bool("ALLOW_ANONYMOUS_ACCESS", False)
    # Default to AUTH_TOKEN so all multi-tenant APIs work with Bearer token only; API key not required
    auth_source = (x_auth_source or "AUTH_TOKEN").upper()

    if not auth_enabled or (allow_anonymous and not require_api_key):
        # Populate anonymous context
        request.state.user_id = None
        request.state.api_key_id = None
        request.state.api_key_name = None
        request.state.user_email = None
        request.state.is_authenticated = False

        return {
            "user_id": None,
            "api_key_id": None,
            "user": None,
            "api_key": None,
        }

    if auth_source == "AUTH_TOKEN":
        return await authenticate_bearer_token(request, authorization)

    try:
        # Extract API key from X-API-Key header first, then fallback to Authorization header
        api_key = x_api_key or get_api_key_from_header(authorization)
        
        if not api_key:
            raise AuthenticationError("Missing API key")
        
        # Get Redis client from app state
        redis_client = getattr(request.app.state, "redis_client", None)
        
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
    x_auth_source: Optional[str] = Header(default=None, alias="X-Auth-Source"),
    db: AsyncSession = Depends(get_auth_db_session)
) -> Optional[Dict[str, Any]]:
    """Optional authentication provider that doesn't raise exception if no auth provided."""
    try:
        return await AuthProvider(request, authorization, x_api_key, x_auth_source, db)
    except AuthenticationError:
        # Return None for optional auth
        return None


async def authenticate_bearer_token(request: Request, authorization: Optional[str]) -> Dict[str, Any]:
    """Validate JWT access token via auth service."""
    if not authorization or not authorization.startswith("Bearer "):
        raise AuthenticationError("Missing bearer token")

    token = authorization.split(" ", 1)[1]
    headers = {"Authorization": f"Bearer {token}"}

    try:
        async with httpx.AsyncClient(timeout=AUTH_HTTP_TIMEOUT) as client:
            response = await client.get(f"{AUTH_SERVICE_URL}/api/v1/auth/validate", headers=headers)
    except Exception as exc:
        logger.error(f"Auth service validation failed: {exc}")
        raise AuthenticationError("Failed to validate access token")

    if response.status_code != 200:
        logger.warning("Auth service rejected token with status %s", response.status_code)
        raise AuthenticationError("Invalid or expired token")

    data = response.json() if response.content else {}

    user_id = data.get("user_id") or data.get("sub")
    username = data.get("username") or data.get("email")

    request.state.user_id = user_id
    request.state.api_key_id = None
    request.state.api_key_name = None
    request.state.user_email = data.get("email")
    request.state.is_authenticated = True

    return {
        "user_id": user_id,
        "api_key_id": None,
        "user": {
            "username": username,
            "email": data.get("email"),
            "permissions": data.get("permissions"),
        },
        "api_key": None,
    }


