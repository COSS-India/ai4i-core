"""
Request/response logging middleware for tracking API Gateway usage.

Uses structured JSON logging with trace correlation, compatible with OpenSearch dashboards.
"""

import time
import os
import json

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.datastructures import UploadFile
from ai4icore_logging import get_logger, get_correlation_id, get_organization

logger = get_logger(__name__)

# Environment variable to enable request body logging
LOG_REQUEST_BODY = os.getenv("LOG_REQUEST_BODY", "false").lower() == "true"
MAX_BODY_LOG_SIZE = int(os.getenv("MAX_BODY_LOG_SIZE", "10000"))  # Max 10KB by default


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Request logging middleware for tracking API usage."""

    def __init__(self, app):
        super().__init__(app)

    async def dispatch(self, request: Request, call_next):
        """Log request and response information with structured logging."""
        # Capture start time
        start_time = time.time()

        # Extract request info
        method = request.method
        path = request.url.path
        query_params = str(request.url.query) if request.url.query else ""
        client_ip = request.client.host if request.client else "unknown"
        user_agent = request.headers.get("user-agent", "unknown")

        # Extract auth context from request.state if available
        user_id = getattr(request.state, "user_id", None)
        api_key_id = getattr(request.state, "api_key_id", None)

        # Get correlation ID (set by CorrelationMiddleware)
        correlation_id = get_correlation_id(request)
        
        # Print incoming request details
        print("=" * 80)
        print(f"📥 INCOMING REQUEST - API Gateway")
        print(f"   Method: {method}")
        print(f"   Path: {path}")
        if query_params:
            print(f"   Query: {query_params}")
        print(f"   Client IP: {client_ip}")
        print(f"   User Agent: {user_agent}")
        print(f"   Correlation ID: {correlation_id}")
        if user_id:
            print(f"   User ID: {user_id}")
        if api_key_id:
            print(f"   API Key ID: {api_key_id}")
        
        # Print headers (excluding sensitive ones)
        print(f"   Headers:")
        for header_name, header_value in request.headers.items():
            if header_name.lower() in ['authorization', 'x-api-key', 'cookie']:
                # Mask sensitive headers
                if header_name.lower() == 'authorization':
                    masked = f"{header_value[:20]}..." if len(header_value) > 20 else "***"
                    print(f"      {header_name}: {masked}")
                else:
                    print(f"      {header_name}: ***")
            else:
                print(f"      {header_name}: {header_value}")
        
        # Log request body if enabled (optional, as it consumes the body stream)
        if method in ['POST', 'PUT', 'PATCH']:
            content_type = request.headers.get('content-type', '')
            content_length = request.headers.get('content-length', 'unknown')
            
            if LOG_REQUEST_BODY:
                try:
                    # Read body for logging
                    body_bytes = await request.body()
                    
                    # Recreate request stream so downstream handlers can read it
                    async def receive():
                        return {"type": "http.request", "body": body_bytes}
                    request._receive = receive
                    
                    if body_bytes and len(body_bytes) <= MAX_BODY_LOG_SIZE:
                        # Try to parse as JSON
                        try:
                            body_json = json.loads(body_bytes.decode('utf-8'))
                            print(f"   Request Body (JSON):")
                            body_str = json.dumps(body_json, indent=6)
                            for line in body_str.split('\n'):
                                print(f"      {line}")
                        except:
                            # If not JSON, show as string
                            body_str = body_bytes.decode('utf-8', errors='ignore')
                            if len(body_str) > 500:
                                print(f"   Request Body (first 500 chars): {body_str[:500]}...")
                            else:
                                print(f"   Request Body: {body_str}")
                    elif body_bytes:
                        print(f"   Request Body: [Too large to log: {len(body_bytes)} bytes, max: {MAX_BODY_LOG_SIZE}]")
                    else:
                        print(f"   Request Body: [Empty]")
                except Exception as e:
                    print(f"   Request Body: [Error reading: {e}]")
            else:
                print(f"   Request Body: [Content-Type: {content_type}, Length: {content_length} bytes] (body logging disabled)")
        
        print("=" * 80)

        # Process request first (this will trigger ObservabilityMiddleware which sets organization)
        # Note: FastAPI exception handlers (like RequestValidationError) will catch
        # exceptions and return responses, which will still come back through this middleware
        # We don't catch exceptions here - let FastAPI's exception handlers handle them
        # The response from exception handlers will still come back through this middleware
        response: Response
        try:
            response = await call_next(request)
        except Exception:
            # If an exception occurs, FastAPI's exception handlers will catch it
            # and return a response. That response will come back through this middleware.
            raise

        # Calculate processing time
        processing_time = time.time() - start_time

        # Determine log level based on status code
        status_code = response.status_code

        # Get organization from request.state first (set by ObservabilityMiddleware)
        # This is more reliable than contextvars in async middleware
        organization = getattr(request.state, "organization", None)

        # Fallback: try to get from context if request.state doesn't have it
        if not organization:
            try:
                organization = get_organization()
            except Exception:
                organization = None

        # Build context for structured logging
        log_context = {
            "method": method,
            "path": path,
            "status_code": status_code,
            "duration_ms": round(processing_time * 1000, 2),
            "client_ip": client_ip,
            "user_agent": user_agent,
        }

        if user_id:
            log_context["user_id"] = user_id
        if api_key_id:
            log_context["api_key_id"] = api_key_id
        if correlation_id:
            log_context["correlation_id"] = correlation_id
        if organization:
            log_context["organization"] = organization
        
        # Add gateway error context if available (for service unavailable scenarios)
        gateway_error_service = getattr(request.state, "gateway_error_service", None)
        if gateway_error_service:
            log_context["gateway_error_service"] = gateway_error_service
            log_context["gateway_error_type"] = getattr(request.state, "gateway_error_type", "unknown")

        # Print response details
        print("=" * 80)
        print(f"📤 OUTGOING RESPONSE - API Gateway")
        print(f"   Method: {method}")
        print(f"   Path: {path}")
        print(f"   Status Code: {status_code}")
        print(f"   Processing Time: {processing_time:.3f}s")
        print(f"   Correlation ID: {correlation_id}")
        print("=" * 80)
        
        # Log with appropriate level using structured logging
        # Skip logging successful requests (200-299) - these are logged at service level
        # Skip logging server errors (500+) from downstream services - these are logged at service level to avoid duplicates
        # Log gateway-generated server errors (500+) - these indicate gateway issues (service unavailable, etc.)
        # Log authentication (401) and authorization (403) errors at gateway level
        # Other client errors (400, 404, etc.) are also logged at gateway level
        if 200 <= status_code < 300:
            # Don't log successful requests - let downstream services handle this
            pass
        elif 400 <= status_code < 500:
            # Log client errors (401, 403, etc.) for authentication/authorization tracking at gateway
            logger.warning(
                f"{method} {path} - {status_code} - {processing_time:.3f}s",
                extra={"context": log_context},
            )
        else:
            # For server errors (500+), only log if it's gateway-generated (service unavailable, etc.)
            # If it came from a downstream service, skip logging to avoid duplicates
            downstream_response = getattr(request.state, "downstream_response", False)
            if gateway_error_service:
                # Gateway-generated error (service down, connection error, etc.) - log it
                logger.error(
                    f"{method} {path} - {status_code} - {processing_time:.3f}s",
                    extra={"context": log_context},
                )
            elif not downstream_response:
                # Gateway-generated error (not from downstream) - log it
                logger.error(
                    f"{method} {path} - {status_code} - {processing_time:.3f}s",
                    extra={"context": log_context},
                )
            # else: downstream service returned 500+ - already logged at service level, skip to avoid duplicates

        # Add processing time header
        response.headers["X-Process-Time"] = f"{processing_time:.3f}"

        return response

