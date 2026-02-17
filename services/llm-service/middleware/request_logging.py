"""
Request/response logging middleware for tracking API usage.
"""
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi import Request, Response
import logging
import sys
import time
import os

# Import OpenTelemetry to extract trace_id
try:
    from opentelemetry import trace
    TRACING_AVAILABLE = True
except ImportError:
    TRACING_AVAILABLE = False

# Get Jaeger URL from environment or use default
JAEGER_UI_URL = os.getenv("JAEGER_UI_URL", "http://localhost:16686")

# Get logger and configure with JSONFormatter
logger = logging.getLogger(__name__)

# Only configure if not already configured
if not logger.handlers:
    # Import JSONFormatter from ai4icore_logging
    try:
        from ai4icore_logging import JSONFormatter
        import os
        
        # Add stdout handler with JSONFormatter
        handler = logging.StreamHandler(sys.stdout)
        service_name = os.getenv("SERVICE_NAME", "llm-service")
        formatter = JSONFormatter(service_name=service_name)
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    except ImportError:
        # Fallback to basic logging if ai4icore_logging not available
        handler = logging.StreamHandler(sys.stdout)
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)

# Disable propagation to prevent duplicate logs
logger.propagate = False


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Request logging middleware for tracking API usage."""
    
    def __init__(self, app):
        super().__init__(app)
        
        # Read filtering configuration from environment variables
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
            "/api/v1/llm/health",
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
        """Log request and response information."""
        # Capture start time
        start_time = time.time()
        
        # Extract request info
        method = request.method
        path = request.url.path
        client_ip = request.client.host if request.client else "unknown"
        user_agent = request.headers.get("user-agent", "unknown")
        
        # Extract auth context from request.state if available
        user_id = getattr(request.state, 'user_id', None)
        api_key_id = getattr(request.state, 'api_key_id', None)
        
        # Process request
        response = await call_next(request)
        
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
        
        # Extract trace_id from OpenTelemetry context for Jaeger URL
        # IMPORTANT: Extract AFTER request processing to ensure span is fully initialized
        trace_id = None
        jaeger_trace_url = None
        if TRACING_AVAILABLE:
            try:
                current_span = trace.get_current_span()
                if current_span:
                    span_context = current_span.get_span_context()
                    # Format trace_id as hex string (Jaeger format) - 32 hex characters
                    # Ensure trace_id is non-zero (valid trace) and span is valid
                    if span_context.is_valid and span_context.trace_id != 0:
                        trace_id = format(span_context.trace_id, '032x')
                        # Store only trace_id - OpenSearch will use URL template to construct full URL
                        jaeger_trace_url = trace_id
            except Exception as e:
                # If trace extraction fails, continue without it
                logger.debug(f"Failed to extract trace ID: {e}")
                pass
        
        # Get correlation ID if available
        try:
            from ai4icore_logging import get_correlation_id
            correlation_id = get_correlation_id(request)
        except Exception:
            correlation_id = None
        
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
        
        # Logging strategy to avoid duplicates:
        # - 200-299: Log here (successful requests - service level)
        # - 400-499: Do NOT log (handled by API Gateway)
        # - 500-599: Log here (service errors - service level)
        if 200 <= status_code < 300:
            # Success - log at INFO level
            logger.info(
                f"{method} {path} - {status_code} - {processing_time:.3f}s",
                extra={"context": log_context}
            )
        elif 500 <= status_code < 600:
            # Server error - log at ERROR level
            logger.error(
                f"{method} {path} - {status_code} - {processing_time:.3f}s",
                extra={"context": log_context}
            )
        # Do NOT log 400-499 errors - they are logged at API Gateway level
        
        # Add processing time header
        response.headers["X-Process-Time"] = f"{processing_time:.3f}"
        
        return response
