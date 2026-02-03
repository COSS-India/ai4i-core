"""
Authentication provider for FastAPI routes - supports JWT, API key, and BOTH with permission checks.
Uses local JWT signature + expiry verification (no auth-service calls for JWT).
Uses auth-service for API key permission validation.
"""
import os
import logging
from typing import Optional, Dict, Any, Tuple

import httpx
from fastapi import Request, Header
from jose import JWTError, jwt
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode

from middleware.exceptions import AuthenticationError, AuthorizationError

logger = logging.getLogger(__name__)
tracer = trace.get_tracer("audio-lang-detection-service")

# JWT Configuration for local verification
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "dhruva-jwt-secret-key-2024-super-secure")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")

AUTH_SERVICE_URL = os.getenv("AUTH_SERVICE_URL", "http://auth-service:8081")
AUTH_HTTP_TIMEOUT = float(os.getenv("AUTH_HTTP_TIMEOUT", "5.0"))


def get_api_key_from_header(authorization: Optional[str]) -> Optional[str]:
    """Extract API key from Authorization header."""
    if not authorization:
        return None
    
    # Support formats: "Bearer <key>", "<key>", "ApiKey <key>"
    if authorization.startswith("Bearer "):
        return None  # Bearer is JWT, not API key
    elif authorization.startswith("ApiKey "):
        return authorization[7:]
    else:
        return authorization


def determine_service_and_action(request: Request) -> Tuple[str, str]:
    path = request.url.path.lower()
    method = request.method.upper()
    service = "audio-lang-detection"
    if "/inference" in path and method == "POST":
        action = "inference"
    elif method == "GET":
        action = "read"
    else:
        action = "read"
    return service, action


async def validate_api_key_permissions(api_key: str, service: str, action: str) -> None:
    """Validate API key has required permissions by calling auth-service."""
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
            span.set_attribute("auth.service", service)
            span.set_attribute("auth.action", action)
            span.set_attribute("auth.api_key_present", True)
            
            try:
                validate_url = f"{AUTH_SERVICE_URL}/api/v1/auth/validate-api-key"
                span.set_attribute("http.url", validate_url)
                span.set_attribute("http.method", "POST")
                span.add_event("auth.validation.start", {
                    "service": service,
                    "action": action
                })
                
                async with httpx.AsyncClient(timeout=AUTH_HTTP_TIMEOUT) as client:
                    response = await client.post(
                        validate_url, json={"api_key": api_key, "service": service, "action": action}
                    )
                
                span.set_attribute("http.status_code", response.status_code)
                span.set_attribute("auth.response_status", response.status_code)
                
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
                            return
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
                    # FastAPI HTTPException uses "detail" field, auth-service uses "message"
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


async def _validate_api_key_permissions_impl(api_key: str, service: str, action: str) -> None:
    """Fallback implementation when tracing is not available."""
    validate_url = f"{AUTH_SERVICE_URL}/api/v1/auth/validate-api-key"
    async with httpx.AsyncClient(timeout=AUTH_HTTP_TIMEOUT) as client:
        response = await client.post(
            validate_url, json={"api_key": api_key, "service": service, "action": action}
        )
    if response.status_code == 200:
        result = response.json()
        if result.get("valid"):
            return
        error_msg = result.get("message", "Permission denied")
        raise AuthorizationError(error_msg)

    try:
        error_data = response.json()
        err_msg = error_data.get("detail") or error_data.get("message") or response.text
    except Exception:
        err_msg = response.text
    logger.error(f"Auth service returned status {response.status_code}: {err_msg}")
    raise AuthorizationError(err_msg or "Failed to validate API key permissions")


async def authenticate_bearer_token(request: Request, authorization: Optional[str]) -> Dict[str, Any]:
    """
    Validate JWT access token locally (signature + expiry check).
    Kong already validated the token, this is a defense-in-depth check.
    """
    if not tracer:
        return await _authenticate_bearer_token_impl(request, authorization)
    
    with tracer.start_as_current_span("auth.verify_jwt") as span:
        # Decision point: Check if token is present
        with tracer.start_as_current_span("auth.decision.check_token_presence") as decision_span:
            decision_span.set_attribute("auth.decision", "check_token_presence")
            if not authorization or not authorization.startswith("Bearer "):
                decision_span.set_attribute("auth.decision.result", "rejected")
                decision_span.set_attribute("error", True)
                decision_span.set_attribute("error.type", "MissingToken")
                decision_span.set_attribute("error.reason", "token_missing")
                decision_span.set_attribute("error.message", "Missing bearer token")
                decision_span.set_status(Status(StatusCode.ERROR, "Missing bearer token"))
                
                span.set_attribute("error", True)
                span.set_attribute("error.type", "MissingToken")
                span.set_attribute("error.reason", "token_missing")
                span.set_attribute("error.message", "Missing bearer token")
                span.set_status(Status(StatusCode.ERROR, "Missing bearer token"))
                raise AuthenticationError("Missing bearer token")
            decision_span.set_attribute("auth.decision.result", "passed")
            decision_span.set_status(Status(StatusCode.OK))

        token = authorization.split(" ", 1)[1]
        span.set_attribute("auth.token_present", True)
        span.set_attribute("auth.token_length", len(token))
        span.add_event("auth.jwt.verification.start")

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
                verify_span.set_attribute("auth.decision.result", "passed")
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
                    type_span.set_attribute("error.type", "InvalidTokenType")
                    type_span.set_attribute("error.reason", "wrong_token_type")
                    type_span.set_attribute("error.message", f"Invalid token type: {token_type}")
                    type_span.set_status(Status(StatusCode.ERROR, "Invalid token type"))
                    
                    span.set_attribute("error", True)
                    span.set_attribute("error.type", "InvalidTokenType")
                    span.set_attribute("error.reason", "wrong_token_type")
                    span.set_attribute("error.message", f"Invalid token type: {token_type}")
                    span.set_status(Status(StatusCode.ERROR, "Invalid token type"))
                    raise AuthenticationError("Invalid token type")
                type_span.set_attribute("auth.decision.result", "passed")
                type_span.set_status(Status(StatusCode.OK))
            
            # Decision point: Check user ID presence
            with tracer.start_as_current_span("auth.decision.check_user_id") as user_span:
                user_span.set_attribute("auth.decision", "check_user_id")
                if not user_id:
                    user_span.set_attribute("auth.decision.result", "rejected")
                    user_span.set_attribute("error", True)
                    user_span.set_attribute("error.type", "MissingUserID")
                    user_span.set_attribute("error.reason", "user_id_missing")
                    user_span.set_attribute("error.message", "User ID not found in token")
                    user_span.set_status(Status(StatusCode.ERROR, "User ID not found in token"))
                    
                    span.set_attribute("error", True)
                    span.set_attribute("error.type", "MissingUserID")
                    span.set_attribute("error.reason", "user_id_missing")
                    span.set_attribute("error.message", "User ID not found in token")
                    span.set_status(Status(StatusCode.ERROR, "User ID not found in token"))
                    raise AuthenticationError("User ID not found in token")
                user_span.set_attribute("auth.decision.result", "passed")
                user_span.set_attribute("auth.user_id", str(user_id))
                user_span.set_status(Status(StatusCode.OK))

            # Populate request state
            request.state.user_id = int(user_id) if isinstance(user_id, (str, int)) else user_id
            request.state.api_key_id = None
            request.state.api_key_name = None
            request.state.user_email = email
            request.state.is_authenticated = True
            request.state.jwt_payload = payload  # Store JWT payload for tenant resolution

            span.set_attribute("auth.user_id", str(user_id))
            span.set_attribute("auth.valid", True)
            span.add_event("auth.jwt.verification.success", {"user_id": str(user_id)})
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
                fail_span.set_attribute("error.type", "JWTError")
                # Determine specific reason
                error_reason = "token_expired" if "expired" in str(exc).lower() else "token_invalid"
                fail_span.set_attribute("error.reason", error_reason)
                fail_span.set_attribute("error.message", str(exc))
                fail_span.set_status(Status(StatusCode.ERROR, str(exc)))
            
            span.set_attribute("error", True)
            span.set_attribute("error.type", "JWTError")
            error_reason = "token_expired" if "expired" in str(exc).lower() else "token_invalid"
            span.set_attribute("error.reason", error_reason)
            span.set_attribute("error.message", str(exc))
            span.set_attribute("auth.valid", False)
            span.add_event("auth.jwt.verification.failed", {
                "reason": error_reason,
                "message": str(exc)
            })
            span.set_status(Status(StatusCode.ERROR, str(exc)))
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
                unexpected_span.set_attribute("error.reason", "unexpected_error")
                unexpected_span.set_attribute("error.message", str(exc))
                unexpected_span.set_status(Status(StatusCode.ERROR, str(exc)))
            
            span.set_attribute("error", True)
            span.set_attribute("error.type", type(exc).__name__)
            span.set_attribute("error.reason", "unexpected_error")
            span.set_attribute("error.message", str(exc))
            span.set_attribute("auth.valid", False)
            span.set_status(Status(StatusCode.ERROR, str(exc)))
            span.record_exception(exc)
            logger.error(f"Unexpected error during JWT verification: {exc}")
            raise AuthenticationError("Failed to verify token")


async def _authenticate_bearer_token_impl(request: Request, authorization: Optional[str]) -> Dict[str, Any]:
    """Fallback implementation when tracing is not available."""
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

        request.state.user_id = int(user_id) if isinstance(user_id, (str, int)) else user_id
        request.state.api_key_id = None
        request.state.api_key_name = None
        request.state.user_email = email
        request.state.is_authenticated = True
        request.state.jwt_payload = payload  # Store JWT payload for tenant resolution

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


async def AuthProvider(
    request: Request,
    authorization: Optional[str] = Header(None, alias="Authorization"),
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    x_auth_source: str = Header(default="API_KEY", alias="X-Auth-Source"),
) -> Dict[str, Any]:
    """Authentication provider for Audio Language Detection - supports AUTH_TOKEN, API_KEY, BOTH."""
    if not tracer:
        return await _auth_provider_impl(request, authorization, x_api_key, x_auth_source)
    
    with tracer.start_as_current_span("request.authorize") as auth_span:
        auth_span.set_attribute("auth.operation", "authorize_request")
        auth_source = (x_auth_source or "API_KEY").upper()
        auth_span.set_attribute("auth.source", auth_source)
        auth_span.set_attribute("auth.authorization_present", bool(authorization))
        auth_span.set_attribute("auth.api_key_present", bool(x_api_key))
        
        try:
            # Decision point: Determine auth method
            with tracer.start_as_current_span("auth.decision.select_auth_method") as method_span:
                method_span.set_attribute("auth.decision", "select_auth_method")
                method_span.set_attribute("auth.source", auth_source)
                
                if auth_source == "AUTH_TOKEN":
                    method_span.set_attribute("auth.decision.result", "jwt_token")
                    method_span.set_attribute("auth.method", "JWT")
                    method_span.set_status(Status(StatusCode.OK))
                    auth_span.set_attribute("auth.method", "JWT")
                    # Enforce API key requirement for this service
                    method_span.set_attribute("auth.decision.result", "rejected")
                    method_span.set_attribute("error", True)
                    method_span.set_attribute("error.type", "MissingAPIKey")
                    method_span.set_attribute("error.reason", "api_key_required_for_service")
                    method_span.set_status(Status(StatusCode.ERROR, "Missing API key"))
                    
                    auth_span.set_attribute("auth.authorized", False)
                    auth_span.set_attribute("error", True)
                    auth_span.set_attribute("error.type", "MissingAPIKey")
                    auth_span.set_attribute("error.reason", "api_key_required_for_service")
                    auth_span.set_status(Status(StatusCode.ERROR, "Missing API key"))
                    raise AuthenticationError("Missing API key")

                api_key = x_api_key or get_api_key_from_header(authorization)
                auth_span.set_attribute("auth.api_key_extracted", bool(api_key))

                if auth_source == "BOTH":
                    method_span.set_attribute("auth.decision.result", "both")
                    method_span.set_attribute("auth.method", "JWT+API_KEY")
                    method_span.set_status(Status(StatusCode.OK))
                    auth_span.set_attribute("auth.method", "JWT+API_KEY")
                    
                    # Decision point: Check API key for BOTH mode
                    with tracer.start_as_current_span("auth.decision.check_api_key_both") as both_span:
                        both_span.set_attribute("auth.decision", "check_api_key_for_both_mode")
                        bearer_result = await authenticate_bearer_token(request, authorization)
                        if not api_key:
                            both_span.set_attribute("auth.decision.result", "rejected")
                            both_span.set_attribute("error", True)
                            both_span.set_attribute("error.type", "MissingAPIKey")
                            both_span.set_attribute("error.reason", "api_key_missing_in_both_mode")
                            both_span.set_status(Status(StatusCode.ERROR, "Missing API key"))
                            
                            auth_span.set_attribute("auth.authorized", False)
                            auth_span.set_attribute("error", True)
                            auth_span.set_attribute("error.type", "MissingAPIKey")
                            auth_span.set_attribute("error.reason", "api_key_missing_in_both_mode")
                            auth_span.set_status(Status(StatusCode.ERROR, "Missing API key"))
                            raise AuthenticationError("Missing API key")
                        both_span.set_attribute("auth.decision.result", "passed")
                        both_span.set_status(Status(StatusCode.OK))
                    
                    service, action = determine_service_and_action(request)
                    await validate_api_key_permissions(api_key, service, action)
                    auth_span.set_attribute("auth.authorized", True)
                    auth_span.set_attribute("auth.user_id", str(bearer_result.get("user_id", "")))
                    auth_span.set_status(Status(StatusCode.OK))
                    return bearer_result

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
                        # Don't record exception here - error handler will do it
                        raise AuthenticationError("Missing API key")
                    key_span.set_attribute("auth.decision.result", "passed")
                    key_span.set_status(Status(StatusCode.OK))

                service, action = determine_service_and_action(request)
                await validate_api_key_permissions(api_key, service, action)
                
                request.state.user_id = None
                request.state.api_key_id = None
                request.state.api_key_name = None
                request.state.user_email = None
                request.state.is_authenticated = True
                
                auth_span.set_attribute("auth.authorized", True)
                auth_span.set_status(Status(StatusCode.OK))
                return {"user_id": None, "api_key_id": None, "user": None, "api_key": {"masked": True}}
                
        except AuthenticationError as exc:
            # Mark auth span as failed (error handler will create request.reject span)
            auth_span.set_attribute("auth.authorized", False)
            auth_span.set_attribute("error.type", "AuthenticationError")
            auth_span.set_attribute("error.reason", "authentication_failed")
            auth_span.set_status(Status(StatusCode.ERROR, str(exc)))
            # Don't record exception here - error handler will do it
            raise
        except AuthorizationError as exc:
            # Mark auth span as failed (error handler will create request.reject span)
            auth_span.set_attribute("auth.authorized", False)
            auth_span.set_attribute("error.type", "AuthorizationError")
            auth_span.set_attribute("error.reason", "authorization_failed")
            auth_span.set_status(Status(StatusCode.ERROR, str(exc)))
            # Don't record exception here - error handler will do it
            raise


async def _auth_provider_impl(
    request: Request,
    authorization: Optional[str],
    x_api_key: Optional[str],
    x_auth_source: str,
) -> Dict[str, Any]:
    """Fallback implementation when tracing is not available."""
    auth_source = (x_auth_source or "API_KEY").upper()

    if auth_source == "AUTH_TOKEN":
        # Enforce API key requirement for this service
        raise AuthenticationError("Missing API key")

    api_key = x_api_key or get_api_key_from_header(authorization)

    if auth_source == "BOTH":
        bearer_result = await _authenticate_bearer_token_impl(request, authorization)
        if not api_key:
            raise AuthenticationError("Missing API key")
        service, action = determine_service_and_action(request)
        await _validate_api_key_permissions_impl(api_key, service, action)
        return bearer_result

    # Default: API_KEY
    if not api_key:
        raise AuthenticationError("Missing API key")

    service, action = determine_service_and_action(request)
    await _validate_api_key_permissions_impl(api_key, service, action)

    request.state.user_id = None
    request.state.api_key_id = None
    request.state.api_key_name = None
    request.state.user_email = None
    request.state.is_authenticated = True

    return {"user_id": None, "api_key_id": None, "user": None, "api_key": {"masked": True}}


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


