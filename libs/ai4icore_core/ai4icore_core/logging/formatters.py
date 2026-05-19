"""
JSON Log Formatter

Formats log records as structured JSON for easy parsing and searching.
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from .config import get_default_config
from ai4icore_core.context import generate_trace_id


class JSONFormatter(logging.Formatter):
    """
    JSON formatter for structured logging.

    Formats log records as JSON with standard fields:
    - timestamp: ISO 8601 format
    - level: Log level (INFO, ERROR, etc.)
    - service: Service name
    - trace_id: 32-hex trace ID (from request context)
    - tenant_id: Tenant identifier
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
        super().__init__()

        cfg = get_default_config()
        self.service_name = service_name or cfg.service_name or "unknown"
        self.service_version = service_version or cfg.service_version or "1.0.0"
        self.environment = environment or cfg.environment or "development"
        self.include_hostname = include_hostname

        if include_hostname:
            import socket
            self.hostname = socket.gethostname()
        else:
            self.hostname = None

    def format(self, record: logging.LogRecord) -> str:
        # ContextFilter (on the root handler) already injected trace_id / tenant_id
        # into the record before format() is called. Read from the record directly.
        trace_id = getattr(record, "trace_id", None) or generate_trace_id()

        tenant_id = getattr(record, "tenant_id", None)
        if not tenant_id:
            context = getattr(record, "context", None)
            if isinstance(context, dict):
                tenant_id = context.get("tenant_id")

        log_data: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "service": self.service_name,
            "trace_id": trace_id,
            "tenant_id": tenant_id or "system",
            "message": record.getMessage(),
            "service_version": self.service_version,
            "environment": self.environment,
        }

        if self.hostname:
            log_data["hostname"] = self.hostname

        if record.name != "root":
            log_data["logger"] = record.name

        if record.levelno >= logging.ERROR:
            log_data["file"] = record.pathname
            log_data["line"] = record.lineno
            log_data["function"] = record.funcName

        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        if hasattr(record, "context") and isinstance(record.context, dict):
            log_data["context"] = record.context

        standard_fields = {
            "name", "msg", "args", "created", "filename", "funcName",
            "levelname", "levelno", "lineno", "module", "msecs",
            "message", "pathname", "process", "processName", "relativeCreated",
            "thread", "threadName", "exc_info", "exc_text", "stack_info",
            "context",
        }
        for key, value in record.__dict__.items():
            if key not in standard_fields and not key.startswith("_") and key not in log_data:
                log_data[key] = value

        return json.dumps(log_data, default=str, ensure_ascii=False)
