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
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode

from repositories.api_key_repository import ApiKeyRepository
from repositories.user_repository import UserRepository
from repositories.nmt_repository import get_db_session
from models.auth_models import ApiKeyDB, UserDB
from middleware.exceptions import AuthenticationError, InvalidAPIKeyError, ExpiredAPIKeyError, AuthorizationError

logger = logging.getLogger(__name__)
tracer = trace.get_tracer("nmt-service")

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
    
    # Extract service name from path (e.g., /api/v1/nmt/... -> nmt)
    service = None
    for svc in ["asr", "nmt", "tts", "pipeline", "model-management", "llm"]:
        if f"/api/v1/{svc}/" in path or path.endswith(f"/api/v1/{svc}"):
            service = svc
            break
    
    if not service:
        # Default to nmt for this service
        service = "nmt"
    
    # Determine action based on path and method
    if "/inference" in path and method == "POST":
        action = "inference"
    elif method == "GET" or "/services" in path or "/models" in path or "/languages" in path:
        action = "read"
    else:
        # Default to read for other operations
        action = "read"
    
    return service, action


async def _authenticate_bearer_token_impl(request: Request, authorization: Optional[str]) -> Dict[str, Any]:
    """Internal implementation of bearer token authentication."""
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


async def authenticate_bearer_token(request: Request, authorization: Optional[str]) -> Dict[str, Any]:
    """
    Validate JWT access token locally (signature + expiry check).
    Kong already validated the token, this is a defense-in-depth check.
    """
    if not tracer:
        return await _authenticate_bearer_token_impl(request, authorization)
    
    # Collapsed: JWT verification is now part of parent "Request Authorization" span
    # No separate span for JWT verification to reduce noise
    # Collapsed: Decision logic is now just conditional checks
    if not authorization or not authorization.startswith("Bearer "):
        raise AuthenticationError("Missing bearer token")

    token = authorization.split(" ", 1)[1]

    try:
        result = await _authenticate_bearer_token_impl(request, authorization)
        return result
    except AuthenticationError as e:
        raise


async def _validate_api_key_permissions_impl(api_key: str, service: str, action: str) -> None:
    """Internal implementation of API key permission validation."""
    try:
        validate_url = f"{AUTH_SERVICE_URL}/api/v1/auth/validate-api-key"
        
        # Call auth-service to validate permissions
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.post(
                validate_url,
                json={
                    "api_key": api_key,
                    "service": service,
                    "action": action
                }
            )
            
            if response.status_code == 200:
                result = response.json()
                if result.get("valid"):
                    return
                else:
                    error_msg = result.get("message", "Permission denied")
                    raise AuthorizationError(error_msg)
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


async def validate_api_key_permissions(api_key: str, service: str, action: str) -> None:
    """
    Validate API key has required permissions by calling auth-service.
    
    Args:
        api_key: The API key to validate
        service: Service name (asr, nmt, tts, etc.)
        action: Action type (read, inference)
    
    Raises:
        AuthorizationError: If permission check fails
    """
    if not tracer:
        return await _validate_api_key_permissions_impl(api_key, service, action)
    
    # Business-level span: Authentication validation
    with tracer.start_as_current_span("Authentication Validation") as validate_span:
        validate_span.set_attribute("purpose", "Validates user authentication and permissions before processing the request")
        validate_span.set_attribute("user_visible", False)
        validate_span.set_attribute("impact_if_slow", "Request is delayed - user may experience slower response times")
        validate_span.set_attribute("owner", "Security Team")
        validate_span.set_attribute("auth.operation", "validate_api_key")
        validate_span.set_attribute("auth.service", service)
        validate_span.set_attribute("auth.action", action)
        validate_span.set_attribute("auth.api_key_present", bool(api_key))
        validate_span.set_attribute("auth.api_key_length", len(api_key) if api_key else 0)
        
        # Collapsed: Internal decision logic is now just conditional checks
        # No separate span for decision points to reduce noise
        if not api_key:
            validate_span.set_attribute("error", True)
            validate_span.set_attribute("error.type", "MissingAPIKey")
            validate_span.set_attribute("error.reason", "api_key_missing")
            validate_span.set_attribute("error.message", "API key is missing")
            validate_span.set_status(Status(StatusCode.ERROR, "API key missing"))
            raise AuthorizationError("API key is missing")
        
        # Collapsed: Auth service call is now part of parent span
        # No separate span for the HTTP call to reduce noise
        try:
            await _validate_api_key_permissions_impl(api_key, service, action)
            validate_span.set_attribute("auth.validation_result", "approved")
            validate_span.add_event("Auth Validation Successful")
            validate_span.set_status(Status(StatusCode.OK))
        except AuthorizationError as e:
            validate_span.set_attribute("auth.validation_result", "rejected")
            validate_span.set_attribute("error.type", "AuthorizationError")
            validate_span.set_attribute("error.reason", "permission_denied")
            validate_span.set_attribute("error.message", str(e))
            validate_span.add_event("Auth Validation Failed", {"error_message": str(e)})
            validate_span.set_status(Status(StatusCode.ERROR, str(e)))
            raise


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


async def _auth_provider_impl(
    request: Request,
    authorization: Optional[str],
    x_api_key: Optional[str],
    x_auth_source: str,
    db: AsyncSession
) -> Dict[str, Any]:
    """Internal implementation of authentication provider."""
    auth_source = (x_auth_source or "API_KEY").upper()
    
    # Handle Bearer token authentication (user tokens - no permission check needed)
    if auth_source == "AUTH_TOKEN":
        return await _authenticate_bearer_token_impl(request, authorization)
    
    # Handle BOTH Bearer token AND API key (already validated by API Gateway)
    if auth_source == "BOTH":
        # Validate Bearer token to get user info
        bearer_result = await _authenticate_bearer_token_impl(request, authorization)
        
        # Extract API key
        api_key = x_api_key or get_api_key_from_header(authorization)
        if not api_key:
            raise AuthenticationError("Missing API key")
        
        # Validate API key permissions via auth-service (skip database lookup)
        service, action = determine_service_and_action(request)
        await _validate_api_key_permissions_impl(api_key, service, action)
        
        # Populate request state with auth context from Bearer token
        request.state.user_id = bearer_result.get("user_id")
        request.state.api_key_id = None  # Not needed when using BOTH
        request.state.api_key_name = None
        request.state.user_email = bearer_result.get("user", {}).get("email")
        request.state.is_authenticated = True
        
        return bearer_result
    
    # Handle API key authentication (requires permission check)
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
    
    # Validate API key has required permissions
    await _validate_api_key_permissions_impl(api_key, service, action)
    
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


async def AuthProvider(
    request: Request,
    authorization: Optional[str] = Header(None, alias="Authorization"),
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    x_auth_source: str = Header(default="API_KEY", alias="X-Auth-Source"),
    db: AsyncSession = Depends(get_db_session)
) -> Dict[str, Any]:
    """Authentication provider dependency for FastAPI routes."""
    if not tracer:
        return await _auth_provider_impl(request, authorization, x_api_key, x_auth_source, db)
    
    # Business-level span: Request authorization
    with tracer.start_as_current_span("Request Authorization") as auth_span:
        auth_span.set_attribute("purpose", "Authorizes the incoming request by validating authentication credentials")
        auth_span.set_attribute("user_visible", False)
        auth_span.set_attribute("impact_if_slow", "Request is delayed - user may experience slower response times")
        auth_span.set_attribute("owner", "Security Team")
        auth_span.set_attribute("auth.operation", "authorize_request")
        auth_source = (x_auth_source or "API_KEY").upper()
        auth_span.set_attribute("auth.source", auth_source)
        auth_span.set_attribute("auth.authorization_present", bool(authorization))
        auth_span.set_attribute("auth.api_key_present", bool(x_api_key))
        
        try:
            # Collapsed: Auth method selection is now just conditional logic
            # No separate span for decision points to reduce noise
            if auth_source == "AUTH_TOKEN":
                auth_span.set_attribute("auth.method", "JWT")
                result = await authenticate_bearer_token(request, authorization)
                auth_span.set_attribute("auth.authorized", True)
                auth_span.set_attribute("auth.user_id", str(result.get("user_id", "")))
                auth_span.set_status(Status(StatusCode.OK))
                return result

            api_key = x_api_key or get_api_key_from_header(authorization)
            auth_span.set_attribute("auth.api_key_extracted", bool(api_key))

            if auth_source == "BOTH":
                auth_span.set_attribute("auth.method", "JWT+API_KEY")
                # Collapsed: Decision logic is now just conditional checks
                bearer_result = await authenticate_bearer_token(request, authorization)
                if not api_key:
                    auth_span.set_attribute("auth.authorized", False)
                    auth_span.set_attribute("error", True)
                    auth_span.set_attribute("error.type", "MissingAPIKey")
                    auth_span.set_attribute("error.reason", "api_key_missing_in_both_mode")
                    auth_span.set_status(Status(StatusCode.ERROR, "Missing API key"))
                    raise AuthenticationError("Missing API key")
                
                service, action = determine_service_and_action(request)
                await validate_api_key_permissions(api_key, service, action)
                auth_span.set_attribute("auth.authorized", True)
                auth_span.set_attribute("auth.user_id", str(bearer_result.get("user_id", "")))
                auth_span.set_status(Status(StatusCode.OK))
                return bearer_result

            # Default: API_KEY
            auth_span.set_attribute("auth.method", "API_KEY")
            
            # Collapsed: Decision logic is now just conditional checks
            if not api_key:
                auth_span.set_attribute("auth.authorized", False)
                auth_span.set_attribute("error.type", "MissingAPIKey")
                auth_span.set_attribute("error.reason", "api_key_missing")
                auth_span.set_status(Status(StatusCode.ERROR, "Missing API key"))
                raise AuthenticationError("Missing API key")

            service, action = determine_service_and_action(request)
            await validate_api_key_permissions(api_key, service, action)
            
            # Get API key and user from database
            api_key_db, user_db = await validate_api_key(api_key, db, request.app.state.redis_client)
            
            # Populate request state
            request.state.user_id = user_db.id
            request.state.api_key_id = api_key_db.id
            request.state.api_key_name = api_key_db.name
            request.state.user_email = user_db.email
            request.state.is_authenticated = True
            
            auth_span.set_attribute("auth.authorized", True)
            auth_span.set_attribute("auth.user_id", str(user_db.id))
            auth_span.set_attribute("auth.api_key_id", str(api_key_db.id))
            auth_span.set_status(Status(StatusCode.OK))
            return {
                "user_id": user_db.id,
                "api_key_id": api_key_db.id,
                "user": user_db,
                "api_key": api_key_db
            }
                
        except AuthenticationError as exc:
            # Mark auth span as failed (error handler will create request.reject span)
            auth_span.set_attribute("auth.authorized", False)
            auth_span.set_attribute("error.type", "AuthenticationError")
            auth_span.set_attribute("error.reason", "authentication_failed")
            auth_span.set_status(Status(StatusCode.ERROR, str(exc)))
            raise
        except AuthorizationError as exc:
            # Mark auth span as failed (error handler will create request.reject span)
            auth_span.set_attribute("auth.authorized", False)
            auth_span.set_attribute("error.type", "AuthorizationError")
            auth_span.set_attribute("error.reason", "authorization_failed")
            auth_span.set_status(Status(StatusCode.ERROR, str(exc)))
            raise
        except Exception as e:
            logger.error(f"Authentication error: {e}")
            auth_span.set_attribute("auth.authorized", False)
            auth_span.set_attribute("error.type", "Exception")
            auth_span.set_attribute("error.reason", "unexpected_error")
            auth_span.set_status(Status(StatusCode.ERROR, str(e)))
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
