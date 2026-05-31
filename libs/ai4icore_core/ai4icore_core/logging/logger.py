"""
Logger configuration.

Call configure_logging() once at service startup. After that, use standard
Python logging everywhere — no special imports needed in route handlers or
service code:

    import logging
    logger = logging.getLogger(__name__)
    logger.info("something happened")

All loggers propagate to the root logger, which has the JSONFormatter
attached, so every log line across the whole process comes out as structured
JSON — your code, FastAPI internals, SQLAlchemy, httpx, all of it.
"""

import logging
import sys
from typing import Dict, Optional

from .config import get_default_config
from .formatters import JSONFormatter
from ai4icore_core.context import get_trace_id, get_tenant_id

# Default third-party log levels applied when the caller does not supply their own.
# Services that pass third_party_log_levels replace this list entirely — they own
# the full set of overrides and must repeat any defaults they want to keep.
_DEFAULT_THIRD_PARTY_LEVELS: Dict[str, str] = {
    "httpx": "WARNING",
    "httpcore": "WARNING",
    "urllib3": "WARNING",
    "sqlalchemy.engine": "WARNING",
}


class ContextFilter(logging.Filter):
    """
    Injects request context into every log record before formatting.

    Attached to the root handler so it runs for every log line in the process —
    service code, FastAPI internals, SQLAlchemy, httpx, all of it — without
    any library needing to know about contextvars.

    The formatter then reads record.trace_id / record.tenant_id instead of
    calling the context functions itself.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        record.trace_id = get_trace_id()
        record.tenant_id = get_tenant_id()
        return True


def get_logger(name: str) -> logging.Logger:
    """Return a standard logger. configure_logging() handles the formatting."""
    return logging.getLogger(name)


def configure_logging(
    service_name: Optional[str] = None,
    log_level: Optional[str] = None,
    third_party_log_levels: Optional[Dict[str, str]] = None,
) -> None:
    """
    Configure the root logger with JSONFormatter writing to stdout.

    Must be called once at service startup before the first request.

    Args:
        service_name: Identifies the service in every log line. Falls back to
            the SERVICE_NAME env var, then "unknown".
        log_level: Root log level (DEBUG/INFO/WARNING/ERROR). Falls back to the
            LOG_LEVEL env var, then INFO.
        third_party_log_levels: Logger-name → level mapping for third-party
            libraries. When provided, replaces the built-in defaults entirely —
            the service owns the full list. When omitted, the built-in defaults
            are used:
                {
                    "httpx": "WARNING",
                    "httpcore": "WARNING",
                    "urllib3": "WARNING",
                    "sqlalchemy.engine": "WARNING",
                }
            Example — keep defaults but also silence boto3 and enable SQLAlchemy
            query logging:
                configure_logging(
                    service_name="my-service",
                    third_party_log_levels={
                        "httpx": "WARNING",
                        "httpcore": "WARNING",
                        "urllib3": "WARNING",
                        "sqlalchemy.engine": "INFO",  # want query logs
                        "boto3": "WARNING",
                        "botocore": "WARNING",
                    },
                )
    """
    cfg = get_default_config()
    name = service_name or cfg.service_name or "unknown"
    level = getattr(logging, (log_level or cfg.log_level_raw or "INFO").upper(), logging.INFO)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JSONFormatter(service_name=name))
    handler.addFilter(ContextFilter())

    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(level)
    root.addHandler(handler)

    levels = third_party_log_levels if third_party_log_levels is not None else _DEFAULT_THIRD_PARTY_LEVELS
    for logger_name, lvl in levels.items():
        logging.getLogger(logger_name).setLevel(getattr(logging, lvl.upper(), logging.WARNING))

    # Suppress uvicorn's built-in access log — RequestMiddleware handles request logging.
    uv_access = logging.getLogger("uvicorn.access")
    uv_access.handlers.clear()
    uv_access.propagate = False
    uv_access.disabled = True
