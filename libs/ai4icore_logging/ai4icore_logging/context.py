"""
Trace ID Context Manager

Manages trace ID (correlation ID) in async context for automatic
injection into log entries across the application.

Uses contextvars for async-compatible context management that works
correctly with FastAPI/Starlette async middleware.
"""

import contextvars
import uuid
from contextlib import contextmanager
from typing import Optional

# Context variable for trace ID (async-safe)
_trace_id_var: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar('trace_id', default=None)


def set_trace_id(trace_id: str) -> None:
    """
    Set the trace ID for the current async context.
    
    Args:
        trace_id: The trace/correlation ID to set
    """
    _trace_id_var.set(trace_id)


def get_trace_id() -> Optional[str]:
    """
    Get the trace ID for the current async context.
    
    Returns:
        The trace ID if set, None otherwise
    """
    return _trace_id_var.get()


def clear_trace_id() -> None:
    """
    Clear the trace ID for the current async context.
    """
    _trace_id_var.set(None)


def generate_trace_id() -> str:
    """
    Generate a new UUID-based trace ID.
    
    Returns:
        A new trace ID string
    """
    return str(uuid.uuid4())


@contextmanager
def TraceContext(trace_id: Optional[str] = None):
    """
    Context manager for trace ID.
    
    Usage:
        with TraceContext("abc-123"):
            logger.info("This log will have trace_id=abc-123")
    
    Args:
        trace_id: Trace ID to use. If None, generates a new one.
    """
    old_trace_id = get_trace_id()
    new_trace_id = trace_id or generate_trace_id()
    
    try:
        set_trace_id(new_trace_id)
        yield new_trace_id
    finally:
        if old_trace_id:
            set_trace_id(old_trace_id)
        else:
            clear_trace_id()

