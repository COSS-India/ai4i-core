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
_auth_type_var: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar("auth_type", default=None)
_llm_usage_input_tokens_var: contextvars.ContextVar[Optional[int]] = contextvars.ContextVar("llm_usage_input_tokens", default=None)
_llm_usage_output_tokens_var: contextvars.ContextVar[Optional[int]] = contextvars.ContextVar("llm_usage_output_tokens", default=None)
_llm_usage_model_name_var: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar("llm_usage_model_name", default=None)
# Distinct from llm_usage_model_name: this is the Model Registry's stable
# identity for the model behind the service (resolved via MMS at service
# lookup, before the upstream inference engine even responds), whereas
# model_name is the upstream engine's own echoed model name (only known
# after the response). Both are metric labels — see ai4i_core.observability.
_llm_usage_model_id_var: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar("llm_usage_model_id", default=None)


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


def set_auth_type(auth_type: str) -> contextvars.Token:
    return _auth_type_var.set(auth_type)


def get_auth_type() -> Optional[str]:
    return _auth_type_var.get()


def set_llm_usage_input_tokens(input_tokens: Optional[int]) -> contextvars.Token:
    return _llm_usage_input_tokens_var.set(input_tokens)


def get_llm_usage_input_tokens() -> Optional[int]:
    return _llm_usage_input_tokens_var.get()


def reset_llm_usage_input_tokens(token: contextvars.Token) -> None:
    _llm_usage_input_tokens_var.reset(token)


def set_llm_usage_output_tokens(output_tokens: Optional[int]) -> contextvars.Token:
    return _llm_usage_output_tokens_var.set(output_tokens)


def get_llm_usage_output_tokens() -> Optional[int]:
    return _llm_usage_output_tokens_var.get()


def reset_llm_usage_output_tokens(token: contextvars.Token) -> None:
    _llm_usage_output_tokens_var.reset(token)


def set_llm_usage_model_name(model_name: Optional[str]) -> contextvars.Token:
    return _llm_usage_model_name_var.set(model_name)


def get_llm_usage_model_name() -> Optional[str]:
    return _llm_usage_model_name_var.get()


def reset_llm_usage_model_name(token: contextvars.Token) -> None:
    _llm_usage_model_name_var.reset(token)


def set_llm_usage_model_id(model_id: Optional[str]) -> contextvars.Token:
    return _llm_usage_model_id_var.set(model_id)


def get_llm_usage_model_id() -> Optional[str]:
    return _llm_usage_model_id_var.get()


def reset_llm_usage_model_id(token: contextvars.Token) -> None:
    _llm_usage_model_id_var.reset(token)
