"""
Shared request context — zero external dependencies.

Single source of truth for async-safe context propagation across all
ai4i_core subpackages (logging, observability, telemetry).

Each asyncio Task (i.e. each HTTP request) gets its own isolated copy of
these vars — equivalent to Java's ThreadLocal but scoped to a coroutine chain.
"""

import contextvars
import uuid
from typing import Optional

_trace_id_var: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar("trace_id", default=None)
_tenant_id_var: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar("tenant_id", default=None)
_user_id_var: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar("user_id", default=None)
_endpoint_path_var: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar("endpoint_path", default=None)


def generate_trace_id() -> str:
    """Generate a new 32-hex trace ID (OTel-compatible, no hyphens)."""
    return uuid.uuid4().hex


def set_trace_id(trace_id: str) -> contextvars.Token:
    return _trace_id_var.set(trace_id)


def get_trace_id() -> Optional[str]:
    return _trace_id_var.get()


def reset_trace_id(token: contextvars.Token) -> None:
    _trace_id_var.reset(token)


def set_tenant_id(tenant_id: str) -> contextvars.Token:
    return _tenant_id_var.set(tenant_id)


def get_tenant_id() -> Optional[str]:
    return _tenant_id_var.get()


def reset_tenant_id(token: contextvars.Token) -> None:
    _tenant_id_var.reset(token)


def set_endpoint_path(endpoint_path: str) -> contextvars.Token:
    return _endpoint_path_var.set(endpoint_path)


def get_endpoint_path() -> Optional[str]:
    return _endpoint_path_var.get()


def set_user_id(user_id: str) -> contextvars.Token:
    return _user_id_var.set(user_id)


def get_user_id() -> Optional[str]:
    return _user_id_var.get()


def reset_user_id(token: contextvars.Token) -> None:
    _user_id_var.reset(token)
