"""
Correlation Middleware and Request Logging Middleware

Extracts correlation/trace ID from HTTP headers and sets it in logging context
for automatic inclusion in all log entries.
"""

import os
import time
import logging
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi import Request, Response
from typing import Optional

from .context import set_trace_id, get_trace_id, generate_trace_id
from .logger import get_logger


class CorrelationMiddleware(BaseHTTPMiddleware):
    """
    Middleware for correlation ID (trace ID) management.
    
    Extracts X-Correlation-ID from request headers, generates one if missing,
    and sets it in the logging context so it appears in all log entries.
    
    Also stores the correlation ID in request.state for use in the application.
    """
    
    def __init__(self, app, header_name: str = "X-Correlation-ID"):
        """
        Initialize correlation middleware.
        
        Args:
            app: FastAPI application instance
            header_name: HTTP header name to look for correlation ID
        """
        super().__init__(app)
        self.header_name = header_name
    
    async def dispatch(self, request: Request, call_next):
        """
        Process request and set correlation ID in logging context.
        
        Args:
            request: FastAPI request object
            call_next: Next middleware/handler in chain
            
        Returns:
            Response object
        """
        # Try to create a span for correlation middleware
        try:
            from opentelemetry import trace
            tracer = trace.get_tracer(__name__)
            span_context = tracer.start_as_current_span("middleware.correlation")
        except Exception:
            tracer = None
            span_context = None
        
        try:
            # Extract correlation ID from headers
            correlation_id = request.headers.get(self.header_name)
            
            # Generate if missing
            if not correlation_id:
                correlation_id = generate_trace_id()
            
            # Add to span
            if span_context:
                span = trace.get_current_span()
                if span:
                    span.set_attribute("correlation.id", correlation_id)
                    span.set_attribute("correlation.header", self.header_name)
                    span.set_attribute("correlation.generated", correlation_id not in request.headers)
            
            # Store in request.state for application use
            request.state.correlation_id = correlation_id
            request.state.trace_id = correlation_id  # Alias for compatibility
            
            # Set in logging context (so it appears in all logs)
            set_trace_id(correlation_id)
            
            try:
                # Process request
                response = await call_next(request)
                
                # Add correlation ID to response headers
                response.headers[self.header_name] = correlation_id
                
                return response
            finally:
                # Clear trace ID from context after request (optional, but good practice)
                # Note: This is optional since each request gets a new thread context
                # But it's good to clean up
                pass
        finally:
            if span_context:
                try:
                    span_context.__exit__(None, None, None)
                except Exception:
                    pass


def get_correlation_id(request: Request) -> Optional[str]:
    """
    Helper function to get correlation ID from request.
    
    Args:
        request: FastAPI request object
        
    Returns:
        Correlation ID if available, None otherwise
    """
    return getattr(request.state, 'correlation_id', None)


def get_trace_id_from_request(request: Request) -> Optional[str]:
    """
    Helper function to get trace ID from request (alias for correlation_id).
    
    Args:
        request: FastAPI request object
        
    Returns:
        Trace ID if available, None otherwise
    """
    return getattr(request.state, 'trace_id', None) or getattr(request.state, 'correlation_id', None)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """
    Request logging middleware with configurable filtering.
    
    Logs request/response information with structured JSON logging.
    Supports filtering health endpoints, metrics endpoints, and log levels
    via environment variables.
    """
    
    def __init__(self, app):
        """
        Initialize request logging middleware.
        
        Reads environment variables for filtering configuration:
        - EXCLUDE_HEALTH_LOGS: Set to "true" to skip logging /health endpoints
        - EXCLUDE_METRICS_LOGS: Set to "true" to skip logging /metrics and /enterprise/metrics endpoints
        - MIN_LOG_LEVEL: Minimum log level (DEBUG, INFO, WARNING, ERROR). Defaults to INFO.
        """
        super().__init__(app)
        
        # Read filtering configuration from environment variables
        self.exclude_health_logs = os.getenv("EXCLUDE_HEALTH_LOGS", "false").lower() == "true"
        self.exclude_metrics_logs = os.getenv("EXCLUDE_METRICS_LOGS", "false").lower() == "true"
        
        # Parse minimum log level
        min_log_level_str = os.getenv("MIN_LOG_LEVEL", "INFO").upper()
        self.min_log_level = getattr(logging, min_log_level_str, logging.INFO)
        
        # Get logger
        self.logger = get_logger(__name__)
        
        # Health endpoint patterns
        self.health_patterns = [
            "/health",
            "/api/v1/health",
            "/api/v1/llm/health",
            "/api/v1/nmt/health",
            "/api/v1/asr/health",
            "/api/v1/tts/health",
            "/api/v1/ocr/health",
            "/api/v1/ner/health",
            "/api/v1/transliteration/health",
            "/api/v1/language-detection/health",
            "/api/v1/speaker-diarization/health",
            "/api/v1/language-diarization/health",
            "/api/v1/audio-lang-detection/health",
            "/api/v1/pipeline/health",
        ]
        
        # Metrics endpoint patterns
        self.metrics_patterns = [
            "/metrics",
            "/enterprise/metrics",
            "/api/v1/metrics",
        ]
    
    def _should_skip_logging(self, path: str, status_code: int) -> bool:
        """
        Check if logging should be skipped based on path and configuration.
        
        Args:
            path: Request path
            status_code: HTTP status code
            
        Returns:
            True if logging should be skipped, False otherwise
        """
        path_lower = path.lower()
        
        # Check health endpoints
        if self.exclude_health_logs:
            if any(path_lower.endswith(pattern) or path_lower == pattern for pattern in self.health_patterns):
                return True
        
        # Check metrics endpoints
        if self.exclude_metrics_logs:
            if any(path_lower.endswith(pattern) or path_lower == pattern for pattern in self.metrics_patterns):
                return True
        
        return False
    
    def _should_log_by_level(self, status_code: int) -> bool:
        """
        Check if log should be written based on minimum log level and status code.
        
        Args:
            status_code: HTTP status code
            
        Returns:
            True if log should be written, False otherwise
        """
        # Map status codes to log levels
        if 200 <= status_code < 300:
            log_level = logging.INFO
        elif 400 <= status_code < 500:
            log_level = logging.WARNING
        elif 500 <= status_code < 600:
            log_level = logging.ERROR
        else:
            log_level = logging.INFO
        
        # Check if log level meets minimum threshold
        return log_level >= self.min_log_level
    
    async def dispatch(self, request: Request, call_next):
        """
        Process request and log information with filtering.
        
        Args:
            request: FastAPI request object
            call_next: Next middleware/handler in chain
            
        Returns:
            Response object
        """
        # Capture start time
        start_time = time.time()
        
        # Extract request info
        method = request.method
        path = request.url.path
        client_ip = request.client.host if request.client else "unknown"
        user_agent = request.headers.get("user-agent", "unknown")
        
        # Extract auth context from request.state if available
        user_id = getattr(request.state, "user_id", None)
        api_key_id = getattr(request.state, "api_key_id", None)
        
        # Get correlation ID (set by CorrelationMiddleware)
        correlation_id = get_correlation_id(request)
        
        # Process request
        try:
            response = await call_next(request)
        except Exception:
            # Let FastAPI exception handlers handle it
            raise
        
        # Calculate processing time
        processing_time = time.time() - start_time
        status_code = response.status_code
        
        # Check if logging should be skipped
        if self._should_skip_logging(path, status_code):
            # Add processing time header even if we skip logging
            response.headers["X-Process-Time"] = f"{processing_time:.3f}"
            return response
        
        # Check if log level meets minimum threshold
        if not self._should_log_by_level(status_code):
            response.headers["X-Process-Time"] = f"{processing_time:.3f}"
            return response
        
        # Extract trace_id from OpenTelemetry context
        trace_id = None
        jaeger_trace_url = None
        try:
            from opentelemetry import trace
            current_span = trace.get_current_span()
            if current_span:
                span_context = current_span.get_span_context()
                if span_context.is_valid and span_context.trace_id != 0:
                    trace_id = format(span_context.trace_id, '032x')
                    jaeger_trace_url = trace_id
        except Exception:
            pass
        
        # Get organization from request.state (set by ObservabilityMiddleware)
        organization = getattr(request.state, "organization", None)
        if not organization:
            try:
                from .context import get_organization
                organization = get_organization()
            except Exception:
                pass
        
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
        if trace_id:
            log_context["trace_id"] = trace_id
        if jaeger_trace_url:
            log_context["jaeger_trace_url"] = jaeger_trace_url
        
        # Add input/output details if available
        input_details = getattr(request.state, "input_details", None)
        if input_details:
            log_context["input_details"] = input_details
        
        output_details = getattr(request.state, "output_details", None)
        if output_details:
            log_context["output_details"] = output_details
        
        # Log with appropriate level using structured logging
        # Skip logging 400-series errors - these are logged at gateway level only
        # Log 200-series (success) and 500-series (server errors) at service level
        if 200 <= status_code < 300:
            self.logger.info(
                f"{method} {path} - {status_code} - {processing_time:.3f}s",
                extra={"context": log_context}
            )
        elif 400 <= status_code < 500:
            # Don't log 400-series errors - gateway handles this to avoid duplicates
            pass
        else:
            self.logger.error(
                f"{method} {path} - {status_code} - {processing_time:.3f}s",
                extra={"context": log_context}
            )
        
        # Add processing time header
        response.headers["X-Process-Time"] = f"{processing_time:.3f}"
        
        return response

