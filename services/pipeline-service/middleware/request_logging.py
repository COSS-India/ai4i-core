"""
Request/response logging middleware for tracking Pipeline API usage.

Uses structured JSON logging with trace correlation.
"""

import os
import time

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

try:
    from ai4icore_logging import get_logger, get_correlation_id
    logger = get_logger(__name__)
    LOGGING_AVAILABLE = True
except ImportError:
    import logging
    logger = logging.getLogger(__name__)
    LOGGING_AVAILABLE = False
    
    def get_correlation_id(request: Request) -> str:
        """Fallback correlation ID getter."""
        return getattr(request.state, 'correlation_id', None) or request.headers.get('x-correlation-id', 'unknown')

# Import OpenTelemetry to extract trace_id
try:
    from opentelemetry import trace
    TRACING_AVAILABLE = True
except ImportError:
    TRACING_AVAILABLE = False

# Get Jaeger URL from environment or use default
JAEGER_UI_URL = os.getenv("JAEGER_UI_URL", "http://localhost:16686")


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Request logging middleware for tracking API usage."""

    def __init__(self, app):
        super().__init__(app)
        
        # Read filtering configuration from environment variables
        import logging
        exclude_health_env = os.getenv("EXCLUDE_HEALTH_LOGS", "false")
        exclude_metrics_env = os.getenv("EXCLUDE_METRICS_LOGS", "false")
        allowed_log_levels_env = os.getenv("ALLOWED_LOG_LEVELS", "DEBUG,INFO,WARNING,ERROR")
        
        self.exclude_health_logs = exclude_health_env.lower() == "true"
        self.exclude_metrics_logs = exclude_metrics_env.lower() == "true"
        
        # Parse allowed log levels (comma-separated: "INFO,ERROR" or "DEBUG,INFO,WARNING,ERROR")
        allowed_levels_str = [level.strip().upper() for level in allowed_log_levels_env.split(",")]
        self.allowed_log_levels = set()
        for level_str in allowed_levels_str:
            level_value = getattr(logging, level_str, None)
            if level_value is not None:
                self.allowed_log_levels.add(level_value)
        
        # If no valid levels found, default to all levels
        if not self.allowed_log_levels:
            self.allowed_log_levels = {logging.DEBUG, logging.INFO, logging.WARNING, logging.ERROR}
        
        # Log configuration at startup (only once per service instance)
        logger.info(
            f"RequestLoggingMiddleware initialized: EXCLUDE_HEALTH_LOGS={self.exclude_health_logs}, "
            f"EXCLUDE_METRICS_LOGS={self.exclude_metrics_logs}, ALLOWED_LOG_LEVELS={allowed_levels_str}",
            extra={"context": {
                "exclude_health_logs": self.exclude_health_logs,
                "exclude_metrics_logs": self.exclude_metrics_logs,
                "allowed_log_levels": allowed_levels_str,
            }}
        )
        
        # Health endpoint patterns
        self.health_patterns = [
            "/health",
            "/api/v1/health",
            "/api/v1/pipeline/health",
        ]
        
        # Metrics endpoint patterns
        self.metrics_patterns = [
            "/metrics",
            "/enterprise/metrics",
            "/api/v1/metrics",
        ]
    
    def _should_skip_logging(self, path: str, status_code: int) -> bool:
        """Check if logging should be skipped based on path and configuration."""
        path_lower = path.lower().rstrip('/')
        
        # Check health endpoints - match any path containing /health
        if self.exclude_health_logs:
            if '/health' in path_lower or path_lower.endswith('/health'):
                return True
        
        # Check metrics endpoints - match any path containing /metrics
        if self.exclude_metrics_logs:
            if '/metrics' in path_lower or path_lower.endswith('/metrics'):
                return True
        
        return False
    
    def _should_log_by_level(self, status_code: int) -> bool:
        """Check if log should be written based on allowed log levels and status code."""
        import logging
        # Map status codes to log levels
        if 200 <= status_code < 300:
            log_level = logging.INFO
        elif 400 <= status_code < 500:
            log_level = logging.WARNING
        elif 500 <= status_code < 600:
            log_level = logging.ERROR
        else:
            log_level = logging.INFO
        
        # Check if log level is in the allowed list
        return log_level in self.allowed_log_levels

    async def dispatch(self, request: Request, call_next):
        """Log request and response information with structured logging."""
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
        
        # Extract trace_id from OpenTelemetry context for Jaeger URL
        trace_id = None
        jaeger_trace_url = None
        if TRACING_AVAILABLE:
            try:
                current_span = trace.get_current_span()
                if current_span and current_span.get_span_context().is_valid:
                    span_context = current_span.get_span_context()
                    # Format trace_id as hex string (Jaeger format)
                    trace_id = format(span_context.trace_id, '032x')
                    # Create full Jaeger URL
                    # Store only trace_id - OpenSearch will use URL template to construct full URL
                    jaeger_trace_url = trace_id
            except Exception:
                # If trace extraction fails, continue without it
                pass

        # Process request
        # Note: FastAPI exception handlers (like RequestValidationError) will catch
        # exceptions and return responses, which will still come back through this middleware
        # We don't catch exceptions here - let FastAPI's exception handlers handle them
        # The response from exception handlers will still come back through this middleware
        try:
            response = await call_next(request)
        except Exception:
            # If an exception occurs, FastAPI's exception handlers will catch it
            # and return a response. That response will come back through this middleware
            # So we re-raise to let the exception handler work
            raise

        # Calculate processing time
        processing_time = time.time() - start_time

        # Determine log level based on status code
        status_code = response.status_code
        
        # Check if logging should be skipped (health/metrics filtering)
        if self._should_skip_logging(path, status_code):
            response.headers["X-Process-Time"] = f"{processing_time:.3f}"
            return response
        
        # Check if log level meets minimum threshold
        if not self._should_log_by_level(status_code):
            response.headers["X-Process-Time"] = f"{processing_time:.3f}"
            return response
        
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
        
        # Add trace_id and Jaeger URL if available
        if trace_id:
            log_context["trace_id"] = trace_id
        if jaeger_trace_url:
            log_context["jaeger_trace_url"] = jaeger_trace_url

        # Log with appropriate level using structured logging
        # Skip logging 400-series errors - these are logged at gateway level only
        # Log 200-series (success) and 500-series (server errors) at service level
        if LOGGING_AVAILABLE:
            if 200 <= status_code < 300:
                logger.info(
                    f"{method} {path} - {status_code} - {processing_time:.3f}s",
                    extra={"context": log_context}
                )
            elif 400 <= status_code < 500:
                # Don't log 400-series errors - gateway handles this to avoid duplicates
                pass
            else:
                logger.error(
                    f"{method} {path} - {status_code} - {processing_time:.3f}s",
                    extra={"context": log_context}
                )
        else:
            # Fallback to standard logging
            if 200 <= status_code < 300:
                logger.info(f"{method} {path} - {status_code} - {processing_time:.3f}s")
            elif 400 <= status_code < 500:
                # Don't log 400-series errors - gateway handles this to avoid duplicates
                pass
            else:
                logger.error(f"{method} {path} - {status_code} - {processing_time:.3f}s")

        # Add processing time header
        response.headers["X-Process-Time"] = f"{processing_time:.3f}"

        return response

