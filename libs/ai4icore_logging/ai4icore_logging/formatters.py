"""
JSON Log Formatter

Formats log records as structured JSON for easy parsing and searching.
"""

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from .context import get_trace_id


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
        # Get trace ID from context
        trace_id = get_trace_id()
        
        # Build base log structure
        log_data: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "service": self.service_name,
            "message": record.getMessage(),
        }
        
        # Add trace ID if available
        if trace_id:
            log_data["trace_id"] = trace_id
        
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

