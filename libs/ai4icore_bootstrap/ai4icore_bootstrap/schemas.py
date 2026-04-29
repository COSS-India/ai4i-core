"""
Backwards-compatibility shim.

The canonical implementation lives in ``ai4icore_core.bootstrap.schemas``. This module re-exports
its public API so existing ``from ai4icore_<lib>... import ...`` continues
to work. New code should import from ``ai4icore_core.bootstrap.schemas`` directly.
"""
from ai4icore_core.bootstrap.schemas import *  # noqa: F401,F403

# Also propagate private symbols (e.g. helpers, module-level state) for full
# backwards compatibility with services that imported private names.
from importlib import import_module as _import_module
_real = _import_module("ai4icore_core.bootstrap.schemas")
globals().update({k: v for k, v in vars(_real).items() if not k.startswith("__")})
del _real, _import_module
