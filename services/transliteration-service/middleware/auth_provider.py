"""
Authentication provider for FastAPI routes with API key validation and Redis caching.
"""
from fastapi import Request, Header, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, Dict, Any, Tuple
import hashlib
import json
import logging

from repositories.api_key_repository import APIKeyRepository
from repositories.user_repository import UserRepository
from repositories.transliteration_repository import get_db_session
from models.auth_models import APIKey, User
from middleware.exceptions import (
    AuthenticationError,
    InvalidAPIKeyError,
    ExpiredAPIKeyError,
    AuthorizationError,
)
import httpx
import os
from jose import JWTError, jwt

logger = logging.getLogger(__name__)

AUTH_SERVICE_URL = os.getenv("AUTH_SERVICE_URL", "http://auth-service:8081")
AUTH_HTTP_TIMEOUT = float(os.getenv("AUTH_HTTP_TIMEOUT", "5.0"))

# JWT Configuration for local verification (same as nmt-service)
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "dhruva-jwt-secret-key-2024-super-secure")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")


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
    path = request.url.path.lower()
    method = request.method.upper()
    service = "transliteration"
    if "/inference" in path and method == "POST":
        action = "inference"
    elif method == "GET":
        action = "read"
    else:
        action = "read"
    return service, action


async def authenticate_bearer_token(request: Request, authorization: Optional[str]) -> Dict[str, Any]:
    """
    Validate JWT access token locally (signature + expiry check).
    Same pattern as nmt-service - sets request.state.jwt_payload for tenant resolution.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise AuthenticationError("Missing bearer token")

    token = authorization.split(" ", 1)[1]

    try:
        payload = jwt.decode(
            token,
            JWT_SECRET_KEY,
            algorithms=[JWT_ALGORITHM],
            options={"verify_signature": True, "verify_exp": True}
        )
        
        user_id = payload.get("sub") or payload.get("user_id")
        email = payload.get("email", "")
        username = payload.get("username") or payload.get("email", "")
        roles = payload.get("roles", [])
        token_type = payload.get("type", "")
        
        if token_type != "access":
            raise AuthenticationError("Invalid token type")
        
        if not user_id:
            raise AuthenticationError("User ID not found in token")

        # Populate request state (same as nmt-service)
        request.state.user_id = int(user_id) if isinstance(user_id, (str, int)) else user_id
        request.state.api_key_id = None
        request.state.api_key_name = None
        request.state.user_email = email
        request.state.is_authenticated = True
        request.state.jwt_payload = payload  # For tenant resolution in tenant_context

        return {
            "user_id": int(user_id) if isinstance(user_id, (str, int)) else user_id,
            "api_key_id": None,
            "user": {"username": username, "email": email, "roles": roles},
            "api_key": None,
        }
        
    except JWTError as e:
        logger.warning(f"JWT verification failed: {e}")
        raise AuthenticationError("Invalid or expired token")
    except Exception as e:
        logger.error(f"Unexpected error during JWT verification: {e}")
        raise AuthenticationError("Failed to verify token")


async def validate_api_key_permissions(
    api_key: str,
    service: str,
    action: str,
    user_id: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Validate API key has required permissions by calling auth-service.
    If user_id is provided, auth-service will enforce that the API key belongs to that user
    (same ownership semantics as nmt-service).
    Returns the auth-service response dict on success.
    """
    # Explicitly handle missing API key BEFORE talking to auth-service so the
    # client sees a clear "missing API key" error instead of "invalid API key".
    if not api_key:
        raise AuthorizationError("API key is missing")

    try:
        validate_url = f"{AUTH_SERVICE_URL}/api/v1/auth/validate-api-key"
        payload: Dict[str, Any] = {
            "api_key": api_key,
            "service": service,
            "action": action,
        }
        if user_id is not None:
            payload["user_id"] = user_id

        async with httpx.AsyncClient(timeout=AUTH_HTTP_TIMEOUT) as client:
            response = await client.post(validate_url, json=payload)

        if response.status_code == 200:
            result = response.json()
            if result.get("valid"):
                return result

            # API key invalid - extract detailed reason from auth-service
            error_msg = result.get("message", "Permission denied")
            error_code = result.get("code", "PERMISSION_DENIED")
            error_reason = result.get("reason", "unknown")
            logger.error(
                "Auth-service rejected API key: reason=%s code=%s message=%s",
                error_reason,
                error_code,
                error_msg,
            )
            raise AuthorizationError(error_msg)

        # Handle non-200 responses - extract error from detail or message field
        try:
            error_data = response.json()
            # FastAPI HTTPException uses "detail" field, auth-service uses "message"
            err_msg = error_data.get("detail") or error_data.get("message") or response.text
        except Exception:
            err_msg = response.text
        logger.error(f"Auth service returned status {response.status_code}: {err_msg}")
        raise AuthorizationError(err_msg or "Failed to validate API key permissions")
    except httpx.TimeoutException:
        logger.error("Timeout calling auth-service for permission validation")
        raise AuthorizationError("Permission validation service unavailable")
    except httpx.RequestError as e:
        logger.error(f"Error calling auth-service: {e}")
        raise AuthorizationError("Failed to validate API key permissions")
    except AuthorizationError:
        # Re-raise explicit authorization failures without wrapping
        raise
    except Exception as e:
        logger.error(f"Unexpected error validating permissions: {e}")
        raise AuthorizationError("Permission validation failed")


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
    db: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """Authentication provider dependency for FastAPI routes with permission checks."""
    try:
        auth_source = (x_auth_source or "API_KEY").upper()

        # AUTH_TOKEN flow: For this service, API key is required – do not allow JWT-only.
        if auth_source == "AUTH_TOKEN":
            # Mirror behavior of other services (e.g. audio-lang) where an API key
            # is mandatory and AUTH_TOKEN-only access is rejected explicitly.
            raise AuthenticationError("Missing API key")

        # Resolve API key
        api_key = x_api_key or get_api_key_from_header(authorization)
        
        # BOTH flow: JWT + API key (decodes JWT and sets request.state.jwt_payload)
        if auth_source == "BOTH":
            try:
                # 1) Authenticate via JWT
                bearer_result = await authenticate_bearer_token(request, authorization)
                jwt_user_id = bearer_result.get("user_id")

                if not api_key:
                    raise AuthenticationError("Missing API key")

                # 2) Validate API key + permissions via auth-service (single source of truth),
                # passing jwt_user_id so auth-service can enforce ownership.
                service, action = determine_service_and_action(request)
                auth_result = await validate_api_key_permissions(api_key, service, action, user_id=jwt_user_id)
                
                # CRITICAL: Always check valid field - auth-service may return valid=false for ownership mismatch
                if not auth_result.get("valid", False):
                    error_msg = auth_result.get("message", "API key does not belong to the authenticated user")
                    raise AuthenticationError("API key does not belong to the authenticated user")

                # 3) Populate request.state – keep JWT as primary identity (matching ASR/TTS/NMT)
                request.state.user_id = jwt_user_id
                request.state.api_key_id = None
                request.state.api_key_name = None
                request.state.user_email = bearer_result.get("user", {}).get("email")
                request.state.is_authenticated = True

                return bearer_result
            except (AuthenticationError, AuthorizationError, InvalidAPIKeyError, ExpiredAPIKeyError) as e:
                # For ANY auth/key error in BOTH mode, surface a single, consistent message
                logger.error(f"Transliteration BOTH mode: Authentication/Authorization error: {e}")
                raise AuthenticationError("API key does not belong to the authenticated user")
            except Exception as e:
                logger.error(f"Transliteration BOTH mode: Unexpected error: {e}", exc_info=True)
                # Even on unexpected errors we normalize the external message
                raise AuthenticationError("API key does not belong to the authenticated user")

        # API_KEY flow: API key only
        if not api_key:
            raise AuthenticationError("Missing API key")
        
        # Determine service and action from request
        service, action = determine_service_and_action(request)
        
        # Validate API key and permissions via auth-service (skip local DB validation)
        await validate_api_key_permissions(api_key, service, action)

        # Populate request state (minimal info since we're not querying DB)
        request.state.user_id = None  # Not available without DB lookup
        request.state.api_key_id = None
        request.state.api_key_name = None
        request.state.user_email = None
        request.state.is_authenticated = True

        return {
            "user_id": None,
            "api_key_id": None,
            "user": None,
            "api_key": None,
        }

    except (AuthenticationError, InvalidAPIKeyError, ExpiredAPIKeyError, AuthorizationError) as e:
        # In BOTH mode, only convert explicit ownership mismatches to the stable
        # "API key does not belong to the authenticated user" message.
        # For all other auth/permission errors, preserve the real message so callers
        # can distinguish "no permission for service/action" vs "wrong user's key".
        if auth_source == "BOTH":
            msg = getattr(e, "message", str(e))
            if msg == "API key does not belong to the authenticated user":
                raise AuthenticationError(msg)
            # Otherwise, let the original exception bubble up
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
