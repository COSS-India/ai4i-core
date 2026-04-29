"""
Backwards-compatibility shim.

The canonical implementation lives in ``ai4icore_core.bootstrap``. This package re-exports
its public API so existing ``from ai4icore_<lib> import ...`` continues
to work. New code should import from ``ai4icore_core.bootstrap`` directly.
"""
from ai4icore_core.bootstrap import *  # noqa: F401,F403

# Also propagate private symbols (e.g. helpers) for full backwards compatibility.
from importlib import import_module as _import_module
_real = _import_module("ai4icore_core.bootstrap")
globals().update({k: v for k, v in vars(_real).items() if not k.startswith("__")})
del _real, _import_module
