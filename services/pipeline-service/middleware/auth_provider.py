"""
Authentication provider for FastAPI routes with API key validation via auth-service.
Pipeline service is stateless and uses auth-service for all validation.
"""
from fastapi import Request, Header, Depends
from typing import Optional, Dict, Any, Tuple
import logging
import httpx
import os

from middleware.exceptions import AuthenticationError, AuthorizationError

# Import OpenTelemetry for tracing
try:
    from opentelemetry import trace
    from opentelemetry.trace import Status, StatusCode
    TRACING_AVAILABLE = True
except ImportError:
    TRACING_AVAILABLE = False
    logging.warning("OpenTelemetry not available in auth_provider")

logger = logging.getLogger(__name__)

# Get tracer for detailed authentication tracing
if TRACING_AVAILABLE:
    tracer = trace.get_tracer("pipeline-service")
else:
    tracer = None

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


def determine_service_and_action(request: Request) -> Tuple[str, str]:
    """
    Determine service name and action from request path and method.
    
    Returns:
        Tuple of (service_name, action)
        service_name: pipeline
        action: read or inference
    """
    path = request.url.path.lower()
    method = request.method.upper()
    
    # Pipeline service
    service = "pipeline"
    
    # Determine action based on path and method
    if "/inference" in path and method == "POST":
        action = "inference"
    elif method == "GET" or "/info" in path:
        action = "read"
    else:
        # Default to inference for POST requests
        action = "inference" if method == "POST" else "read"
    
    return service, action


async def authenticate_bearer_token(request: Request, authorization: Optional[str]) -> Dict[str, Any]:
    """
    Validate JWT access token locally (signature + expiry check).
    Kong already validated the token, this is a defense-in-depth check.
    """
    from jose import JWTError, jwt
    
    if not tracer:
        return await _authenticate_bearer_token_impl(request, authorization)
    
    with tracer.start_as_current_span("auth.verify_jwt") as span:
        # Decision point: Check if token is present
        with tracer.start_as_current_span("auth.decision.check_token_presence") as decision_span:
            decision_span.set_attribute("auth.decision", "check_token_presence")
            if not authorization or not authorization.startswith("Bearer "):
                decision_span.set_attribute("auth.decision.result", "rejected")
                decision_span.set_attribute("error", True)
                decision_span.set_status(Status(StatusCode.ERROR, "Missing bearer token"))
                span.set_attribute("auth.result", "failed")
                span.set_attribute("auth.failure_reason", "missing_token")
                raise AuthenticationError("Missing bearer token")
            decision_span.set_attribute("auth.decision.result", "approved")
            decision_span.set_status(Status(StatusCode.OK))

        token = authorization.split(" ", 1)[1]
        span.set_attribute("auth.token_present", True)
        span.set_attribute("auth.token_length", len(token))
        
        # JWT Configuration for local verification
        JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "dhruva-jwt-secret-key-2024-super-secure")
        JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")

        try:
            # Decision point: Verify JWT signature and expiry
            with tracer.start_as_current_span("auth.decision.verify_jwt_signature") as verify_span:
                verify_span.set_attribute("auth.decision", "verify_jwt_signature")
                # Verify JWT signature and expiry locally
                payload = jwt.decode(
                    token,
                    JWT_SECRET_KEY,
                    algorithms=[JWT_ALGORITHM],
                    options={"verify_signature": True, "verify_exp": True}
                )
                verify_span.set_attribute("auth.decision.result", "valid")
                verify_span.set_status(Status(StatusCode.OK))
            
            # Extract user info from JWT claims
            user_id = payload.get("sub") or payload.get("user_id")
            email = payload.get("email", "")
            username = payload.get("username") or payload.get("email", "")
            roles = payload.get("roles", [])
            token_type = payload.get("type", "")
            
            # Decision point: Check token type
            with tracer.start_as_current_span("auth.decision.check_token_type") as type_span:
                type_span.set_attribute("auth.decision", "check_token_type")
                type_span.set_attribute("auth.token_type", token_type)
                if token_type != "access":
                    type_span.set_attribute("auth.decision.result", "rejected")
                    type_span.set_attribute("error", True)
                    type_span.set_status(Status(StatusCode.ERROR, "Invalid token type"))
                    span.set_attribute("auth.result", "failed")
                    span.set_attribute("auth.failure_reason", "invalid_token_type")
                    raise AuthenticationError("Invalid token type")
                type_span.set_attribute("auth.decision.result", "approved")
                type_span.set_status(Status(StatusCode.OK))
            
            # Decision point: Check user ID presence
            with tracer.start_as_current_span("auth.decision.check_user_id") as user_span:
                user_span.set_attribute("auth.decision", "check_user_id")
                if not user_id:
                    user_span.set_attribute("auth.decision.result", "rejected")
                    user_span.set_attribute("error", True)
                    user_span.set_status(Status(StatusCode.ERROR, "User ID not found"))
                    span.set_attribute("auth.result", "failed")
                    span.set_attribute("auth.failure_reason", "missing_user_id")
                    raise AuthenticationError("User ID not found in token")
                user_span.set_attribute("auth.decision.result", "approved")
                user_span.set_attribute("auth.user_id", str(user_id))
                user_span.set_status(Status(StatusCode.OK))

            # Populate request state
            request.state.user_id = int(user_id) if isinstance(user_id, (str, int)) else user_id
            request.state.api_key_id = None
            request.state.api_key_name = None
            request.state.user_email = email
            request.state.is_authenticated = True
            
            span.set_attribute("auth.result", "success")
            span.set_attribute("auth.user_id", str(user_id))
            span.set_attribute("auth.username", username)
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
            
        except JWTError as exc:
            # Decision point: JWT verification failed
            with tracer.start_as_current_span("auth.decision.jwt_verification_failed") as fail_span:
                fail_span.set_attribute("auth.decision", "handle_jwt_verification_failure")
                fail_span.set_attribute("auth.decision.result", "rejected")
                fail_span.set_attribute("error", True)
                fail_span.set_attribute("error.type", type(exc).__name__)
                fail_span.set_attribute("error.message", str(exc))
                fail_span.set_status(Status(StatusCode.ERROR, str(exc)))
                fail_span.record_exception(exc)
            
            span.set_attribute("auth.result", "failed")
            span.set_attribute("auth.failure_reason", "jwt_verification_failed")
            span.set_attribute("error", True)
            span.set_status(Status(StatusCode.ERROR, "JWT verification failed"))
            span.record_exception(exc)
            logger.warning(f"JWT verification failed: {exc}")
            raise AuthenticationError("Invalid or expired token")
        except Exception as exc:
            # Decision point: Unexpected error
            with tracer.start_as_current_span("auth.decision.unexpected_jwt_error") as unexpected_span:
                unexpected_span.set_attribute("auth.decision", "handle_unexpected_jwt_error")
                unexpected_span.set_attribute("auth.decision.result", "rejected")
                unexpected_span.set_attribute("error", True)
                unexpected_span.set_attribute("error.type", type(exc).__name__)
                unexpected_span.set_attribute("error.message", str(exc))
                unexpected_span.set_status(Status(StatusCode.ERROR, str(exc)))
                unexpected_span.record_exception(exc)
            
            span.set_attribute("auth.result", "failed")
            span.set_attribute("auth.failure_reason", "unexpected_error")
            span.set_attribute("error", True)
            span.set_status(Status(StatusCode.ERROR, "Unexpected JWT error"))
            span.record_exception(exc)
            logger.error(f"Unexpected error during JWT verification: {exc}")
            raise AuthenticationError("Failed to verify token")


async def _authenticate_bearer_token_impl(request: Request, authorization: Optional[str]) -> Dict[str, Any]:
    """Implementation without tracing - fallback when tracing not available."""
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


async def validate_api_key_permissions(api_key: str, service: str, action: str) -> bool:
    """
    Validate API key has required permissions by calling auth-service.
    
    Args:
        api_key: The API key to validate
        service: Service name (pipeline)
        action: Action type (read, inference)
    
    Returns:
        True if permission is granted, False otherwise
    
    Raises:
        AuthorizationError: If permission check fails
    """
    if not tracer:
        # Fallback if tracing not available
        return await _validate_api_key_permissions_impl(api_key, service, action)
    
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
                decision_span.set_status(Status(StatusCode.ERROR, "Missing API key"))
                validate_span.set_attribute("auth.result", "failed")
                validate_span.set_attribute("auth.failure_reason", "missing_api_key")
                raise AuthenticationError("Missing API key")
            decision_span.set_attribute("auth.decision.result", "approved")
            decision_span.set_status(Status(StatusCode.OK))
        
        # Call auth-service
        with tracer.start_as_current_span("auth.validate_api_key") as span:
            span.set_attribute("auth.service", service)
            span.set_attribute("auth.action", action)
            span.set_attribute("auth.api_key_present", True)
            
            try:
                validate_url = f"{AUTH_SERVICE_URL}/api/v1/auth/validate-api-key"
                span.set_attribute("http.url", validate_url)
                span.set_attribute("http.method", "POST")
                
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
                    
                    span.set_attribute("http.status_code", response.status_code)
                    
                    if response.status_code == 200:
                        result = response.json()
                        # Decision point: Check if API key is valid
                        with tracer.start_as_current_span("auth.decision.check_validity") as validity_span:
                            validity_span.set_attribute("auth.decision", "check_api_key_validity")
                            if result.get("valid"):
                                validity_span.set_attribute("auth.decision.result", "approved")
                                validity_span.set_status(Status(StatusCode.OK))
                                span.set_attribute("auth.result", "valid")
                                span.set_status(Status(StatusCode.OK))
                                validate_span.set_attribute("auth.result", "success")
                                validate_span.set_status(Status(StatusCode.OK))
                                return True
                            else:
                                error_msg = result.get("message", "Permission denied")
                                validity_span.set_attribute("auth.decision.result", "rejected")
                                validity_span.set_attribute("auth.rejection_reason", error_msg)
                                validity_span.set_attribute("error", True)
                                validity_span.set_status(Status(StatusCode.ERROR, error_msg))
                                span.set_attribute("auth.result", "invalid")
                                span.set_attribute("auth.rejection_reason", error_msg)
                                span.set_attribute("error", True)
                                span.set_status(Status(StatusCode.ERROR, error_msg))
                                validate_span.set_attribute("auth.result", "failed")
                                validate_span.set_attribute("auth.failure_reason", "permission_denied")
                                raise AuthorizationError(error_msg)
                    else:
                        # Decision point: Auth service rejected
                        with tracer.start_as_current_span("auth.decision.auth_service_response") as decision_span:
                            decision_span.set_attribute("auth.decision", "process_auth_service_response")
                            decision_span.set_attribute("auth.decision.result", "rejected")
                            decision_span.set_attribute("http.status_code", response.status_code)
                            decision_span.set_attribute("error", True)
                            error_msg = f"Auth service returned status {response.status_code}"
                            decision_span.set_status(Status(StatusCode.ERROR, error_msg))
                        
                        logger.error(f"Auth service returned status {response.status_code}: {response.text}")
                        span.set_attribute("auth.result", "failed")
                        span.set_attribute("error", True)
                        span.set_status(Status(StatusCode.ERROR, error_msg))
                        validate_span.set_attribute("auth.result", "failed")
                        validate_span.set_attribute("auth.failure_reason", "auth_service_error")
                        raise AuthorizationError("Failed to validate API key permissions")
                        
            except httpx.TimeoutException as exc:
                # Decision point: Timeout
                with tracer.start_as_current_span("auth.decision.timeout") as timeout_span:
                    timeout_span.set_attribute("auth.decision", "handle_timeout")
                    timeout_span.set_attribute("auth.decision.result", "rejected")
                    timeout_span.set_attribute("error", True)
                    timeout_span.set_attribute("error.type", "TimeoutException")
                    timeout_span.set_status(Status(StatusCode.ERROR, "Timeout"))
                    timeout_span.record_exception(exc)
                
                logger.error("Timeout calling auth-service for permission validation")
                span.set_attribute("auth.result", "failed")
                span.set_attribute("error", True)
                span.set_status(Status(StatusCode.ERROR, "Timeout"))
                span.record_exception(exc)
                validate_span.set_attribute("auth.result", "failed")
                validate_span.set_attribute("auth.failure_reason", "timeout")
                raise AuthorizationError("Permission validation service unavailable")
            except httpx.RequestError as exc:
                # Decision point: Request error
                with tracer.start_as_current_span("auth.decision.request_error") as error_span:
                    error_span.set_attribute("auth.decision", "handle_request_error")
                    error_span.set_attribute("auth.decision.result", "rejected")
                    error_span.set_attribute("error", True)
                    error_span.set_attribute("error.type", type(exc).__name__)
                    error_span.set_attribute("error.message", str(exc))
                    error_span.set_status(Status(StatusCode.ERROR, str(exc)))
                    error_span.record_exception(exc)
                
                logger.error(f"Error calling auth-service: {exc}")
                span.set_attribute("auth.result", "failed")
                span.set_attribute("error", True)
                span.set_status(Status(StatusCode.ERROR, "Request error"))
                span.record_exception(exc)
                validate_span.set_attribute("auth.result", "failed")
                validate_span.set_attribute("auth.failure_reason", "request_error")
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
                    unexpected_span.set_attribute("error.message", str(exc))
                    unexpected_span.set_status(Status(StatusCode.ERROR, str(exc)))
                    unexpected_span.record_exception(exc)
                
                logger.error(f"Unexpected error validating permissions: {exc}")
                span.set_attribute("auth.result", "failed")
                span.set_attribute("error", True)
                span.set_status(Status(StatusCode.ERROR, "Unexpected error"))
                span.record_exception(exc)
                validate_span.set_attribute("auth.result", "failed")
                validate_span.set_attribute("auth.failure_reason", "unexpected_error")
                raise AuthorizationError("Permission validation failed")


async def _validate_api_key_permissions_impl(api_key: str, service: str, action: str) -> bool:
    """Implementation without tracing - fallback when tracing not available."""
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
                    return True
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


async def AuthProvider(
    request: Request,
    authorization: Optional[str] = Header(None, alias="Authorization"),
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    x_auth_source: str = Header(default="API_KEY", alias="X-Auth-Source"),
) -> Dict[str, Any]:
    """Authentication provider dependency for FastAPI routes."""
    if not tracer:
        return await _auth_provider_impl(request, authorization, x_api_key, x_auth_source)
    
    with tracer.start_as_current_span("request.authorize") as auth_span:
        auth_span.set_attribute("auth.operation", "authorize_request")
        auth_source = (x_auth_source or "API_KEY").upper()
        auth_span.set_attribute("auth.source", auth_source)
        auth_span.set_attribute("http.method", request.method)
        auth_span.set_attribute("http.path", request.url.path)
        
        try:
            # Decision point: Determine auth method
            with tracer.start_as_current_span("auth.decision.select_auth_method") as method_span:
                method_span.set_attribute("auth.decision", "select_auth_method")
                method_span.set_attribute("auth.source", auth_source)
                
                # Handle Bearer token authentication (user tokens - no permission check needed)
                if auth_source == "AUTH_TOKEN":
                    method_span.set_attribute("auth.decision.result", "use_bearer_token")
                    method_span.set_status(Status(StatusCode.OK))
                    auth_span.set_attribute("auth.method", "JWT")
                    result = await authenticate_bearer_token(request, authorization)
                    auth_span.set_attribute("auth.result", "success")
                    auth_span.set_status(Status(StatusCode.OK))
                    return result
                
                # Handle BOTH Bearer token AND API key (already validated by API Gateway)
                elif auth_source == "BOTH":
                    method_span.set_attribute("auth.decision.result", "use_both")
                    method_span.set_status(Status(StatusCode.OK))
                    auth_span.set_attribute("auth.method", "JWT+API_KEY")
                    
                    try:
                        # 1) Authenticate via JWT
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
                            raise AuthenticationError("API key does not belong to the authenticated user")
                    
                        # 4) Populate request.state – keep JWT as primary identity (matching ASR/TTS/NMT)
                        request.state.user_id = jwt_user_id
                        request.state.api_key_id = None
                        request.state.api_key_name = None
                        request.state.user_email = bearer_result.get("user", {}).get("email")
                        request.state.is_authenticated = True
                        
                        auth_span.set_attribute("auth.result", "success")
                        auth_span.set_status(Status(StatusCode.OK))
                        return bearer_result
                    except (AuthenticationError, AuthorizationError, InvalidAPIKeyError, ExpiredAPIKeyError) as e:
                        # For ANY auth/key error in BOTH mode, surface a single, consistent message
                        logger.error(f"Pipeline BOTH mode: Authentication/Authorization error: {e}")
                        auth_span.set_attribute("auth.result", "failed")
                        auth_span.set_attribute("auth.failure_reason", "authentication_failed")
                        auth_span.set_status(Status(StatusCode.ERROR, "API key does not belong to the authenticated user"))
                        raise AuthenticationError("API key does not belong to the authenticated user")
                    except Exception as e:
                        logger.error(f"Pipeline BOTH mode: Unexpected error: {e}", exc_info=True)
                        auth_span.set_attribute("auth.result", "failed")
                        auth_span.set_attribute("auth.failure_reason", "unexpected_error")
                        auth_span.set_status(Status(StatusCode.ERROR, "API key does not belong to the authenticated user"))
                        # Even on unexpected errors we normalize the external message
                        raise AuthenticationError("API key does not belong to the authenticated user")
                
                # Handle API key authentication (requires permission check via auth-service)
                else:
                    method_span.set_attribute("auth.decision.result", "use_api_key")
                    method_span.set_status(Status(StatusCode.OK))
                    auth_span.set_attribute("auth.method", "API_KEY")
                    
                    # Decision point: Check API key presence
                    with tracer.start_as_current_span("auth.decision.check_api_key_presence") as key_span:
                        key_span.set_attribute("auth.decision", "check_api_key_presence")
                        api_key = x_api_key or get_api_key_from_header(authorization)
                        if not api_key:
                            key_span.set_attribute("auth.decision.result", "rejected")
                            key_span.set_attribute("error", True)
                            key_span.set_status(Status(StatusCode.ERROR, "Missing API key"))
                            auth_span.set_attribute("auth.result", "failed")
                            auth_span.set_attribute("auth.failure_reason", "missing_api_key")
                            raise AuthenticationError("Missing API key")
                        key_span.set_attribute("auth.decision.result", "approved")
                        key_span.set_status(Status(StatusCode.OK))
                    
                    # Determine service and action from request
                    service, action = determine_service_and_action(request)
                    auth_span.set_attribute("auth.service", service)
                    auth_span.set_attribute("auth.action", action)
                    
                    # Validate API key permissions via auth-service
                    await validate_api_key_permissions(api_key, service, action)
                    
                    # For API key only, we don't have user info
                    # Set minimal state
                    request.state.user_id = None
                    request.state.api_key_id = None
                    request.state.api_key_name = None
                    request.state.user_email = None
                    request.state.is_authenticated = True
                    
                    auth_span.set_attribute("auth.result", "success")
                    auth_span.set_status(Status(StatusCode.OK))
                    
                    # Return auth context
                    return {
                        "user_id": None,
                        "api_key_id": None,
                        "user": None,
                        "api_key": None
                    }
        
        except (AuthenticationError, AuthorizationError) as exc:
            auth_span.set_attribute("auth.result", "failed")
            auth_span.set_attribute("error", True)
            auth_span.set_attribute("error.type", type(exc).__name__)
            auth_span.set_attribute("error.message", str(exc))
            auth_span.set_status(Status(StatusCode.ERROR, str(exc)))
            auth_span.record_exception(exc)
            # For BOTH mode, always present a single, stable error message on any
            # auth/API-key failure so repeated calls behave consistently.
            if auth_source == "BOTH":
                raise AuthenticationError("API key does not belong to the authenticated user")
            raise
        except Exception as exc:
            auth_span.set_attribute("auth.result", "failed")
            auth_span.set_attribute("error", True)
            auth_span.set_attribute("error.type", type(exc).__name__)
            auth_span.set_attribute("error.message", str(exc))
            auth_span.set_status(Status(StatusCode.ERROR, "Authentication failed"))
            auth_span.record_exception(exc)
            logger.error(f"Authentication error: {exc}")
            if auth_source == "BOTH":
                raise AuthenticationError("API key does not belong to the authenticated user")
            raise AuthenticationError("Authentication failed")


async def _auth_provider_impl(
    request: Request,
    authorization: Optional[str],
    x_api_key: Optional[str],
    x_auth_source: str
) -> Dict[str, Any]:
    """Implementation without tracing - fallback when tracing not available."""
    auth_source = (x_auth_source or "API_KEY").upper()
    
    # Handle Bearer token authentication (user tokens - no permission check needed)
    if auth_source == "AUTH_TOKEN":
        return await authenticate_bearer_token(request, authorization)
    
    # Handle BOTH Bearer token AND API key (already validated by API Gateway)
    if auth_source == "BOTH":
        # 1) Validate Bearer token to get user info
        bearer_result = await authenticate_bearer_token(request, authorization)
        jwt_user_id = bearer_result.get("user_id")
        
        # 2) Extract API key
        api_key = x_api_key or get_api_key_from_header(authorization)
        if not api_key:
            raise AuthenticationError("Missing API key")
        
        # 3) (Lightweight) ownership enforcement: for pipeline we primarily depend on
        #    auth-service permissions; ownership is best enforced there. Here we only
        #    ensure that if an API key lookup is available, it must map to this user.
        #    If such a lookup path is added later, plug it in here similar to NMT/ASR.
        
        # 4) Validate API key permissions via auth-service
        service, action = determine_service_and_action(request)
        await validate_api_key_permissions(api_key, service, action)
        
        # 5) Populate request state with auth context from Bearer token
        request.state.user_id = jwt_user_id
        request.state.api_key_id = None  # Not tracked for BOTH in current pipeline design
        request.state.api_key_name = None
        request.state.user_email = bearer_result.get("user", {}).get("email")
        request.state.is_authenticated = True
        
        return bearer_result
    
    # Handle API key authentication (requires permission check via auth-service)
    try:
        # Extract API key from X-API-Key header first, then Authorization header
        api_key = x_api_key or get_api_key_from_header(authorization)
        
        if not api_key:
            raise AuthenticationError("Missing API key")
        
        # Determine service and action from request
        service, action = determine_service_and_action(request)
        
        # Validate API key permissions via auth-service
        await validate_api_key_permissions(api_key, service, action)
        
        # For API key only, we don't have user info from database
        # Set minimal state
        request.state.user_id = None
        request.state.api_key_id = None
        request.state.api_key_name = None
        request.state.user_email = None
        request.state.is_authenticated = True
        
        # Return auth context
        return {
            "user_id": None,
            "api_key_id": None,
            "user": None,
            "api_key": None
        }
        
    except (AuthenticationError, AuthorizationError):
        raise
    except Exception as e:
        logger.error(f"Authentication error: {e}")
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
        # Return None for optional auth
        return None






