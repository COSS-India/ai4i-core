"""
PPU quota guard — enforces X-Budget-Exhausted and X-Quota-Exhausted headers
before any inference request is processed.

Usage in a service:

    from ai4i_core.ppu import load_inference_types, quota_guard

    # In lifespan:
    load_inference_types(app)

    # On the router (applies to every route automatically):
    app.include_router(router, dependencies=[Depends(quota_guard)])
"""

import logging
from pathlib import Path

import yaml
from fastapi import FastAPI, HTTPException, Request

logger = logging.getLogger(__name__)

_YAML_PATH = Path(__file__).parent / "inference_types.yaml"


def get_inference_types() -> list[dict]:
    """Return the raw inference type list from the bundled YAML."""
    with _YAML_PATH.open() as f:
        return yaml.safe_load(f)["inference_types"]


def load_inference_types(app: FastAPI) -> None:
    """
    Read inference_types.yaml once at startup and store a name→endpoint_pattern
    map in app.state.inference_type_map.

    Call this inside the FastAPI lifespan before yielding.
    """
    try:
        items = get_inference_types()
        app.state.inference_type_map = {
            item["name"]: item["endpoint_pattern"] for item in items
        }
        logger.info(
            "Inference type map loaded: %d types.", len(app.state.inference_type_map)
        )
    except Exception as exc:
        logger.warning("Failed to load inference type map: %s", exc)
        app.state.inference_type_map = {}


async def quota_guard(request: Request) -> None:
    """
    FastAPI dependency — enforces PPU budget and quota headers injected by the
    gateway before the request reaches any inference handler.

    X-Budget-Exhausted: true
        → HTTP 429, budget fully exhausted for this tenant.

    X-Quota-Exhausted: <type>[,<type>...]   (e.g. "nmt" or "nmt,asr")
        → Splits on comma, resolves each type's endpoint_pattern from app.state.
        → If the incoming request path matches any exhausted type's pattern → HTTP 429.
        → If none match → the request does not require those types, proceed.
    """
    if request.headers.get("X-Budget-Exhausted") == "true":
        raise HTTPException(
            status_code=429,
            detail={"error": "budget_exhausted", "message": "Budget Exhausted"},
        )

    exhausted_types_raw = request.headers.get("X-Quota-Exhausted")
    if exhausted_types_raw:
        pattern_map: dict = getattr(request.app.state, "inference_type_map", {})
        for exhausted_type in (t.strip() for t in exhausted_types_raw.split(",") if t.strip()):
            pattern = pattern_map.get(exhausted_type)
            if pattern and request.url.path == pattern:
                raise HTTPException(
                    status_code=429,
                    detail={
                        "error": "quota_exhausted",
                        "message": f"Quota Exhausted for: {exhausted_type}",
                    },
                )
