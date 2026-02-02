"""
JSON Log Formatter

Formats log records as structured JSON for easy parsing and searching.
"""

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from .context import get_trace_id, get_organization

# Try to import OpenTelemetry for trace ID extraction
try:
    from opentelemetry import trace
    OPENTELEMETRY_AVAILABLE = True
except ImportError:
    OPENTELEMETRY_AVAILABLE = False


class JSONFormatter(logging.Formatter):
    """
    JSON formatter for structured logging.
    
    Formats log records as JSON with standard fields:
    - timestamp: ISO 8601 format
    - level: Log level (INFO, ERROR, etc.)
    - service: Service name
    - trace_id: Correlation/trace ID
    - message: Log message
    - context: Additional context fields
    """
    
    def __init__(
        self,
        service_name: Optional[str] = None,
        service_version: Optional[str] = None,
        environment: Optional[str] = None,
        include_hostname: bool = True,
    ):
        """
        Initialize JSON formatter.
        
        Args:
            service_name: Name of the service (defaults to env SERVICE_NAME)
            service_version: Version of the service (defaults to env SERVICE_VERSION)
            environment: Environment name (defaults to env ENVIRONMENT)
            include_hostname: Whether to include hostname in logs
        """
        super().__init__()
        
        self.service_name = service_name or os.getenv("SERVICE_NAME", "unknown")
        self.service_version = service_version or os.getenv("SERVICE_VERSION", "1.0.0")
        self.environment = environment or os.getenv("ENVIRONMENT", "development")
        self.include_hostname = include_hostname
        
        if include_hostname:
            import socket
            self.hostname = socket.gethostname()
        else:
            self.hostname = None
    
    def format(self, record: logging.LogRecord) -> str:
        """
        Format log record as JSON.
        
        Args:
            record: Log record to format
            
        Returns:
            JSON string representation of the log
        """
        # Get trace ID from context (correlation ID)
        # Use try/except to handle any contextvars issues gracefully
        correlation_id = None
        try:
            correlation_id = get_trace_id()
        except Exception:
            # If contextvars fails, we'll generate a trace_id below
            pass
        
        # Try to get OpenTelemetry trace ID from active span (for Jaeger correlation)
        opentelemetry_trace_id = None
        if OPENTELEMETRY_AVAILABLE:
            try:
                span = trace.get_current_span()
                if span:
                    trace_context = span.get_span_context()
                    # Check if trace_id is non-zero (valid)
                    if trace_context.trace_id != 0:
                        # Format trace ID as hex string (Jaeger format) - 32 hex chars
                        opentelemetry_trace_id = format(trace_context.trace_id, "032x")
            except Exception:
                # Silently fail if OpenTelemetry is not properly initialized
                pass
        
        # Build base log structure
        log_data: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "service": self.service_name,
            "message": record.getMessage(),
        }
        
        # Prefer OpenTelemetry trace ID (for Jaeger correlation), fallback to correlation ID
        # Always ensure trace_id is set for correlation between logs and traces
        # CRITICAL: trace_id must ALWAYS be present in logs
        if opentelemetry_trace_id:
            log_data["trace_id"] = opentelemetry_trace_id
            # Also include correlation_id if different
            if correlation_id and correlation_id != opentelemetry_trace_id:
                log_data["correlation_id"] = correlation_id
        elif correlation_id:
            log_data["trace_id"] = correlation_id
        else:
            # Fallback: generate a trace ID if neither is available
            # This ensures trace_id is always present in logs
            # IMPORTANT: This should never happen in normal operation, but ensures logs always have trace_id
            from .context import generate_trace_id
            log_data["trace_id"] = generate_trace_id()
        
        # Get organization from context (if available)
        # Also check log record's extra context (set by RequestLoggingMiddleware)
        organization = None
        try:
            organization = get_organization()
        except Exception:
            pass
        
        # Fallback: check if organization is in the log record's extra context
        if not organization:
            context = getattr(record, "context", None)
            if context and isinstance(context, dict):
                organization = context.get("organization")
        
        # Always add organization field, even if None or "unknown" for debugging
        # This helps identify if organization extraction is working
        if organization:
            log_data["organization"] = organization
        else:
            # Add organization field with "unknown" to indicate it was checked but not found
            log_data["organization"] = "unknown"
        
        # Get tenant_id from context (if available)
        # Also check log record's extra context (set by RequestLoggingMiddleware)
        tenant_id = None
        try:
            from .context import get_tenant_id
            tenant_id = get_tenant_id()
        except Exception:
            pass
        
        # Fallback: check if tenant_id is in the log record's extra context
        if not tenant_id:
            context = getattr(record, "context", None)
            if context and isinstance(context, dict):
                tenant_id = context.get("tenant_id")
        
        # Always add tenant_id field
        # If not found, use temporary default value (temporary fix)
        if tenant_id:
            log_data["tenant_id"] = tenant_id
        else:
            # Temporary fix: use default tenant_id if not found
            # TODO: Remove this temporary fix once all users are registered to tenants
            log_data["tenant_id"] = "new-organization-487578"
        
        # Add service metadata
        log_data["service_version"] = self.service_version
        log_data["environment"] = self.environment
        
        if self.hostname:
            log_data["hostname"] = self.hostname
        
        # Add logger name (module)
        if record.name != "root":
            log_data["logger"] = record.name
        
        # Add file and line number for errors
        if record.levelno >= logging.ERROR:
            log_data["file"] = record.pathname
            log_data["line"] = record.lineno
            log_data["function"] = record.funcName
        
        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)
        
        # Add any extra context from the log record
        if hasattr(record, "context") and isinstance(record.context, dict):
            log_data["context"] = record.context
        
        # Add any extra fields passed via extra parameter
        # Exclude standard logging fields
        standard_fields = {
            "name", "msg", "args", "created", "filename", "funcName",
            "levelname", "levelno", "lineno", "module", "msecs",
            "message", "pathname", "process", "processName", "relativeCreated",
            "thread", "threadName", "exc_info", "exc_text", "stack_info",
            "context"
        }
        
        for key, value in record.__dict__.items():
            if key not in standard_fields and not key.startswith("_"):
                if key not in log_data:
                    log_data[key] = value
        
        # Convert to JSON string
        return json.dumps(log_data, default=str, ensure_ascii=False)

