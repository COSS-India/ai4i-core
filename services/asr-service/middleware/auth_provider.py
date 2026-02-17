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
import logging
import httpx
import os

from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode

from repositories.api_key_repository import ApiKeyRepository
from repositories.user_repository import UserRepository
from repositories.asr_repository import get_db_session
from models.auth_models import ApiKeyDB, UserDB
from middleware.exceptions import AuthenticationError, InvalidAPIKeyError, ExpiredAPIKeyError, AuthorizationError

logger = logging.getLogger(__name__)
tracer = trace.get_tracer("asr-service")

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
    
    # Extract service name from path (e.g., /api/v1/asr/... -> asr)
    service = None
    for svc in ["asr", "nmt", "tts", "pipeline", "model-management", "llm"]:
        if f"/api/v1/{svc}/" in path or path.endswith(f"/api/v1/{svc}"):
            service = svc
            break
    
    if not service:
        # Default to asr for this service
        service = "asr"
    
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
    Emits OpenTelemetry spans so JWT verification is visible in Jaeger.
    """
    import os
    from jose import JWTError, jwt

    if not authorization or not authorization.startswith("Bearer "):
        # Decision point: Check if token is present
        with tracer.start_as_current_span("auth.decision.check_token_presence") as decision_span:
            decision_span.set_attribute("auth.decision", "check_token_presence")
            decision_span.set_attribute("auth.decision.result", "rejected")
            decision_span.set_attribute("error", True)
            decision_span.set_attribute("error.type", "MissingToken")
            decision_span.set_attribute("error.reason", "token_missing")
            decision_span.set_attribute("error.message", "Missing bearer token")
            decision_span.set_status(Status(StatusCode.ERROR, "Missing bearer token"))
        
        with tracer.start_as_current_span("auth.verify_jwt") as span:
            span.set_attribute("auth.operation", "verify_jwt")
            span.set_attribute("auth.token_present", False)
            span.set_attribute("error", True)
            span.set_attribute("error.type", "MissingToken")
            span.set_attribute("error.reason", "token_missing")
            span.set_attribute("error.message", "Missing bearer token")
            span.set_status(Status(StatusCode.ERROR, "Missing bearer token"))
        raise AuthenticationError("Missing bearer token")

    token = authorization.split(" ", 1)[1]

    # JWT Configuration for local verification
    JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "dhruva-jwt-secret-key-2024-super-secure")
    JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")

    # Always use tracing-aware implementation (OpenTelemetry handles no-op if not configured)
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
            # Expose raw JWT payload for any tenant-aware logic
            request.state.jwt_payload = payload
            # Extract tenant context from JWT if available
            if payload.get("schema_name"):
                request.state.tenant_schema = payload.get("schema_name")
                request.state.tenant_id = payload.get("tenant_id")
                request.state.tenant_uuid = payload.get("tenant_uuid")
                logger.info(
                    f"Extracted tenant schema from JWT: schema={payload.get('schema_name')}, tenant_id={payload.get('tenant_id')}"
                )
            else:
                logger.info(f"JWT payload does not contain schema_name. Available keys: {list(payload.keys())}")
            # Populate request state
            request.state.user_id = int(user_id) if isinstance(user_id, (str, int)) else user_id
            request.state.api_key_id = None
            request.state.api_key_name = None
            request.state.user_email = email
            request.state.is_authenticated = True
            request.state.jwt_payload = payload  # Store JWT payload for tenant resolution and serviceId extraction

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


async def validate_api_key_permissions(api_key: str, service: str, action: str, user_id: Optional[int] = None) -> Dict[str, Any]:
    """
    Validate API key has required permissions by calling auth-service.
    Emits OpenTelemetry spans so permission checks are visible in Jaeger.

    Args:
        api_key: The API key to validate
        service: Service name (asr, nmt, tts, etc.)
        action: Action type (read, inference)
    """
    # Always use tracing-aware implementation (OpenTelemetry handles no-op if not configured)
    with tracer.start_as_current_span("auth.validate") as validate_span:
        validate_span.set_attribute("auth.operation", "validate_api_key")
        validate_span.set_attribute("auth.service", service)
        validate_span.set_attribute("auth.action", action)
        validate_span.set_attribute("auth.api_key_present", bool(api_key))
        validate_span.set_attribute("auth.api_key_length", len(api_key) if api_key else 0)
        
        # Decision point: Check if API key is present
        with tracer.start_as_current_span("auth.decision.check_api_key") as decision_span:
            decision_span.set_attribute("auth.decision", "check_api_key_presence")
            if not api_key:
                decision_span.set_attribute("auth.decision.result", "rejected")
                decision_span.set_attribute("error", True)
                decision_span.set_attribute("error.type", "MissingAPIKey")
                decision_span.set_attribute("error.reason", "api_key_missing")
                decision_span.set_attribute("error.message", "API key is missing")
                decision_span.set_status(Status(StatusCode.ERROR, "API key missing"))
                validate_span.set_attribute("error", True)
                validate_span.set_attribute("error.type", "MissingAPIKey")
                validate_span.set_attribute("error.reason", "api_key_missing")
                validate_span.set_status(Status(StatusCode.ERROR, "API key missing"))
                raise AuthorizationError("API key is missing")
            decision_span.set_attribute("auth.decision.result", "passed")
            decision_span.set_status(Status(StatusCode.OK))
        
        # Call auth-service
        with tracer.start_as_current_span("auth.validate_api_key") as span:
            span.set_attribute("auth.operation", "validate_api_key")
            span.set_attribute("auth.service", service)
            span.set_attribute("auth.action", action)
            span.set_attribute("auth.api_key_present", bool(api_key))
            try:
                validate_url = f"{AUTH_SERVICE_URL}/api/v1/auth/validate-api-key"
                span.set_attribute("http.url", validate_url)
                span.set_attribute("http.method", "POST")

                payload = {
                    "api_key": api_key,
                    "service": service,
                    "action": action,
                }
                if user_id is not None:
                    payload["user_id"] = user_id
                # Debug: log what we are sending to auth-service
                logger.info(f"ASR validate_api_key_permissions: calling auth-service with payload={payload}")
                async with httpx.AsyncClient(timeout=5.0) as client:
                    response = await client.post(
                        validate_url,
                        json=payload,
                    )

                    span.set_attribute("http.status_code", response.status_code)

                if response.status_code == 200:
                    result = response.json()
                    # Decision point: Check if API key is valid
                    with tracer.start_as_current_span("auth.decision.check_validity") as validity_span:
                        validity_span.set_attribute("auth.decision", "check_api_key_validity")
                        if result.get("valid"):
                            validity_span.set_attribute("auth.decision.result", "approved")
                            validity_span.set_attribute("auth.valid", True)
                            validity_span.set_status(Status(StatusCode.OK))
                            span.set_attribute("auth.valid", True)
                            span.add_event("auth.validation.success")
                            span.set_status(Status(StatusCode.OK))
                            validate_span.set_attribute("auth.valid", True)
                            validate_span.set_status(Status(StatusCode.OK))
                            # Return full payload including user_id, permissions, etc.
                            return result
                    # API key invalid - extract detailed reason
                    error_msg = result.get("message", "Permission denied")
                    error_code = result.get("code", "PERMISSION_DENIED")
                    error_reason = result.get("reason", "unknown")
                    
                    validity_span.set_attribute("auth.decision.result", "rejected")
                    validity_span.set_attribute("error", True)
                    validity_span.set_attribute("error.type", "AuthorizationError")
                    validity_span.set_attribute("error.reason", error_reason)
                    validity_span.set_attribute("error.code", error_code)
                    validity_span.set_attribute("error.message", error_msg)
                    validity_span.set_status(Status(StatusCode.ERROR, error_msg))
                    
                    span.set_attribute("auth.valid", False)
                    span.set_attribute("error", True)
                    span.set_attribute("error.type", "AuthorizationError")
                    span.set_attribute("error.reason", error_reason)
                    span.set_attribute("error.code", error_code)
                    span.set_attribute("error.message", error_msg)
                    span.add_event("auth.validation.failed", {
                        "reason": error_reason,
                        "code": error_code,
                        "message": error_msg
                    })
                    span.set_status(Status(StatusCode.ERROR, error_msg))
                    
                    validate_span.set_attribute("auth.valid", False)
                    validate_span.set_attribute("error", True)
                    validate_span.set_attribute("error.type", "AuthorizationError")
                    validate_span.set_attribute("error.reason", error_reason)
                    validate_span.set_attribute("error.code", error_code)
                    validate_span.set_status(Status(StatusCode.ERROR, error_msg))
                    
                    raise AuthorizationError(error_msg)

                # Handle non-200 responses - extract error from detail or message field
                try:
                    error_data = response.json()
                    err_msg = error_data.get("detail") or error_data.get("message") or response.text
                    error_code = error_data.get("code", f"HTTP_{response.status_code}")
                    error_reason = error_data.get("reason", "auth_service_error")
                except Exception:
                    err_msg = response.text
                    error_code = f"HTTP_{response.status_code}"
                    error_reason = "auth_service_error"
                
                # Decision point: Auth service rejected
                with tracer.start_as_current_span("auth.decision.auth_service_response") as decision_span:
                    decision_span.set_attribute("auth.decision", "process_auth_service_response")
                    decision_span.set_attribute("auth.decision.result", "rejected")
                    decision_span.set_attribute("http.status_code", response.status_code)
                    decision_span.set_attribute("error", True)
                    decision_span.set_attribute("error.type", "AuthServiceError")
                    decision_span.set_attribute("error.reason", error_reason)
                    decision_span.set_attribute("error.code", error_code)
                    decision_span.set_attribute("error.message", err_msg)
                    decision_span.set_status(Status(StatusCode.ERROR, err_msg))
                
                span.set_attribute("error", True)
                span.set_attribute("error.type", "AuthServiceError")
                span.set_attribute("error.reason", error_reason)
                span.set_attribute("error.code", error_code)
                span.set_attribute("error.message", err_msg)
                span.set_attribute("auth.valid", False)
                span.add_event("auth.validation.failed", {
                    "status_code": response.status_code,
                    "reason": error_reason,
                    "code": error_code,
                    "message": err_msg
                })
                span.set_status(Status(StatusCode.ERROR, err_msg))
                span.record_exception(Exception(err_msg))
                
                validate_span.set_attribute("auth.valid", False)
                validate_span.set_attribute("error", True)
                validate_span.set_attribute("error.type", "AuthServiceError")
                validate_span.set_attribute("error.reason", error_reason)
                validate_span.set_attribute("error.code", error_code)
                validate_span.set_status(Status(StatusCode.ERROR, err_msg))
                
                logger.error(f"Auth service returned status {response.status_code}: {err_msg}")
                raise AuthorizationError(err_msg or "Failed to validate API key permissions")

            except httpx.TimeoutException as exc:
                # Decision point: Timeout
                with tracer.start_as_current_span("auth.decision.timeout") as timeout_span:
                    timeout_span.set_attribute("auth.decision", "handle_timeout")
                    timeout_span.set_attribute("auth.decision.result", "rejected")
                    timeout_span.set_attribute("error", True)
                    timeout_span.set_attribute("error.type", "TimeoutException")
                    timeout_span.set_attribute("error.reason", "auth_service_timeout")
                    timeout_span.set_attribute("error.message", "Auth service timeout")
                    timeout_span.set_status(Status(StatusCode.ERROR, "Auth service timeout"))
                
                span.set_attribute("error", True)
                span.set_attribute("error.type", "TimeoutException")
                span.set_attribute("error.reason", "auth_service_timeout")
                span.set_attribute("error.message", "Auth service timeout")
                span.set_status(Status(StatusCode.ERROR, "Auth service timeout"))
                span.record_exception(exc)
                
                validate_span.set_attribute("error", True)
                validate_span.set_attribute("error.type", "TimeoutException")
                validate_span.set_attribute("error.reason", "auth_service_timeout")
                validate_span.set_status(Status(StatusCode.ERROR, "Auth service timeout"))
                
                logger.error("Timeout calling auth-service for permission validation")
                raise AuthorizationError("Permission validation service unavailable")
            except httpx.RequestError as exc:
                # Decision point: Request error
                with tracer.start_as_current_span("auth.decision.request_error") as error_span:
                    error_span.set_attribute("auth.decision", "handle_request_error")
                    error_span.set_attribute("auth.decision.result", "rejected")
                    error_span.set_attribute("error", True)
                    error_span.set_attribute("error.type", "RequestError")
                    error_span.set_attribute("error.reason", "auth_service_unavailable")
                    error_span.set_attribute("error.message", str(exc))
                    error_span.set_status(Status(StatusCode.ERROR, str(exc)))
                
                span.set_attribute("error", True)
                span.set_attribute("error.type", "RequestError")
                span.set_attribute("error.reason", "auth_service_unavailable")
                span.set_attribute("error.message", str(exc))
                span.set_status(Status(StatusCode.ERROR, str(exc)))
                span.record_exception(exc)
                
                validate_span.set_attribute("error", True)
                validate_span.set_attribute("error.type", "RequestError")
                validate_span.set_attribute("error.reason", "auth_service_unavailable")
                validate_span.set_status(Status(StatusCode.ERROR, str(exc)))
                
                logger.error(f"Error calling auth-service: {exc}")
                raise AuthorizationError("Failed to validate API key permissions")
            except AuthorizationError:
                raise
            except Exception as exc:
                # Decision point: Unexpected error
                with tracer.start_as_current_span("auth.decision.unexpected_error") as unexpected_span:
                    unexpected_span.set_attribute("auth.decision", "handle_unexpected_error")
                    unexpected_span.set_attribute("auth.decision.result", "rejected")
                    unexpected_span.set_attribute("error", True)
                    unexpected_span.set_attribute("error.type", type(exc).__name__)
                    unexpected_span.set_attribute("error.reason", "unexpected_error")
                    unexpected_span.set_attribute("error.message", str(exc))
                    unexpected_span.set_status(Status(StatusCode.ERROR, str(exc)))
                
                span.set_attribute("error", True)
                span.set_attribute("error.type", type(exc).__name__)
                span.set_attribute("error.reason", "unexpected_error")
                span.set_attribute("error.message", str(exc))
                span.set_status(Status(StatusCode.ERROR, str(exc)))
                span.record_exception(exc)
                
                validate_span.set_attribute("error", True)
                validate_span.set_attribute("error.type", type(exc).__name__)
                validate_span.set_attribute("error.reason", "unexpected_error")
                validate_span.set_status(Status(StatusCode.ERROR, str(exc)))
                
                logger.error(f"Unexpected error validating permissions: {exc}")
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
    import os

    # Check if authentication is disabled
    # NOTE: For ASR we always enforce authentication + API key (no anonymous access),
    # to ensure API key ownership checks are consistently applied like TTS.
    env_auth_enabled = os.getenv("AUTH_ENABLED", "true").lower() == "true"
    env_require_api_key = os.getenv("REQUIRE_API_KEY", "true").lower() == "true"
    env_allow_anonymous = os.getenv("ALLOW_ANONYMOUS_ACCESS", "false").lower() == "true"

    auth_enabled = True
    require_api_key = True
    allow_anonymous = False

    auth_source = (x_auth_source or "API_KEY").upper()

    # Always use tracing-aware implementation (OpenTelemetry handles no-op if not configured)
    with tracer.start_as_current_span("request.authorize") as auth_span:
        auth_span.set_attribute("auth.operation", "authorize_request")
        auth_span.set_attribute("auth.source", auth_source)
        auth_span.set_attribute("auth.enabled", auth_enabled)
        auth_span.set_attribute("auth.require_api_key", require_api_key)
        auth_span.set_attribute("auth.allow_anonymous", allow_anonymous)
        auth_span.set_attribute("auth.authorization_present", bool(authorization))
        auth_span.set_attribute("auth.api_key_present", bool(x_api_key))
        # Debug log to see effective auth configuration for each request
        logger.info(
            "ASR AuthProvider: auth_source=%s, auth_enabled=%s, require_api_key=%s, allow_anonymous=%s",
            auth_source,
            auth_enabled,
            require_api_key,
            allow_anonymous,
        )
        
        try:
            # Decision point: Determine auth method
            with tracer.start_as_current_span("auth.decision.select_auth_method") as method_span:
                method_span.set_attribute("auth.decision", "select_auth_method")
                method_span.set_attribute("auth.source", auth_source)
                
                # If authentication is disabled or anonymous access is allowed, skip auth
                if not auth_enabled or (allow_anonymous and not require_api_key):
                    method_span.set_attribute("auth.decision.result", "skip")
                    method_span.set_attribute("auth.method", "NONE")
                    method_span.set_status(Status(StatusCode.OK))
                    auth_span.set_attribute("auth.method", "NONE")
                    request.state.user_id = None
                    request.state.api_key_id = None
                    request.state.api_key_name = None
                    request.state.user_email = None
                    request.state.is_authenticated = False
                    auth_span.set_attribute("auth.authorized", False)
                    auth_span.set_attribute("auth.skipped", True)
                    auth_span.set_status(Status(StatusCode.OK))
                    return {"user_id": None, "api_key_id": None, "user": None, "api_key": None}
                
                # Bearer token only
                if auth_source == "AUTH_TOKEN":
                    method_span.set_attribute("auth.decision.result", "jwt_token")
                    method_span.set_attribute("auth.method", "JWT")
                    method_span.set_status(Status(StatusCode.OK))
                    auth_span.set_attribute("auth.method", "JWT")
                    result = await authenticate_bearer_token(request, authorization)
                    # Check if tenant schema was extracted
                    tenant_schema = getattr(request.state, "tenant_schema", None)
                    if tenant_schema:
                        logger.info(f"AuthProvider: Tenant schema extracted from JWT: {tenant_schema}")
                    else:
                        logger.warning(f"AuthProvider: No tenant schema found in request.state after JWT auth. JWT payload keys: {list(getattr(request.state, 'jwt_payload', {}).keys())}")
                    auth_span.set_attribute("auth.authorized", True)
                    auth_span.set_attribute("auth.user_id", str(result.get("user_id", "")))
                    auth_span.set_status(Status(StatusCode.OK))
                    return result
                
                api_key = x_api_key or get_api_key_from_header(authorization)
                auth_span.set_attribute("auth.api_key_extracted", bool(api_key))
                
                # Check if authorization header contains Bearer token (even in API_KEY mode)
                # If so, extract tenant schema from JWT first
                if authorization and authorization.startswith("Bearer "):
                    try:
                        # Decode JWT to extract tenant info even if we're in API_KEY mode
                        from jose import jwt
                        JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "dhruva-jwt-secret-key-2024-super-secure")
                        JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
                        token = authorization.split(" ", 1)[1]
                        payload = jwt.decode(
                            token,
                            JWT_SECRET_KEY,
                            algorithms=[JWT_ALGORITHM],
                            options={"verify_signature": True, "verify_exp": True},
                        )
                        request.state.jwt_payload = payload
                        if payload.get("schema_name"):
                            request.state.tenant_schema = payload.get("schema_name")
                            request.state.tenant_id = payload.get("tenant_id")
                            request.state.tenant_uuid = payload.get("tenant_uuid")
                            logger.info(f"AuthProvider API_KEY mode: Extracted tenant schema from Bearer token: {payload.get('schema_name')}")
                    except Exception as e:
                        logger.debug(f"Could not extract tenant from Bearer token in API_KEY mode: {e}")
                
                # BOTH: Bearer + API key
                if auth_source == "BOTH":
                    method_span.set_attribute("auth.decision.result", "both")
                    method_span.set_attribute("auth.method", "JWT+API_KEY")
                    method_span.set_status(Status(StatusCode.OK))
                    auth_span.set_attribute("auth.method", "JWT+API_KEY")
                    
                    try:
                        # 1) Authenticate user via JWT
                        bearer_result = await authenticate_bearer_token(request, authorization)
                        jwt_user_id = bearer_result.get("user_id")

                        # 2) Extract API key
                        if not api_key:
                            raise AuthenticationError("Missing API key")

                        # 3) Validate API key + permissions via auth-service (single source of truth),
                        # passing jwt_user_id so auth-service can enforce ownership.
                        service, action = determine_service_and_action(request)
                        auth_result = await validate_api_key_permissions(api_key, service, action, user_id=jwt_user_id)
                        
                        # CRITICAL: Always check valid field - auth-service may return valid=false for ownership mismatch
                        if not auth_result.get("valid", False):
                            error_msg = auth_result.get("message", "API key does not belong to the authenticated user")
                            # Raise AuthenticationError - the error handler will format it with error + message
                            raise AuthenticationError(error_msg)

                        # 4) Populate request.state – keep JWT as primary identity
                        request.state.user_id = jwt_user_id
                        request.state.api_key_id = None
                        request.state.api_key_name = None
                        request.state.user_email = bearer_result.get("user", {}).get("email")
                        request.state.is_authenticated = True
                        
                        # Tenant schema should already be set by authenticate_bearer_token, but verify
                        if not getattr(request.state, "tenant_schema", None):
                            jwt_payload = getattr(request.state, "jwt_payload", {})
                            if jwt_payload.get("schema_name"):
                                request.state.tenant_schema = jwt_payload.get("schema_name")
                                request.state.tenant_id = jwt_payload.get("tenant_id")
                                logger.info(f"AuthProvider BOTH mode: Extracted tenant schema from JWT: {jwt_payload.get('schema_name')}")

                        auth_span.set_attribute("auth.authorized", True)
                        auth_span.set_attribute("auth.user_id", str(jwt_user_id))
                        auth_span.set_status(Status(StatusCode.OK))

                        return bearer_result
                    except (AuthenticationError, AuthorizationError, InvalidAPIKeyError, ExpiredAPIKeyError) as e:
                        # For ANY auth/key error in BOTH mode, surface a single, consistent message
                        logger.error(f"ASR BOTH mode: Authentication/Authorization error: {e}")
                        auth_span.set_attribute("auth.authorized", False)
                        auth_span.set_attribute("error", True)
                        auth_span.set_attribute("error.type", type(e).__name__)
                        auth_span.set_status(Status(StatusCode.ERROR, "API key does not belong to the authenticated user"))
                        raise AuthenticationError("API key does not belong to the authenticated user")
                    except Exception as e:
                        logger.error(f"ASR BOTH mode: Unexpected error: {e}", exc_info=True)
                        auth_span.set_attribute("auth.authorized", False)
                        auth_span.set_attribute("error", True)
                        auth_span.set_attribute("error.type", type(e).__name__)
                        auth_span.set_status(Status(StatusCode.ERROR, "API key does not belong to the authenticated user"))
                        # Even on unexpected errors we normalize the external message
                        raise AuthenticationError("API key does not belong to the authenticated user")
                
                # Default: API_KEY
                method_span.set_attribute("auth.decision.result", "api_key")
                method_span.set_attribute("auth.method", "API_KEY")
                method_span.set_status(Status(StatusCode.OK))
                auth_span.set_attribute("auth.method", "API_KEY")
                
                # Decision point: Check API key presence
                with tracer.start_as_current_span("auth.decision.check_api_key_presence") as key_span:
                    key_span.set_attribute("auth.decision", "check_api_key_presence")
                    if not api_key:
                        key_span.set_attribute("auth.decision.result", "rejected")
                        key_span.set_attribute("error.type", "MissingAPIKey")
                        key_span.set_attribute("error.reason", "api_key_missing")
                        key_span.set_attribute("error.message", "Missing API key")
                        key_span.set_status(Status(StatusCode.ERROR, "Missing API key"))
                        
                        auth_span.set_attribute("auth.authorized", False)
                        auth_span.set_attribute("error.type", "MissingAPIKey")
                        auth_span.set_attribute("error.reason", "api_key_missing")
                        auth_span.set_status(Status(StatusCode.ERROR, "Missing API key"))
                        raise AuthenticationError("Missing API key")
                    key_span.set_attribute("auth.decision.result", "passed")
                    key_span.set_status(Status(StatusCode.OK))
                
                service, action = determine_service_and_action(request)
                auth_result = await validate_api_key_permissions(api_key, service, action)
                
                # For API_KEY-only mode, we may not have a JWT; use auth-service user_id if present
                user_id = auth_result.get("user_id")
                request.state.user_id = user_id
                request.state.api_key_id = None
                request.state.api_key_name = None
                request.state.user_email = None
                request.state.is_authenticated = True
                
                # Check if tenant info is in auth_result (from auth-service)
                if auth_result.get("tenant_schema"):
                    request.state.tenant_schema = auth_result.get("tenant_schema")
                    request.state.tenant_id = auth_result.get("tenant_id")
                    logger.info(f"AuthProvider: Tenant schema from auth-service: {auth_result.get('tenant_schema')}")
                
                auth_span.set_attribute("auth.authorized", True)
                auth_span.set_attribute("auth.user_id", str(user_id) if user_id is not None else "unknown")
                auth_span.set_status(Status(StatusCode.OK))
                return {
                    "user_id": user_id,
                    "api_key_id": None,
                    "user": None,
                    "api_key": None
                }
                
        except AuthenticationError as exc:
            # Mark auth span as failed
            auth_span.set_attribute("auth.authorized", False)
            auth_span.set_attribute("error.type", "AuthenticationError")
            auth_span.set_attribute("error.reason", "authentication_failed")
            auth_span.set_status(Status(StatusCode.ERROR, str(exc)))
            # For BOTH mode, always surface a single, stable error message so
            # repeated calls with the same bad API key/JWT combo never flicker.
            if auth_source == "BOTH":
                raise AuthenticationError("API key does not belong to the authenticated user")
            raise
        except AuthorizationError as exc:
            # Mark auth span as failed
            auth_span.set_attribute("auth.authorized", False)
            auth_span.set_attribute("error.type", "AuthorizationError")
            auth_span.set_attribute("error.reason", "authorization_failed")
            auth_span.set_status(Status(StatusCode.ERROR, str(exc)))
            if auth_source == "BOTH":
                raise AuthenticationError("API key does not belong to the authenticated user")
            raise
        except Exception as exc:
            auth_span.set_attribute("auth.authorized", False)
            auth_span.set_attribute("error.type", type(exc).__name__)
            auth_span.set_attribute("error.reason", "unexpected_error")
            auth_span.set_status(Status(StatusCode.ERROR, str(exc)))
            logger.error(f"Unexpected authentication error: {exc}")
            raise AuthenticationError("Authentication failed")

    # Tracing-aware implementation
    with tracer.start_as_current_span("request.authorize") as auth_span:
        auth_span.set_attribute("auth.source", auth_source)
        auth_span.set_attribute("auth.enabled", auth_enabled)
        auth_span.set_attribute("auth.require_api_key", require_api_key)
        auth_span.set_attribute("auth.allow_anonymous", allow_anonymous)
        try:
            # If authentication is disabled or anonymous access is allowed, skip auth
            if not auth_enabled or (allow_anonymous and not require_api_key):
                request.state.user_id = None
                request.state.api_key_id = None
                request.state.api_key_name = None
                request.state.user_email = None
                request.state.is_authenticated = False
                auth_span.set_attribute("auth.authorized", False)
                auth_span.set_attribute("auth.skipped", True)
                auth_span.set_status(Status(StatusCode.OK))
                return {"user_id": None, "api_key_id": None, "user": None, "api_key": None}

            # Bearer token only
            if auth_source == "AUTH_TOKEN":
                result = await authenticate_bearer_token(request, authorization)
                auth_span.set_attribute("auth.method", "JWT")
                auth_span.set_attribute("auth.authorized", True)
                auth_span.set_status(Status(StatusCode.OK))
                return result

            # BOTH: Bearer + API key
            if auth_source == "BOTH":
                auth_span.set_attribute("auth.method", "JWT+API_KEY")
                try:
                    # 1) Authenticate user via JWT
                    bearer_result = await authenticate_bearer_token(request, authorization)
                    jwt_user_id = bearer_result.get("user_id")

                    # 2) Extract API key
                    api_key = x_api_key or get_api_key_from_header(authorization)
                    if not api_key:
                        raise AuthenticationError("Missing API key")

                    # 3) Validate API key + permissions via auth-service (single source of truth),
                    # passing jwt_user_id so auth-service can enforce ownership.
                    service, action = determine_service_and_action(request)
                    auth_result = await validate_api_key_permissions(api_key, service, action, user_id=jwt_user_id)
                    
                    # CRITICAL: Always check valid field - auth-service may return valid=false for ownership mismatch
                    if not auth_result.get("valid", False):
                        error_msg = auth_result.get("message", "API key does not belong to the authenticated user")
                        # Raise AuthenticationError - the error handler will format it with error + message
                        raise AuthenticationError(error_msg)

                    # 4) Populate request.state – keep JWT as primary identity
                    request.state.user_id = jwt_user_id
                    request.state.api_key_id = None
                    request.state.api_key_name = None
                    request.state.user_email = bearer_result.get("user", {}).get("email")
                    request.state.is_authenticated = True

                    auth_span.set_attribute("auth.authorized", True)
                    auth_span.set_attribute("auth.user_id", str(jwt_user_id))
                    auth_span.set_status(Status(StatusCode.OK))
                    return bearer_result
                except (AuthenticationError, AuthorizationError, InvalidAPIKeyError, ExpiredAPIKeyError) as e:
                    # For ANY auth/key error in BOTH mode, surface a single, consistent message
                    logger.error(f"ASR BOTH mode (tracing): Authentication/Authorization error: {e}")
                    auth_span.set_attribute("auth.authorized", False)
                    auth_span.set_attribute("error", True)
                    auth_span.set_attribute("error.type", type(e).__name__)
                    auth_span.set_status(Status(StatusCode.ERROR, "API key does not belong to the authenticated user"))
                    raise AuthenticationError("API key does not belong to the authenticated user")
                except Exception as e:
                    logger.error(f"ASR BOTH mode (tracing): Unexpected error: {e}", exc_info=True)
                    auth_span.set_attribute("auth.authorized", False)
                    auth_span.set_attribute("error", True)
                    auth_span.set_attribute("error.type", type(e).__name__)
                    auth_span.set_status(Status(StatusCode.ERROR, "API key does not belong to the authenticated user"))
                    # Even on unexpected errors we normalize the external message
                    raise AuthenticationError("API key does not belong to the authenticated user")

            # API key only
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
        except AuthenticationError as e:
            auth_span.set_attribute("auth.authorized", False)
            auth_span.set_attribute("error", True)
            auth_span.set_attribute("error.type", "AuthenticationError")
            auth_span.set_attribute("error.message", str(e))
            auth_span.set_status(Status(StatusCode.ERROR, str(e)))
            # For BOTH mode, always surface a single, stable error message
            if auth_source == "BOTH":
                raise AuthenticationError("API key does not belong to the authenticated user")
            raise
        except (InvalidAPIKeyError, ExpiredAPIKeyError, AuthorizationError) as e:
            auth_span.set_attribute("auth.authorized", False)
            auth_span.set_attribute("error", True)
            auth_span.set_attribute("error.type", type(e).__name__)
            auth_span.set_attribute("error.message", str(e))
            auth_span.set_status(Status(StatusCode.ERROR, str(e)))
            # For BOTH mode, convert all auth/key errors to consistent ownership message
            if auth_source == "BOTH":
                raise AuthenticationError("API key does not belong to the authenticated user")
            raise
        except Exception as e:
            auth_span.set_attribute("auth.authorized", False)
            auth_span.set_attribute("error", True)
            auth_span.set_attribute("error.type", type(e).__name__)
            auth_span.set_attribute("error.message", str(e))
            auth_span.set_status(Status(StatusCode.ERROR, str(e)))
            logger.error(f"Unexpected authentication error: {e}")
            # For BOTH mode, even unexpected errors should show consistent message
            if auth_source == "BOTH":
                raise AuthenticationError("API key does not belong to the authenticated user")
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
