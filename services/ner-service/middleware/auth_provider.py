"""
Authentication provider for FastAPI routes - supports JWT, API key, and BOTH.
Performs local JWT verification and calls auth-service for API key permission checks.
"""
import os
import logging
from typing import Optional, Dict, Any, Tuple
from contextlib import nullcontext

import httpx
from fastapi import Request, Header
from jose import JWTError, jwt

from middleware.exceptions import AuthenticationError, AuthorizationError

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
                raise AuthenticationError("Token has expired. Please refresh your authentication token.")
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


async def validate_api_key_permissions(api_key: str, service: str, action: str) -> None:
    """Call auth-service to validate API key permissions."""
    tracer = get_tracer()
    
    span_context = tracer.start_as_current_span("auth.validate_api_key") if tracer else nullcontext()
    with span_context as span:
        if span:
            span.set_attribute("auth.operation", "validate_api_key")
            span.set_attribute("auth.service", service)
            span.set_attribute("auth.action", action)
            span.set_attribute("auth.api_key_present", bool(api_key))
        
        try:
            validate_url = f"{AUTH_SERVICE_URL}/api/v1/auth/validate-api-key"
            if span:
                span.set_attribute("http.url", validate_url)
                span.set_attribute("http.method", "POST")
            
            async with httpx.AsyncClient(timeout=AUTH_HTTP_TIMEOUT) as client:
                response = await client.post(
                    validate_url, json={"api_key": api_key, "service": service, "action": action}
                )
            
            if span:
                span.set_attribute("http.status_code", response.status_code)
            
            if response.status_code == 200:
                result = response.json()
                if result.get("valid"):
                    if span:
                        span.set_attribute("auth.valid", True)
                        span.set_status(Status(StatusCode.OK))
                    return
                error_msg = result.get("message", "Permission denied")
                if span:
                    span.set_attribute("auth.valid", False)
                    span.set_attribute("error", True)
                    span.set_attribute("error.type", "AuthorizationError")
                    span.set_attribute("error.message", error_msg)
                    span.set_status(Status(StatusCode.ERROR, error_msg))
                raise AuthorizationError(error_msg)

            try:
                err_msg = response.json().get("message", response.text)
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
) -> Dict[str, Any]:
    """Authentication provider for NER - supports AUTH_TOKEN, API_KEY, BOTH."""
    tracer = get_tracer()
    
    # Also check request headers directly in case FastAPI header parsing missed it
    # (API gateway might forward it with different casing)
    x_auth_source_from_header = request.headers.get("X-Auth-Source") or request.headers.get("x-auth-source")
    if x_auth_source_from_header and not x_auth_source:
        x_auth_source = x_auth_source_from_header
        logger.debug(f"Found X-Auth-Source header: {x_auth_source}")
    
    # Auto-detect auth mode: If Bearer token is provided and no explicit API key,
    # automatically use AUTH_TOKEN mode (unless explicitly set to API_KEY with X-API-Key)
    has_bearer_token = authorization and authorization.startswith("Bearer ")
    has_explicit_api_key = x_api_key is not None
    
    auth_source = (x_auth_source or "API_KEY").upper()
    
    # Smart fallback: If both Bearer token and API key are present but auth_source is API_KEY,
    # automatically use BOTH mode (API gateway might not forward x-auth-source header)
    if auth_source == "API_KEY" and has_bearer_token and has_explicit_api_key:
        auth_source = "BOTH"
        logger.debug(f"Auto-detected BOTH mode: Bearer token + API key present")
    
    logger.debug(f"Auth source determined: {auth_source} (from header: {x_auth_source})")
    
    # If Bearer token is provided but auth_source is API_KEY (default) and no explicit API key,
    # automatically switch to AUTH_TOKEN mode for better UX
    auto_detected = False
    if has_bearer_token and auth_source == "API_KEY" and not has_explicit_api_key:
        auth_source = "AUTH_TOKEN"
        auto_detected = True

    # Tracing-aware implementation
    span_context = tracer.start_as_current_span("request.authorize") if tracer else nullcontext()
    with span_context as auth_span:
        if auth_span:
            auth_span.set_attribute("auth.source", auth_source)
            if auto_detected:
                auth_span.set_attribute("auth.source_auto_detected", True)
        
        try:
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
                bearer_result = await authenticate_bearer_token(request, authorization)
                if not api_key:
                    if auth_span:
                        auth_span.set_attribute("error", True)
                        auth_span.set_attribute("error.type", "MissingAPIKey")
                        auth_span.set_status(Status(StatusCode.ERROR, "Missing API key"))
                    raise AuthenticationError("Missing API key")
                service, action = determine_service_and_action(request)
                await validate_api_key_permissions(api_key, service, action)
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
            
            request.state.user_id = None
            request.state.api_key_id = None
            request.state.api_key_name = None
            request.state.user_email = None
            request.state.is_authenticated = True

            if auth_span:
                auth_span.set_attribute("auth.authorized", True)
                auth_span.set_status(Status(StatusCode.OK))

            return {"user_id": None, "api_key_id": None, "user": None, "api_key": {"masked": True}}
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
