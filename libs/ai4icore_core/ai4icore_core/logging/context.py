"""
Re-exports from ai4icore_core.context for backward compatibility.

The actual ContextVar objects live in ai4icore_core.context (zero-dep shared layer).
Importing from here or from ai4icore_core.context is equivalent — both reference
the same ContextVar instances.
"""

from ai4icore_core.context import (
    generate_trace_id,
    set_trace_id,
    get_trace_id,
    reset_trace_id,
    set_tenant_id,
    get_tenant_id,
    reset_tenant_id,
)

__all__ = [
    "generate_trace_id",
    "set_trace_id",
    "get_trace_id",
    "reset_trace_id",
    "set_tenant_id",
    "get_tenant_id",
    "reset_tenant_id",
]
