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
_cache: list[dict] | None = None

# Unified endpoint that accepts any task_type in the request body.
# It has no entry in the YAML (one path serves all types), so quota
# enforcement must inspect the body field rather than matching the path.
_UNIFIED_INFERENCE_PATH = "/api/v1/inference"


def get_inference_types() -> list[dict]:
    """Return the raw inference type list from the bundled YAML (cached after first read)."""
    global _cache
    if _cache is None:
        with _YAML_PATH.open() as f:
            _cache = yaml.safe_load(f)["inference_types"]
    return _cache


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
        logger.error("Failed to load inference_types.yaml — service cannot start: %s", exc)
        raise


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
        exhausted_set = {t.strip() for t in exhausted_types_raw.split(",") if t.strip()}

        if request.url.path == _UNIFIED_INFERENCE_PATH:
            # Unified endpoint: task_type lives in the request body, not the path.
            # Body bytes are cached by Starlette after the first read, so the
            # downstream route handler sees the same bytes untouched.
            try:
                body = await request.json()
                task_type = str(body.get("task_type", "")).lower()
            except Exception:
                task_type = ""
            if task_type and task_type in exhausted_set:
                raise HTTPException(
                    status_code=429,
                    detail={
                        "error": "quota_exhausted",
                        "message": f"Quota Exhausted for: {task_type}",
                    },
                )
        else:
            pattern_map: dict = getattr(request.app.state, "inference_type_map", {})
            for exhausted_type in exhausted_set:
                pattern = pattern_map.get(exhausted_type)
                if pattern and request.url.path.startswith(pattern):
                    raise HTTPException(
                        status_code=429,
                        detail={
                            "error": "quota_exhausted",
                            "message": f"Quota Exhausted for: {exhausted_type}",
                        },
                    )
