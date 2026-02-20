"""
Authentication provider for FastAPI routes with API key validation and Redis caching.
"""
from fastapi import Request, Header, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, Dict, Any, Tuple
import hashlib
import json
import logging
import httpx
import os

from repositories.api_key_repository import ApiKeyRepository
from repositories.user_repository import UserRepository
from models.auth_models import ApiKeyDB, UserDB
from middleware.exceptions import AuthenticationError, InvalidAPIKeyError, ExpiredAPIKeyError, AuthorizationError

logger = logging.getLogger(__name__)

# Constants for auth service communication
AUTH_SERVICE_URL = os.getenv("AUTH_SERVICE_URL", "http://auth-service:8081")
AUTH_HTTP_TIMEOUT = float(os.getenv("AUTH_HTTP_TIMEOUT", "5.0"))


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


def determine_service_and_action(request: Request) -> Tuple[str, str]:
    """
    Determine service name and action from request path and method.
    
    Returns:
        Tuple of (service_name, action)
        service_name: asr, nmt, tts, pipeline, model-management, llm
        action: read or inference
    """
    path = request.url.path.lower()
    method = request.method.upper()
    
    # Extract service name from path (e.g., /api/v1/llm/... -> llm)
    service = None
    for svc in ["asr", "nmt", "tts", "pipeline", "model-management", "llm"]:
        if f"/api/v1/{svc}/" in path or path.endswith(f"/api/v1/{svc}"):
            service = svc
            break
    
    if not service:
        # Default to llm for this service
        service = "llm"
    
    # Determine action based on path and method
    if "/inference" in path and method == "POST":
        action = "inference"
    elif method == "GET" or "/services" in path or "/models" in path or "/languages" in path:
        action = "read"
    else:
        # Default to read for other operations
        action = "read"
    
    return service, action


async def authenticate_bearer_token(request: Request, authorization: Optional[str]) -> Dict[str, Any]:
    """
    Validate JWT access token locally (signature + expiry check).
    Kong already validated the token, this is a defense-in-depth check.
    """
    from jose import JWTError, jwt
    
    if not authorization or not authorization.startswith("Bearer "):
        raise AuthenticationError("Missing bearer token")

    token = authorization.split(" ", 1)[1]
    
    # JWT Configuration for local verification
    JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "dhruva-jwt-secret-key-2024-super-secure")
    JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")

    try:
        # Verify JWT signature and expiry locally
        payload = jwt.decode(
            token,
            JWT_SECRET_KEY,
            algorithms=[JWT_ALGORITHM],
            options={"verify_signature": True, "verify_exp": True}
        )
        
        # Extract user info from JWT claims
        user_id = payload.get("sub") or payload.get("user_id")
        email = payload.get("email", "")
        username = payload.get("username") or payload.get("email", "")
        roles = payload.get("roles", [])
        token_type = payload.get("type", "")
        
        # Ensure this is an access token
        if token_type != "access":
            raise AuthenticationError("Invalid token type")
        
        if not user_id:
            raise AuthenticationError("User ID not found in token")

        # Populate request state
        request.state.user_id = int(user_id) if isinstance(user_id, (str, int)) else user_id
        request.state.api_key_id = None
        request.state.api_key_name = None
        request.state.user_email = email
        request.state.is_authenticated = True

        return {
            "user_id": int(user_id) if isinstance(user_id, (str, int)) else user_id,
            "api_key_id": None,
            "user": {
                "username": username,
                "email": email,
                "roles": roles,
            },
            "api_key": None,
        }
        
    except JWTError as e:
        logger.warning(f"JWT verification failed: {e}")
        raise AuthenticationError("Invalid or expired token")
    except Exception as e:
        logger.error(f"Unexpected error during JWT verification: {e}")
        raise AuthenticationError("Failed to verify token")


async def validate_api_key_permissions(api_key: str, service: str, action: str, user_id: Optional[int] = None) -> Dict[str, Any]:
    """
    Validate API key has required permissions by calling auth-service.
    
    Args:
        api_key: The API key to validate
        service: Service name (asr, nmt, tts, llm, etc.)
        action: Action type (read, inference)
        user_id: Optional user ID from JWT for ownership check in BOTH mode
    
    Returns:
        Dict with validation result including 'valid', 'message', 'user_id', 'permissions'
    
    Raises:
        AuthorizationError: If permission check fails
    """
    try:
        validate_url = f"{AUTH_SERVICE_URL}/api/v1/auth/validate-api-key"
        
        payload = {
            "api_key": api_key,
            "service": service,
            "action": action
        }
        if user_id is not None:
            payload["user_id"] = user_id
        
        # Call auth-service to validate permissions
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.post(
                validate_url,
                json=payload
            )
            
            if response.status_code == 200:
                result = response.json()
                # Return full result so callers can check valid and get user_id
                return result
            else:
                logger.error(f"Auth service returned status {response.status_code}: {response.text}")
                raise AuthorizationError("Failed to validate API key permissions")
                
    except httpx.TimeoutException:
        logger.error("Timeout calling auth-service for permission validation")
        raise AuthorizationError("Permission validation service unavailable")
    except httpx.RequestError as e:
        logger.error(f"Error calling auth-service: {e}")
        raise AuthorizationError("Failed to validate API key permissions")
    except AuthorizationError:
        raise
    except Exception as e:
        logger.error(f"Unexpected error validating permissions: {e}")
        raise AuthorizationError("Permission validation failed")


async def validate_api_key(api_key: str, db: AsyncSession, redis_client) -> Tuple[ApiKeyDB, UserDB]:
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


async def get_db_session(request: Request) -> AsyncSession:
    """Dependency to get database session from app state."""
    return request.app.state.db_session_factory()


async def AuthProvider(
    request: Request,
    authorization: Optional[str] = Header(None, alias="Authorization"),
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    x_auth_source: str = Header(default="API_KEY", alias="X-Auth-Source"),
    db: AsyncSession = Depends(get_db_session)
) -> Dict[str, Any]:
    """Authentication provider dependency for FastAPI routes."""
    auth_source = (x_auth_source or "API_KEY").upper()
    
    # Handle Bearer token authentication (user tokens - no permission check needed)
    if auth_source == "AUTH_TOKEN":
        return await authenticate_bearer_token(request, authorization)
    
    # Handle BOTH Bearer token AND API key (already validated by API Gateway)
    if auth_source == "BOTH":
        try:
            # 1) Validate Bearer token to get user info
            bearer_result = await authenticate_bearer_token(request, authorization)
            jwt_user_id = bearer_result.get("user_id")
            
            # Store JWT payload for tenant context resolution
            from jose import jwt
            JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "dhruva-jwt-secret-key-2024-super-secure")
            JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
            token = authorization.split(" ", 1)[1] if authorization else ""
            try:
                jwt_payload = jwt.decode(
                    token,
                    JWT_SECRET_KEY,
                    algorithms=[JWT_ALGORITHM],
                    options={"verify_signature": True, "verify_exp": True}
                )
                request.state.jwt_payload = jwt_payload
            except Exception:
                pass  # If JWT decode fails, continue without payload
            
            # 2) Extract API key
            api_key = x_api_key or get_api_key_from_header(authorization)
            if not api_key:
                raise AuthenticationError("Missing API key")
            
            # 3) Validate API key + permissions via auth-service (single source of truth),
            # passing jwt_user_id so auth-service can enforce ownership.
            service, action = determine_service_and_action(request)
            try:
                auth_result = await validate_api_key_permissions(api_key, service, action, user_id=jwt_user_id)
            except (AuthorizationError, InvalidAPIKeyError, ExpiredAPIKeyError) as e:
                # Distinguish between permission/ownership vs generic key problems:
                # - AuthorizationError: permission/ownership -> propagate as AuthorizationError
                # - Invalid/Expired key: treat as authentication problem
                logger.error(f"API key validation failed in BOTH mode: {e}")
                if isinstance(e, AuthorizationError):
                    # Preserve the detailed permission message from auth-service
                    raise AuthorizationError(str(e))
                raise AuthenticationError("API key does not belong to the authenticated user")
            
            # Explicitly check if auth-service returned valid=false (shouldn't happen if exception was raised)
            if not auth_result.get("valid", False):
                error_msg = auth_result.get("message", "API key does not belong to the authenticated user")
                logger.error(f"Auth-service returned valid=false: {error_msg}")
                # Ownership vs permission: keep ownership as AuthenticationError, others as AuthorizationError
                if "does not belong" in error_msg.lower() or "ownership" in error_msg.lower():
                    raise AuthenticationError("API key does not belong to the authenticated user")
                raise AuthorizationError(error_msg)
            
            # 4) Populate request state – keep JWT as primary identity
            request.state.user_id = jwt_user_id
            request.state.api_key_id = None
            request.state.api_key_name = None
            request.state.user_email = bearer_result.get("user", {}).get("email")
            request.state.is_authenticated = True
            
            return bearer_result
        except AuthenticationError:
            # Re-raise AuthenticationError as-is
            raise
        except Exception as e:
            logger.error(f"Unexpected error in BOTH authentication mode: {e}", exc_info=True)
            # Even on unexpected errors we normalize the external message so callers
            # don't see fluctuating error strings for the same request.
            raise AuthenticationError("API key does not belong to the authenticated user")
    
    # Handle API key authentication (requires permission check)
    try:
        # Extract API key from X-API-Key header first, then Authorization header
        api_key = x_api_key or get_api_key_from_header(authorization)
        
        if not api_key:
            raise AuthenticationError("Missing API key")
        
        # Get Redis client from app state
        redis_client = request.app.state.redis_client
        
        # Validate API key exists and is active
        api_key_db, user_db = await validate_api_key(api_key, db, redis_client)
        
        # Determine service and action from request
        service, action = determine_service_and_action(request)
        
        # Validate API key has required permissions via auth-service
        try:
            auth_result = await validate_api_key_permissions(api_key, service, action)
        except (AuthorizationError, InvalidAPIKeyError, ExpiredAPIKeyError) as e:
            logger.error(f"API key permission validation failed: {e}")
            if isinstance(e, AuthorizationError):
                # Permission/ownership errors should be surfaced as AuthorizationError
                raise AuthorizationError(str(e))
            raise AuthenticationError("API key does not belong to the authenticated user")
        
        # Explicitly check if auth-service returned valid=false
        if not auth_result.get("valid", False):
            error_msg = auth_result.get("message", "Permission denied")
            logger.error(f"Auth-service returned valid=false: {error_msg}")
            if "does not belong" in error_msg.lower() or "ownership" in error_msg.lower():
                raise AuthenticationError("API key does not belong to the authenticated user")
            raise AuthorizationError(error_msg)
        
        # For API_KEY-only mode, we may not have a JWT; use auth-service user_id if present
        user_id = auth_result.get("user_id") or user_db.id
        
        # Populate request state with auth context
        request.state.user_id = user_id
        request.state.api_key_id = api_key_db.id
        request.state.api_key_name = api_key_db.name
        request.state.user_email = user_db.email
        request.state.is_authenticated = True
        
        # Return auth context
        return {
            "user_id": user_id,
            "api_key_id": api_key_db.id,
            "user": user_db,
            "api_key": api_key_db
        }
        
    except AuthenticationError:
        # Re-raise AuthenticationError as-is
        raise
    except Exception as e:
        logger.error(f"Authentication error: {e}", exc_info=True)
        raise AuthenticationError("API key does not belong to the authenticated user")


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
