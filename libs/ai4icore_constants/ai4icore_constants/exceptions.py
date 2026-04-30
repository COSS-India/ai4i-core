"""
BACKWARD COMPATIBILITY — re-exports from ai4icore_exceptions.

The canonical home for exceptions is now ai4icore_exceptions.
This file exists so existing 'from ai4icore_constants.exceptions import ...' continues to work.

Requires: pip install ai4icore-constants[compat]
  or:     pip install ai4icore-exceptions
"""

try:
    from ai4icore_exceptions.exceptions import *  # noqa: F401,F403
    from ai4icore_exceptions.exceptions import __all__  # noqa: F401
except ImportError:
    raise ImportError(
        "ai4icore_constants.exceptions has moved to ai4icore_exceptions.\n"
        "Either:\n"
        "  1. pip install ai4icore-exceptions   (and update imports to 'from ai4icore_exceptions import ...')\n"
        "  2. pip install ai4icore-constants[compat]   (to keep using this import path)\n"
    )
