"""
Authentication provider for FastAPI routes with API key validation and Redis caching.

This module now also emits OpenTelemetry spans for authentication and permission checks
so that auth flows are visible in Jaeger (similar to OCR/NMT services).
"""
from fastapi import Request, Header, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, Dict, Any, Tuple
import hashlib
import json
import httpx
import os

from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode

from repositories.api_key_repository import ApiKeyRepository
from repositories.user_repository import UserRepository
from repositories.tts_repository import get_db_session
from models.auth_models import ApiKeyDB, UserDB
from middleware.exceptions import AuthenticationError, InvalidAPIKeyError, ExpiredAPIKeyError, AuthorizationError
from ai4icore_logging import get_logger

logger = get_logger(__name__)
tracer = trace.get_tracer("tts-service")

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
    
    # Extract service name from path (e.g., /api/v1/tts/... -> tts)
    service = None
    for svc in ["asr", "nmt", "tts", "pipeline", "model-management", "llm"]:
        if f"/api/v1/{svc}/" in path or path.endswith(f"/api/v1/{svc}"):
            service = svc
            break
    
    if not service:
        # Default to tts for this service
        service = "tts"
    
    # Determine action based on path and method
    if "/inference" in path and method == "POST":
        action = "inference"
    elif method == "GET" or "/services" in path or "/models" in path or "/languages" in path or "/voices" in path:
        action = "read"
    else:
        # Default to read for other operations
        action = "read"
    
    return service, action


async def authenticate_bearer_token(request: Request, authorization: Optional[str]) -> Dict[str, Any]:
    """
    Validate JWT access token locally (signature + expiry check).
    Kong already validated the token, this is a defense-in-depth check.
    Emits OpenTelemetry spans so JWT verification is visible in Jaeger.
    """
    from jose import JWTError, jwt

    if not authorization or not authorization.startswith("Bearer "):
        if tracer:
            with tracer.start_as_current_span("auth.verify_jwt") as span:
                span.set_attribute("auth.operation", "verify_jwt")
                span.set_attribute("auth.token_present", False)
                span.set_status(Status(StatusCode.ERROR, "Missing bearer token"))
        raise AuthenticationError("Missing bearer token")

    token = authorization.split(" ", 1)[1]

    # JWT Configuration for local verification
    JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "dhruva-jwt-secret-key-2024-super-secure")
    JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")

    if not tracer:
        # Original behavior without spans
        try:
            payload = jwt.decode(
                token,
                JWT_SECRET_KEY,
                algorithms=[JWT_ALGORITHM],
                options={"verify_signature": True, "verify_exp": True},
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

    # Tracing-aware implementation
    with tracer.start_as_current_span("auth.verify_jwt") as span:
        span.set_attribute("auth.operation", "verify_jwt")
        span.set_attribute("auth.token_present", True)
        span.set_attribute("auth.token_length", len(token))
        try:
            payload = jwt.decode(
                token,
                JWT_SECRET_KEY,
                algorithms=[JWT_ALGORITHM],
                options={"verify_signature": True, "verify_exp": True},
            )

            user_id = payload.get("sub") or payload.get("user_id")
            email = payload.get("email", "")
            username = payload.get("username") or payload.get("email", "")
            roles = payload.get("roles", [])
            token_type = payload.get("type", "")

            span.set_attribute("auth.token_type", token_type)

            if token_type != "access":
                span.set_attribute("error", True)
                span.set_attribute("error.type", "InvalidTokenType")
                span.set_attribute("error.message", f"Invalid token type: {token_type}")
                span.set_status(Status(StatusCode.ERROR, "Invalid token type"))
                raise AuthenticationError("Invalid token type")

            if not user_id:
                span.set_attribute("error", True)
                span.set_attribute("error.type", "MissingUserID")
                span.set_attribute("error.message", "User ID not found in token")
                span.set_status(Status(StatusCode.ERROR, "User ID not found in token"))
                raise AuthenticationError("User ID not found in token")

            request.state.user_id = int(user_id) if isinstance(user_id, (str, int)) else user_id
            request.state.api_key_id = None
            request.state.api_key_name = None
            request.state.user_email = email
            request.state.is_authenticated = True

            span.set_attribute("auth.user_id", str(user_id))
            span.set_attribute("auth.valid", True)
            span.set_status(Status(StatusCode.OK))

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
            error_reason = "token_expired" if "expired" in str(e).lower() else "token_invalid"
            span.set_attribute("error", True)
            span.set_attribute("error.type", "JWTError")
            span.set_attribute("error.reason", error_reason)
            span.set_attribute("error.message", str(e))
            span.set_status(Status(StatusCode.ERROR, str(e)))
            span.record_exception(e)
            logger.warning(f"JWT verification failed: {e}")
            raise AuthenticationError("Invalid or expired token")
        except Exception as e:
            span.set_attribute("error", True)
            span.set_attribute("error.type", type(e).__name__)
            span.set_attribute("error.message", str(e))
            span.set_status(Status(StatusCode.ERROR, str(e)))
            span.record_exception(e)
            logger.error(f"Unexpected error during JWT verification: {e}")
            raise AuthenticationError("Failed to verify token")


async def validate_api_key_permissions(api_key: str, service: str, action: str) -> bool:
    """
    Validate API key has required permissions by calling auth-service.
    Emits OpenTelemetry spans so permission checks are visible in Jaeger.
    """
    if not tracer:
        # Original behavior without spans
        try:
            validate_url = f"{AUTH_SERVICE_URL}/api/v1/auth/validate-api-key"
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.post(
                    validate_url,
                    json={
                        "api_key": api_key,
                        "service": service,
                        "action": action,
                    },
                )
            if response.status_code == 200:
                result = response.json()
                if result.get("valid"):
                    return True
                error_msg = result.get("message", "Permission denied")
                raise AuthorizationError(error_msg)
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

    with tracer.start_as_current_span("auth.validate_api_key") as span:
        span.set_attribute("auth.operation", "validate_api_key")
        span.set_attribute("auth.service", service)
        span.set_attribute("auth.action", action)
        span.set_attribute("auth.api_key_present", bool(api_key))
        try:
            validate_url = f"{AUTH_SERVICE_URL}/api/v1/auth/validate-api-key"
            span.set_attribute("http.url", validate_url)
            span.set_attribute("http.method", "POST")

            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.post(
                    validate_url,
                    json={
                        "api_key": api_key,
                        "service": service,
                        "action": action,
                    },
                )

            span.set_attribute("http.status_code", response.status_code)

            if response.status_code == 200:
                result = response.json()
                if result.get("valid"):
                    span.set_attribute("auth.valid", True)
                    span.set_status(Status(StatusCode.OK))
                    return True
                error_msg = result.get("message", "Permission denied")
                span.set_attribute("auth.valid", False)
                span.set_attribute("error", True)
                span.set_attribute("error.type", "AuthorizationError")
                span.set_attribute("error.message", error_msg)
                span.set_status(Status(StatusCode.ERROR, error_msg))
                raise AuthorizationError(error_msg)

            span.set_attribute("error", True)
            span.set_attribute("error.type", "AuthServiceError")
            span.set_attribute("error.message", response.text)
            span.set_status(Status(StatusCode.ERROR, "Auth service error"))
            logger.error(f"Auth service returned status {response.status_code}: {response.text}")
            raise AuthorizationError("Failed to validate API key permissions")

        except httpx.TimeoutException as e:
            span.set_attribute("error", True)
            span.set_attribute("error.type", "TimeoutException")
            span.set_attribute("error.message", "Auth service timeout")
            span.set_status(Status(StatusCode.ERROR, "Auth service timeout"))
            span.record_exception(e)
            logger.error("Timeout calling auth-service for permission validation")
            raise AuthorizationError("Permission validation service unavailable")
        except httpx.RequestError as e:
            span.set_attribute("error", True)
            span.set_attribute("error.type", "RequestError")
            span.set_attribute("error.message", str(e))
            span.set_status(Status(StatusCode.ERROR, str(e)))
            span.record_exception(e)
            logger.error(f"Error calling auth-service: {e}")
            raise AuthorizationError("Failed to validate API key permissions")
        except AuthorizationError:
            raise
        except Exception as e:
            span.set_attribute("error", True)
            span.set_attribute("error.type", type(e).__name__)
            span.set_attribute("error.message", str(e))
            span.set_status(Status(StatusCode.ERROR, str(e)))
            span.record_exception(e)
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


async def AuthProvider(
    request: Request,
    authorization: Optional[str] = Header(None, alias="Authorization"),
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    x_auth_source: str = Header(default="API_KEY", alias="X-Auth-Source"),
    db: AsyncSession = Depends(get_db_session)
) -> Dict[str, Any]:
    """Authentication provider dependency for FastAPI routes.

    Emits a high-level OpenTelemetry span (`request.authorize`) so that authentication
    decisions are visible in Jaeger, similar to OCR/NMT.
    """
    auth_source = (x_auth_source or "API_KEY").upper()

    if not tracer:
        # Original behavior without spans
        if auth_source == "AUTH_TOKEN":
            return await authenticate_bearer_token(request, authorization)

        if auth_source == "BOTH":
            try:
                bearer_result = await authenticate_bearer_token(request, authorization)
                api_key = x_api_key or get_api_key_from_header(authorization)
                if not api_key:
                    raise AuthenticationError("Missing API key")
                service, action = determine_service_and_action(request)
                logger.debug(f"Validating API key permissions for service={service}, action={action}")
                await validate_api_key_permissions(api_key, service, action)
                request.state.user_id = bearer_result.get("user_id")
                request.state.api_key_id = None
                request.state.api_key_name = None
                request.state.user_email = bearer_result.get("user", {}).get("email")
                request.state.is_authenticated = True
                return bearer_result
            except (AuthenticationError, AuthorizationError) as e:
                logger.error(f"Authentication/Authorization error in BOTH mode: {e}")
                raise
            except Exception as e:
                logger.error(f"Unexpected error in BOTH authentication mode: {e}", exc_info=True)
                raise AuthenticationError(f"Authentication failed: {str(e)}")

        try:
            api_key = x_api_key or get_api_key_from_header(authorization)
            if not api_key:
                raise AuthenticationError("Missing API key")
            redis_client = request.app.state.redis_client
            api_key_db, user_db = await validate_api_key(api_key, db, redis_client)
            service, action = determine_service_and_action(request)
            await validate_api_key_permissions(api_key, service, action)
            request.state.user_id = user_db.id
            request.state.api_key_id = api_key_db.id
            request.state.api_key_name = api_key_db.name
            request.state.user_email = user_db.email
            request.state.is_authenticated = True
            return {
                "user_id": user_db.id,
                "api_key_id": api_key_db.id,
                "user": user_db,
                "api_key": api_key_db,
            }
        except (AuthenticationError, InvalidAPIKeyError, ExpiredAPIKeyError, AuthorizationError):
            raise
        except Exception as e:
            logger.error(f"Authentication error: {e}")
            raise AuthenticationError("Authentication failed")

    # Tracing-aware implementation
    with tracer.start_as_current_span("request.authorize") as auth_span:
        auth_span.set_attribute("auth.source", auth_source)
        try:
            if auth_source == "AUTH_TOKEN":
                result = await authenticate_bearer_token(request, authorization)
                auth_span.set_attribute("auth.method", "JWT")
                auth_span.set_attribute("auth.authorized", True)
                auth_span.set_status(Status(StatusCode.OK))
                return result

            if auth_source == "BOTH":
                auth_span.set_attribute("auth.method", "JWT+API_KEY")
                bearer_result = await authenticate_bearer_token(request, authorization)
                api_key = x_api_key or get_api_key_from_header(authorization)
                if not api_key:
                    auth_span.set_attribute("error", True)
                    auth_span.set_attribute("error.type", "MissingAPIKey")
                    auth_span.set_status(Status(StatusCode.ERROR, "Missing API key"))
                    raise AuthenticationError("Missing API key")
                service, action = determine_service_and_action(request)
                logger.debug(f"Validating API key permissions for service={service}, action={action}")
                await validate_api_key_permissions(api_key, service, action)
                request.state.user_id = bearer_result.get("user_id")
                request.state.api_key_id = None
                request.state.api_key_name = None
                request.state.user_email = bearer_result.get("user", {}).get("email")
                request.state.is_authenticated = True
                auth_span.set_attribute("auth.authorized", True)
                auth_span.set_status(Status(StatusCode.OK))
                return bearer_result

            auth_span.set_attribute("auth.method", "API_KEY")
            api_key = x_api_key or get_api_key_from_header(authorization)
            if not api_key:
                auth_span.set_attribute("error", True)
                auth_span.set_attribute("error.type", "MissingAPIKey")
                auth_span.set_status(Status(StatusCode.ERROR, "Missing API key"))
                raise AuthenticationError("Missing API key")

            redis_client = request.app.state.redis_client
            api_key_db, user_db = await validate_api_key(api_key, db, redis_client)
            service, action = determine_service_and_action(request)
            await validate_api_key_permissions(api_key, service, action)
            request.state.user_id = user_db.id
            request.state.api_key_id = api_key_db.id
            request.state.api_key_name = api_key_db.name
            request.state.user_email = user_db.email
            request.state.is_authenticated = True

            auth_span.set_attribute("auth.authorized", True)
            auth_span.set_status(Status(StatusCode.OK))
            return {
                "user_id": user_db.id,
                "api_key_id": api_key_db.id,
                "user": user_db,
                "api_key": api_key_db,
            }
        except (AuthenticationError, InvalidAPIKeyError, ExpiredAPIKeyError, AuthorizationError) as e:
            auth_span.set_attribute("auth.authorized", False)
            auth_span.set_attribute("error", True)
            auth_span.set_attribute("error.type", type(e).__name__)
            auth_span.set_attribute("error.message", str(e))
            auth_span.set_status(Status(StatusCode.ERROR, str(e)))
            raise
        except Exception as e:
            auth_span.set_attribute("auth.authorized", False)
            auth_span.set_attribute("error", True)
            auth_span.set_attribute("error.type", type(e).__name__)
            auth_span.set_attribute("error.message", str(e))
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
