"""
BACKWARD COMPATIBILITY — re-exports from ai4icore_exceptions.
New code should import from ai4icore_exceptions directly.

Requires: pip install ai4icore-constants[compat]
  or:     pip install ai4icore-exceptions
"""

try:
    from ai4icore_exceptions.responses import success_response, error_response  # noqa: F401
    __all__ = ["success_response", "error_response"]
except ImportError:
    raise ImportError(
        "ai4icore_constants.responses has moved to ai4icore_exceptions.\n"
        "Either:\n"
        "  1. pip install ai4icore-exceptions   (and use 'from ai4icore_exceptions import success_response')\n"
        "  2. pip install ai4icore-constants[compat]\n"
    )
