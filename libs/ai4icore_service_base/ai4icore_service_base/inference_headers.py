"""
Backwards-compatibility shim.

The canonical implementation lives in ``ai4icore_core.service_base.inference_headers``. This module re-exports
its public API so existing ``from ai4icore_<lib>... import ...`` continues
to work. New code should import from ``ai4icore_core.service_base.inference_headers`` directly.
"""
from ai4icore_core.service_base.inference_headers import *  # noqa: F401,F403

# Also propagate private symbols (e.g. helpers, module-level state) for full
# backwards compatibility with services that imported private names.
from importlib import import_module as _import_module
_real = _import_module("ai4icore_core.service_base.inference_headers")
globals().update({k: v for k, v in vars(_real).items() if not k.startswith("__")})
del _real, _import_module
