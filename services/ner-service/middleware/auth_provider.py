"""
Authentication provider for FastAPI routes - supports JWT, API key, and BOTH.
Performs local JWT verification and calls auth-service for API key permission checks.
"""
import os
import logging
import hashlib
from typing import Optional, Dict, Any, Tuple
from contextlib import nullcontext

import httpx
from fastapi import Request, Header, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from jose import JWTError, jwt

from middleware.exceptions import AuthenticationError, AuthorizationError
from repositories.api_key_repository import ApiKeyRepository
from repositories.ner_repository import get_db_session

# OpenTelemetry tracing
try:
    from opentelemetry import trace
    from opentelemetry.trace import Status, StatusCode
    TRACING_AVAILABLE = True
except ImportError:
    TRACING_AVAILABLE = False
    trace = None
    Status = None
    StatusCode = None

logger = logging.getLogger(__name__)

# Get tracer for creating spans
def get_tracer():
    """Get tracer instance dynamically at runtime."""
    if not TRACING_AVAILABLE or not trace:
        return None
    try:
        return trace.get_tracer("ner-service")
    except Exception:
        return None

# JWT Configuration for local verification
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "dhruva-jwt-secret-key-2024-super-secure")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")

AUTH_SERVICE_URL = os.getenv("AUTH_SERVICE_URL", "http://auth-service:8081")
AUTH_HTTP_TIMEOUT = float(os.getenv("AUTH_HTTP_TIMEOUT", "5.0"))


def get_api_key_from_header(authorization: Optional[str]) -> Optional[str]:
    if not authorization:
        return None
    if authorization.startswith("Bearer "):
        return authorization[7:]
    if authorization.startswith("ApiKey "):
        return authorization[7:]
    return authorization


def hash_api_key(api_key: str) -> str:
    """Hash API key using SHA256."""
    return hashlib.sha256(api_key.encode()).hexdigest()


async def get_api_key_info(api_key: str, db: AsyncSession) -> Tuple[Optional[int], Optional[int]]:
    """
    Look up API key in database and return (api_key_id, user_id).
    Returns (None, None) if not found or invalid.
    """
    try:
        key_hash = hash_api_key(api_key)
        api_key_repo = ApiKeyRepository(db)
        api_key_db = await api_key_repo.find_by_key_hash(key_hash)
        
        if not api_key_db:
            return None, None
        
        # Validate the key is active and not expired
        if not await api_key_repo.is_key_valid(api_key_db):
            return None, None
        
        # Update last used
        await api_key_repo.update_last_used(api_key_db.id)
        
        return api_key_db.id, api_key_db.user_id
    except Exception as e:
        logger.debug(f"Error looking up API key: {e}")
        return None, None


def determine_service_and_action(request: Request) -> Tuple[str, str]:
    path = request.url.path.lower()
    method = request.method.upper()
    service = "ner"
    if "/inference" in path and method == "POST":
        action = "inference"
    elif method == "GET":
        action = "read"
    else:
        action = "read"
    return service, action


async def authenticate_bearer_token(request: Request, authorization: Optional[str]) -> Dict[str, Any]:
    """Validate JWT access token locally (signature + expiry check)."""
    tracer = get_tracer()
    
    if not authorization or not authorization.startswith("Bearer "):
        raise AuthenticationError("Missing bearer token")

    token = authorization.split(" ", 1)[1]

    # Tracing-aware implementation
    span_context = tracer.start_as_current_span("auth.verify_jwt") if tracer else nullcontext()
    with span_context as span:
        if span:
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

            if span:
                span.set_attribute("auth.token_type", token_type)

            if token_type != "access":
                if span:
                    span.set_attribute("error", True)
                    span.set_attribute("error.type", "InvalidTokenType")
                    span.set_attribute("error.message", f"Invalid token type: {token_type}")
                    span.set_status(Status(StatusCode.ERROR, "Invalid token type"))
                raise AuthenticationError("Invalid token type")

            if not user_id:
                if span:
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
            request.state.jwt_payload = payload  # Store JWT payload for tenant resolution

            if span:
                span.set_attribute("auth.user_id", str(user_id))
                span.set_attribute("auth.valid", True)
                span.set_status(Status(StatusCode.OK))

            return {
                "user_id": int(user_id) if isinstance(user_id, (str, int)) else user_id,
                "api_key_id": None,
                "user": {"username": username, "email": email, "roles": roles},
                "api_key": None,
            }

        except JWTError as e:
            if span:
                span.set_attribute("error", True)
                span.set_attribute("error.type", "JWTError")
                span.set_attribute("error.message", str(e))
                span.set_status(Status(StatusCode.ERROR, str(e)))
            
            # Provide specific error message for expired tokens
            error_msg = str(e).lower()
            if "expired" in error_msg or "exp" in error_msg:
                logger.warning(f"JWT token expired: {e}")
                raise AuthenticationError("Authentication failed. Please log in again.")
            else:
                logger.warning(f"JWT verification failed: {e}")
                raise AuthenticationError("Invalid or expired token")
        except AuthenticationError:
            raise
        except Exception as e:
            if span:
                span.set_attribute("error", True)
                span.set_attribute("error.type", type(e).__name__)
                span.set_attribute("error.message", str(e))
                span.set_status(Status(StatusCode.ERROR, str(e)))
            logger.error(f"Unexpected error during JWT verification: {e}")
            raise AuthenticationError("Failed to verify token")


async def validate_api_key_permissions(
    api_key: str,
    service: str,
    action: str,
    user_id: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Call auth-service to validate API key permissions.
    If user_id is provided, auth-service will enforce that the API key belongs to that user.
    Returns the auth-service response dict on success.
    """
    tracer = get_tracer()

    # Explicitly handle missing API key BEFORE talking to auth-service
    if not api_key:
        raise AuthorizationError("API key is missing")
    
    span_context = tracer.start_as_current_span("auth.validate_api_key") if tracer else nullcontext()
    with span_context as span:
        if span:
            span.set_attribute("auth.operation", "validate_api_key")
            span.set_attribute("auth.service", service)
            span.set_attribute("auth.action", action)
            span.set_attribute("auth.api_key_present", bool(api_key))
            if user_id is not None:
                span.set_attribute("auth.requested_user_id", str(user_id))
        
        try:
            validate_url = f"{AUTH_SERVICE_URL}/api/v1/auth/validate-api-key"
            if span:
                span.set_attribute("http.url", validate_url)
                span.set_attribute("http.method", "POST")

            payload: Dict[str, Any] = {
                "api_key": api_key,
                "service": service,
                "action": action,
            }
            if user_id is not None:
                payload["user_id"] = user_id
            
            async with httpx.AsyncClient(timeout=AUTH_HTTP_TIMEOUT) as client:
                response = await client.post(validate_url, json=payload)
            
            if span:
                span.set_attribute("http.status_code", response.status_code)
            
            if response.status_code == 200:
                result = response.json()
                if result.get("valid"):
                    if span:
                        span.set_attribute("auth.valid", True)
                        span.set_status(Status(StatusCode.OK))
                    return result

                # API key invalid - extract detailed reason from auth-service
                error_msg = result.get("message", "Permission denied")
                error_code = result.get("code", "PERMISSION_DENIED")
                error_reason = result.get("reason", "unknown")

                if span:
                    span.set_attribute("auth.valid", False)
                    span.set_attribute("error", True)
                    span.set_attribute("error.type", "AuthorizationError")
                    span.set_attribute("error.reason", error_reason)
                    span.set_attribute("error.code", error_code)
                    span.set_attribute("error.message", error_msg)
                    span.set_status(Status(StatusCode.ERROR, error_msg))

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
                err_msg = error_data.get("detail") or error_data.get("message") or response.text
            except Exception:
                err_msg = response.text
            
            if span:
                span.set_attribute("error", True)
                span.set_attribute("error.type", "AuthServiceError")
                span.set_attribute("error.message", err_msg)
                span.set_status(Status(StatusCode.ERROR, "Auth service error"))
            
            logger.error(f"Auth service returned status {response.status_code}: {err_msg}")
            raise AuthorizationError(err_msg or "Failed to validate API key permissions")
        except httpx.TimeoutException:
            if span:
                span.set_attribute("error", True)
                span.set_attribute("error.type", "TimeoutException")
                span.set_status(Status(StatusCode.ERROR, "Timeout"))
            logger.error("Timeout calling auth-service for permission validation")
            raise AuthorizationError("Permission validation service unavailable")
        except httpx.RequestError as e:
            if span:
                span.set_attribute("error", True)
                span.set_attribute("error.type", "RequestError")
                span.set_attribute("error.message", str(e))
                span.set_status(Status(StatusCode.ERROR, str(e)))
            logger.error(f"Error calling auth-service: {e}")
            raise AuthorizationError("Failed to validate API key permissions")
        except AuthorizationError:
            raise
        except Exception as e:
            if span:
                span.set_attribute("error", True)
                span.set_attribute("error.type", type(e).__name__)
                span.set_attribute("error.message", str(e))
                span.set_status(Status(StatusCode.ERROR, str(e)))
            logger.error(f"Unexpected error validating permissions: {e}")
            raise AuthorizationError("Permission validation failed")


async def AuthProvider(
    request: Request,
    authorization: Optional[str] = Header(None, alias="Authorization"),
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    x_auth_source: str = Header(default="API_KEY", alias="X-Auth-Source"),
    db: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """Authentication provider for NER - supports AUTH_TOKEN, API_KEY, BOTH."""
    tracer = get_tracer()
    
    # Environment-driven auth behavior (align with ASR service)
    auth_enabled = os.getenv("AUTH_ENABLED", "true").lower() == "true"
    require_api_key = os.getenv("REQUIRE_API_KEY", "true").lower() == "true"
    allow_anonymous = os.getenv("ALLOW_ANONYMOUS_ACCESS", "false").lower() == "true"

    # Also check request headers directly in case FastAPI header parsing missed it
    # (API gateway might forward it with different casing)
    x_auth_source_from_header = request.headers.get("X-Auth-Source") or request.headers.get("x-auth-source")
    if x_auth_source_from_header and not x_auth_source:
        x_auth_source = x_auth_source_from_header
        logger.debug(f"Found X-Auth-Source header: {x_auth_source}")
    
    # Determine auth source strictly from header (no auto-fallback)
    has_bearer_token = authorization and authorization.startswith("Bearer ")
    has_explicit_api_key = x_api_key is not None
    auth_source = (x_auth_source or "API_KEY").upper()

    logger.debug(f"Auth source determined: {auth_source} (from header: {x_auth_source})")

    # Tracing-aware implementation
    span_context = tracer.start_as_current_span("request.authorize") if tracer else nullcontext()
    with span_context as auth_span:
        if auth_span:
            auth_span.set_attribute("auth.source", auth_source)
            auth_span.set_attribute("auth.enabled", auth_enabled)
            auth_span.set_attribute("auth.require_api_key", require_api_key)
            auth_span.set_attribute("auth.allow_anonymous", allow_anonymous)
            auth_span.set_attribute("auth.authorization_present", bool(authorization))
            auth_span.set_attribute("auth.api_key_present", bool(x_api_key))
        
        try:
            # If authentication is disabled or anonymous access is allowed, skip auth
            if not auth_enabled or (allow_anonymous and not require_api_key):
                if auth_span:
                    auth_span.set_attribute("auth.method", "NONE")
                    auth_span.set_attribute("auth.authorized", False)
                    auth_span.set_attribute("auth.skipped", True)
                    auth_span.set_status(Status(StatusCode.OK) if Status else None)

                # Clear request auth state
                request.state.user_id = None
                request.state.api_key_id = None
                request.state.api_key_name = None
                request.state.user_email = None
                request.state.is_authenticated = False

                return {"user_id": None, "api_key_id": None, "user": None, "api_key": None}

            if auth_source == "AUTH_TOKEN":
                if auth_span:
                    auth_span.set_attribute("auth.method", "JWT")
                result = await authenticate_bearer_token(request, authorization)
                if auth_span:
                    auth_span.set_attribute("auth.authorized", True)
                    auth_span.set_status(Status(StatusCode.OK))
                return result

            api_key = x_api_key or get_api_key_from_header(authorization)

            if auth_source == "BOTH":
                if auth_span:
                    auth_span.set_attribute("auth.method", "JWT+API_KEY")
                
                # 1) Authenticate via JWT
                bearer_result = await authenticate_bearer_token(request, authorization)
                jwt_user_id = bearer_result.get("user_id")
                
                # 2) Extract API key
                if not api_key:
                    if auth_span:
                        auth_span.set_attribute("error", True)
                        auth_span.set_attribute("error.type", "MissingAPIKey")
                        auth_span.set_status(Status(StatusCode.ERROR, "Missing API key"))
                    raise AuthenticationError("Missing API key")
                
                # 3) Validate API key + permissions via auth-service (single source of truth),
                #    passing jwt_user_id so auth-service can enforce ownership.
                service, action = determine_service_and_action(request)
                auth_result = await validate_api_key_permissions(api_key, service, action, user_id=jwt_user_id)

                # CRITICAL: Check valid field - auth-service may return valid=false for ownership mismatch
                if not auth_result.get("valid", False):
                    error_msg = auth_result.get("message", "API key validation failed")
                    # Only convert to ownership error if auth-service explicitly says so
                    if "does not belong" in error_msg.lower() or "ownership" in error_msg.lower():
                        raise AuthenticationError("API key does not belong to the authenticated user")
                    # Otherwise, preserve the actual error (permission denied, expired, etc.)
                    raise AuthorizationError(error_msg)
                
                # 4) Populate request state with JWT identity
                request.state.user_id = jwt_user_id
                request.state.api_key_id = None
                request.state.api_key_name = None
                request.state.user_email = bearer_result.get("user", {}).get("email")
                request.state.is_authenticated = True
                
                if auth_span:
                    auth_span.set_attribute("auth.authorized", True)
                    auth_span.set_status(Status(StatusCode.OK))
                
                return bearer_result

            # Default: API_KEY
            if auth_span:
                auth_span.set_attribute("auth.method", "API_KEY")
            
            # In API_KEY mode, if Bearer token is provided along with explicit API key, reject it
            # This prevents expired JWT tokens from being used as API keys
            # Only check this in API_KEY mode (not BOTH mode, which already handled above)
            if auth_source == "API_KEY" and has_bearer_token and has_explicit_api_key:
                if auth_span:
                    auth_span.set_attribute("error", True)
                    auth_span.set_attribute("error.type", "InvalidAuthMethod")
                    auth_span.set_status(Status(StatusCode.ERROR, "Bearer token not allowed with explicit API key in API_KEY mode"))
                raise AuthenticationError(
                    "Bearer token detected with explicit API key in API_KEY mode. "
                    "Use X-Auth-Source: AUTH_TOKEN for JWT tokens only, or X-Auth-Source: BOTH for JWT + API key."
                )
            
            if not api_key:
                if auth_span:
                    auth_span.set_attribute("error", True)
                    auth_span.set_attribute("error.type", "MissingAPIKey")
                    auth_span.set_status(Status(StatusCode.ERROR, "Missing API key"))
                raise AuthenticationError("Missing API key")

            service, action = determine_service_and_action(request)
            await validate_api_key_permissions(api_key, service, action)
            
            # Look up API key in database to get actual IDs
            api_key_id, user_id = await get_api_key_info(api_key, db)
            
            # Get API key name if we found it
            api_key_name = None
            user_email = None
            if api_key_id:
                try:
                    api_key_repo = ApiKeyRepository(db)
                    api_key_db = await api_key_repo.find_by_id(api_key_id)
                    if api_key_db:
                        api_key_name = api_key_db.name
                        if api_key_db.user:
                            user_email = api_key_db.user.email
                except Exception as e:
                    logger.debug(f"Error getting API key details: {e}")
            
            request.state.user_id = user_id
            request.state.api_key_id = api_key_id
            request.state.api_key_name = api_key_name
            request.state.user_email = user_email
            request.state.is_authenticated = True

            if auth_span:
                auth_span.set_attribute("auth.authorized", True)
                auth_span.set_status(Status(StatusCode.OK))

            return {
                "user_id": user_id,
                "api_key_id": api_key_id,
                "user": {"email": user_email} if user_email else None,
                "api_key": {"id": api_key_id, "name": api_key_name} if api_key_id else None,
            }
        except (AuthenticationError, AuthorizationError) as e:
            if auth_span:
                auth_span.set_attribute("auth.authorized", False)
                auth_span.set_attribute("error", True)
                auth_span.set_attribute("error.type", type(e).__name__)
                auth_span.set_attribute("error.message", str(e))
                auth_span.set_status(Status(StatusCode.ERROR, str(e)))
            raise
        except Exception as e:
            if auth_span:
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
) -> Optional[Dict[str, Any]]:
    """Optional authentication provider that doesn't raise exception if no auth provided."""
    try:
        return await AuthProvider(request, authorization, x_api_key, x_auth_source)
    except AuthenticationError:
        return None
