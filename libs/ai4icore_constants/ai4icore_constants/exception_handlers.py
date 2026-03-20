"""
BACKWARD COMPATIBILITY — re-exports from ai4icore_exceptions.
New code should import from ai4icore_exceptions directly.

Requires: pip install ai4icore-constants[compat]
  or:     pip install ai4icore-exceptions
"""

try:
    from ai4icore_exceptions.handlers import register_exception_handlers  # noqa: F401
    __all__ = ["register_exception_handlers"]
except ImportError:
    raise ImportError(
        "ai4icore_constants.exception_handlers has moved to ai4icore_exceptions.\n"
        "Either:\n"
        "  1. pip install ai4icore-exceptions   (and use 'from ai4icore_exceptions import register_exception_handlers')\n"
        "  2. pip install ai4icore-constants[compat]\n"
    )
