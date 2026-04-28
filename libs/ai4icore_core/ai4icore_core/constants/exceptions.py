"""
BACKWARD COMPATIBILITY — re-exports from ai4icore_exceptions.

The canonical home for exceptions is now ai4icore_exceptions.
This file exists so existing 'from ai4icore_constants.exceptions import ...' continues to work.

Requires: pip install ai4icore-constants[compat]
  or:     pip install ai4icore-exceptions
"""

from ai4icore_core.exceptions.exceptions import *  # noqa: F401,F403
from ai4icore_core.exceptions.exceptions import __all__  # noqa: F401
