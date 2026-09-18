"""
PPU (Pay-Per-Use) utilities.

    configure_catalogue(...)   — install the catalogue client once, at startup
    get_catalogue()            — the process-wide catalogue client
    to_legacy_entry(entry)     — project a row into the scalar endpoint_pattern shape
    load_inference_types(app)  — await once in lifespan to populate app.state
    quota_guard                — FastAPI dependency, enforces budget/quota headers

The catalogue is read from platform-core's database via its Redis cache, an HTTP
endpoint, or a direct session, depending on what the service has. The bundled
``inference_types.yaml`` it replaced is gone, along with ``get_inference_types``
and ``get_inference_unit_map`` — use ``get_catalogue().get_all()`` and
``get_catalogue().get_unit_map()``.
"""

from .catalogue import (
    InferenceTypeCatalogue,
    configure_catalogue,
    get_catalogue,
    to_legacy_entry,
)
from .quota_guard import load_inference_types, quota_guard

__all__ = [
    "InferenceTypeCatalogue",
    "configure_catalogue",
    "get_catalogue",
    "to_legacy_entry",
    "load_inference_types",
    "quota_guard",
]
