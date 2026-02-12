"""
Authentication and Authorization Middleware for API Gateway

This middleware handles authentication and authorization at the gateway level,
logging 401 and 403 errors with proper trace context.
"""

import os
import logging
from contextlib import nullcontext
from typing import Optional, Dict, Any, List
from fastapi import Request, HTTPException, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from auth_middleware import auth_middleware
from ai4icore_logging import get_logger, get_correlation_id

# OpenTelemetry for tracing
try:
    from opentelemetry import trace
    from opentelemetry.trace import Status, StatusCode
    TRACING_AVAILABLE = True
except ImportError:
    TRACING_AVAILABLE = False
    trace = None
    Status = None
    StatusCode = None

logger = get_logger(__name__)

# Function to get tracer dynamically (called at runtime, not import time)
# This ensures tracer is available after setup_tracing is called in main.py
def get_tracer():
    """Get tracer instance dynamically at runtime."""
    if not TRACING_AVAILABLE or not trace:
        return None
    try:
        return trace.get_tracer("api-gateway-service")
    except Exception:
        return None

# Public routes that don't require authentication
PUBLIC_ROUTES = [
    "/",
    "/health",
    "/api/v1/status",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/api/v1/auth/login",
    "/api/v1/auth/register",
    "/api/v1/auth/refresh",
    "/api/v1/try-it",
]

# Routes that require authentication but not specific permissions
AUTH_REQUIRED_ROUTES = [
    "/api/v1/auth",
    "/api/v1/config",
    "/api/v1/feature-flags",
    "/api/v1/metrics",
    "/api/v1/telemetry",
    "/api/v1/alerting",
    "/api/v1/dashboard",
    "/api/v1/asr",
    "/api/v1/tts",
    "/api/v1/nmt",
    "/api/v1/ocr",
    "/api/v1/ner",
    "/api/v1/transliteration",
    "/api/v1/language-detection",
    "/api/v1/model-management",
    "/api/v1/speaker-diarization",
    "/api/v1/language-diarization",
    "/api/v1/audio-lang-detection",
    "/api/v1/llm",
    "/api/v1/pipeline",
]


def is_public_route(path: str) -> bool:
    """Check if a route is public (no authentication required)."""
    # Exact match
    if path in PUBLIC_ROUTES:
        return True
    
    # Prefix match for public routes
    for public_route in PUBLIC_ROUTES:
        if path.startswith(public_route):
            return True
    
    return False


def requires_auth(path: str) -> bool:
    """Check if a route requires authentication."""
    # Public routes don't require auth
    if is_public_route(path):
        return False
    
    # Check if path matches any auth-required route prefix
    for auth_route in AUTH_REQUIRED_ROUTES:
        if path.startswith(auth_route):
            return True
    
    # Default: require auth for all other routes
    return True


class AuthGatewayMiddleware(BaseHTTPMiddleware):
    """
    Authentication and Authorization middleware for API Gateway.
    
    This middleware:
    1. Checks if the route requires authentication
    2. Validates JWT tokens for protected routes
    3. Logs 401 and 403 errors with trace context
    4. Sets user context in request.state for downstream services
    """
    
    def __init__(self, app):
        super().__init__(app)
        self.auth_enabled = os.getenv("AUTH_ENABLED", "true").lower() == "true"
    
    async def dispatch(self, request: Request, call_next):
        """Process request with authentication and authorization checks."""
        path = request.url.path
        method = request.method
        
        # Get correlation ID for logging
        correlation_id = get_correlation_id(request)
        
        # Skip authentication for public routes
        if not self.auth_enabled or is_public_route(path):
            # Still try to extract user info if token is present (for optional context)
            if self.auth_enabled:
                try:
                    user = await auth_middleware.optional_auth(request)
                    if user:
                        request.state.user = user
                        request.state.user_id = user.get("user_id")
                        request.state.is_authenticated = True
                except Exception:
                    pass  # Ignore errors for optional auth
            
            return await call_next(request)
        
        # Check if route requires authentication
        if not requires_auth(path):
            return await call_next(request)
        
        # Create main authorization span (similar to OCR service's request.authorize)
        # start_as_current_span automatically creates a child of the current active span (FastAPI span)
        # Get tracer dynamically at runtime (not at import time)
        tracer = get_tracer()
        if tracer:
            auth_span_context = tracer.start_as_current_span("request.authorize")
        else:
            auth_span_context = nullcontext()
        
        with auth_span_context as auth_span:
            if auth_span:
                auth_span.set_attribute("http.method", method)
                auth_span.set_attribute("http.route", path)
                auth_span.set_attribute("correlation_id", correlation_id or "unknown")
                auth_span.set_attribute("gateway.operation", "authorize_request")
            
            # Decision: Check if authorization header is present
            # Use the same tracer instance (already retrieved above)
            token_span_context = tracer.start_as_current_span("auth.decision.check_token_presence") if tracer else nullcontext()
            with token_span_context as token_span:
                auth_header = request.headers.get("Authorization")
                if token_span:
                    token_span.set_attribute("auth.decision", "check_token_presence")
                    token_span.set_attribute("auth.authorization_present", bool(auth_header))
                
                if not auth_header or not auth_header.startswith("Bearer "):
                    if token_span:
                        token_span.set_attribute("auth.decision.result", "rejected")
                        token_span.set_attribute("error.type", "MissingToken")
                        token_span.set_attribute("error.reason", "token_missing")
                        token_span.set_status(Status(StatusCode.ERROR, "Token missing"))
                        auth_span.set_attribute("auth.authorized", False)
                        auth_span.set_attribute("error.type", "MissingToken")
                        auth_span.set_status(Status(StatusCode.ERROR, "Token missing"))
                    
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="Authentication required",
                        headers={"WWW-Authenticate": "Bearer"},
                    )
                
                if token_span:
                    token_span.set_attribute("auth.decision.result", "passed")
                    token_span.set_status(Status(StatusCode.OK))
            
            # Extract token
            token = auth_header.split(" ")[1] if auth_header else None
            if auth_span:
                auth_span.set_attribute("auth.token_present", bool(token))
                auth_span.set_attribute("auth.token_length", len(token) if token else 0)
            
            # Decision: Verify token with auth service
            # Use the same tracer instance (already retrieved above)
            verify_span_context = tracer.start_as_current_span("auth.decision.verify_token") if tracer else nullcontext()
            with verify_span_context as verify_span:
                if verify_span:
                    verify_span.set_attribute("auth.decision", "verify_token")
                    verify_span.set_attribute("auth.method", "JWT")
                
                # Require authentication
                try:
                    user = await auth_middleware.require_auth(request)
                    
                    if verify_span:
                        verify_span.set_attribute("auth.decision.result", "passed")
                        verify_span.set_status(Status(StatusCode.OK))
                    
                    # Set user context in request state
                    request.state.user = user
                    request.state.user_id = user.get("user_id")
                    request.state.username = user.get("username")
                    request.state.permissions = user.get("permissions", [])
                    # Optional multi-tenant context from auth-service (if present)
                    request.state.tenant_id = user.get("tenant_id")
                    request.state.tenant_uuid = user.get("tenant_uuid")
                    request.state.schema_name = user.get("schema_name")
                    request.state.is_authenticated = True
                    
                    # Add user info to auth span
                    if auth_span:
                        auth_span.set_attribute("auth.authorized", True)
                        auth_span.set_attribute("auth.method", "JWT")
                        auth_span.set_attribute("user.id", str(user.get("user_id", "unknown")))
                        auth_span.set_attribute("user.username", user.get("username", "unknown"))
                        auth_span.set_attribute("user.permissions_count", len(user.get("permissions", [])))
                        auth_span.set_status(Status(StatusCode.OK))
                    
                    logger.info(
                        f"Authentication successful for {method} {path}",
                        extra={
                            "context": {
                                "method": method,
                                "path": path,
                                "user_id": user.get("user_id"),
                                "username": user.get("username"),
                                "correlation_id": correlation_id,
                            }
                        }
                    )
                    
                except HTTPException as e:
                    error_detail = str(e.detail)
                    
                    # Handle 401 Unauthorized
                    if e.status_code == status.HTTP_401_UNAUTHORIZED:
                        if verify_span:
                            verify_span.set_attribute("auth.decision.result", "rejected")
                            verify_span.set_attribute("error.type", "AuthenticationError")
                            verify_span.set_attribute("error.reason", "token_invalid")
                            verify_span.set_status(Status(StatusCode.ERROR, error_detail))
                        
                        # Mark auth span as error
                        if auth_span:
                            auth_span.set_status(Status(StatusCode.ERROR, error_detail))
                            auth_span.set_attribute("error.type", "authentication_error")
                            auth_span.set_attribute("error.message", error_detail)
                            auth_span.set_attribute("auth.authorized", False)
                            auth_span.set_attribute("http.status_code", 401)
                        
                        # Mark main FastAPI span as error (this is what shows in red in Jaeger)
                        if TRACING_AVAILABLE and trace:
                            current_span = trace.get_current_span()
                            if current_span:
                                current_span.set_status(Status(StatusCode.ERROR, f"Authentication failed: {error_detail}"))
                                current_span.set_attribute("http.status_code", 401)
                                current_span.set_attribute("error", True)
                                current_span.set_attribute("error.type", "authentication_error")
                                current_span.set_attribute("error.message", error_detail)
                        
                        logger.warning(
                            f"Authentication failed (401) for {method} {path}: {error_detail}",
                            extra={
                                "context": {
                                    "method": method,
                                    "path": path,
                                    "status_code": 401,
                                    "error": "authentication_failed",
                                    "error_detail": error_detail,
                                    "correlation_id": correlation_id,
                                    "client_ip": request.client.host if request.client else "unknown",
                                }
                            }
                        )
                        
                        # Return 401 response
                        return Response(
                            content=f'{{"detail": "{error_detail}", "error": "AUTHENTICATION_REQUIRED"}}',
                            status_code=401,
                            headers={"WWW-Authenticate": "Bearer"},
                            media_type="application/json"
                        )
                    
                    # Handle 403 Forbidden
                    elif e.status_code == status.HTTP_403_FORBIDDEN:
                        error_detail = str(e.detail)
                        
                        # Mark auth span as error
                        if auth_span:
                            auth_span.set_status(Status(StatusCode.ERROR, error_detail))
                            auth_span.set_attribute("error.type", "authorization_error")
                            auth_span.set_attribute("error.message", error_detail)
                            auth_span.set_attribute("auth.authorized", False)
                            auth_span.set_attribute("http.status_code", 403)
                        
                        # Mark main FastAPI span as error (this is what shows in red in Jaeger)
                        if TRACING_AVAILABLE and trace:
                            current_span = trace.get_current_span()
                            if current_span:
                                current_span.set_status(Status(StatusCode.ERROR, f"Authorization failed: {error_detail}"))
                                current_span.set_attribute("http.status_code", 403)
                                current_span.set_attribute("error", True)
                                current_span.set_attribute("error.type", "authorization_error")
                                current_span.set_attribute("error.message", error_detail)
                        
                        # Get user info if available
                        user_id = getattr(request.state, "user_id", None)
                        username = getattr(request.state, "username", None)
                        
                        logger.warning(
                            f"Authorization failed (403) for {method} {path}: {error_detail}",
                            extra={
                                "context": {
                                    "method": method,
                                    "path": path,
                                    "status_code": 403,
                                    "error": "authorization_failed",
                                    "error_detail": error_detail,
                                    "user_id": user_id,
                                    "username": username,
                                    "correlation_id": correlation_id,
                                    "client_ip": request.client.host if request.client else "unknown",
                                }
                            }
                        )
                        
                        # Return 403 response
                        return Response(
                            content=f'{{"detail": "{error_detail}", "error": "AUTHORIZATION_FAILED"}}',
                            status_code=403,
                            media_type="application/json"
                        )
                    
                    # Re-raise other HTTP exceptions
                    raise
                
                except Exception as e:
                    # Handle unexpected errors during authentication
                    error_msg = str(e)
                    
                    # Mark verify span as error
                    if verify_span:
                        verify_span.set_attribute("auth.decision.result", "rejected")
                        verify_span.set_attribute("error.type", "UnexpectedError")
                        verify_span.set_status(Status(StatusCode.ERROR, error_msg))
                    
                    # Mark auth span as error
                    if auth_span:
                        auth_span.set_status(Status(StatusCode.ERROR, error_msg))
                        auth_span.set_attribute("error.type", "authentication_error")
                        auth_span.set_attribute("error.message", error_msg)
                        auth_span.set_attribute("auth.authorized", False)
                    
                    # Mark main FastAPI span as error
                    if TRACING_AVAILABLE and trace:
                        current_span = trace.get_current_span()
                        if current_span:
                            current_span.set_status(Status(StatusCode.ERROR, f"Authentication error: {error_msg}"))
                            current_span.set_attribute("error", True)
                            current_span.set_attribute("error.type", "authentication_error")
                            current_span.set_attribute("error.message", error_msg)
                    
                    logger.error(
                        f"Unexpected error during authentication for {method} {path}: {error_msg}",
                        extra={
                            "context": {
                                "method": method,
                                "path": path,
                                "error": "authentication_error",
                                "error_detail": error_msg,
                                "correlation_id": correlation_id,
                            }
                        },
                        exc_info=True
                    )
                    
                    return Response(
                        content='{"detail": "Authentication service error", "error": "AUTHENTICATION_ERROR"}',
                        status_code=500,
                        media_type="application/json"
                    )
            
            # Process request with authenticated user
            response = await call_next(request)
            
            # Add user info to response headers for debugging (optional)
            if hasattr(request.state, "user_id"):
                response.headers["X-User-ID"] = str(request.state.user_id)
            # Add tenant context headers for debugging (if available)
            if hasattr(request.state, "tenant_id") and request.state.tenant_id:
                response.headers["X-Tenant-Id"] = str(request.state.tenant_id)
            
            return response

