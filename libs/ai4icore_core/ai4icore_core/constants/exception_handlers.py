"""
BACKWARD COMPATIBILITY — re-exports from ai4icore_exceptions.
New code should import from ai4icore_exceptions directly.

Requires: pip install ai4icore-constants[compat]
  or:     pip install ai4icore-exceptions
"""

from ai4icore_core.exceptions.handlers import register_exception_handlers  # noqa: F401
__all__ = ["register_exception_handlers"]
