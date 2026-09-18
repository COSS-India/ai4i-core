"""
PPU quota guard — enforces X-Budget-Exhausted and X-Quota-Exhausted headers
before any inference request is processed.

Usage in a service:

    from ai4i_core.ppu import configure_catalogue, load_inference_types, quota_guard

    # In lifespan, after the catalogue transport is available:
    configure_catalogue(redis_factory=get_redis_client)
    await load_inference_types(app)

    # On the router (applies to every route automatically):
    app.include_router(router, dependencies=[Depends(quota_guard)])

The path→type map now comes from the database-backed catalogue rather than a
bundled YAML, so a type an admin adds at runtime is enforceable without a
release. That is the whole point of the change: the YAML could only be updated
by publishing this package and redeploying every service pinned to it.
"""

import logging

from fastapi import FastAPI, HTTPException, Request

from .catalogue import get_catalogue

logger = logging.getLogger(__name__)

# Unified endpoint that accepts any task_type in the request body.
# It has no catalogue entry (one path serves every type), so quota enforcement
# must inspect the body field rather than matching the path.
_UNIFIED_INFERENCE_PATH = "/api/v1/inference"


async def load_inference_types(app: FastAPI) -> None:
    """
    Warm the catalogue and store a name→endpoint_pattern map in
    ``app.state.inference_type_map``.

    Call this inside the FastAPI lifespan, after ``configure_catalogue``.

    Unlike the YAML version this never raises: the catalogue is a network
    resource now, and a service must still boot when it is briefly unreachable.
    ``quota_guard`` reads an empty map as "no per-service quota to enforce",
    which is the same thing an unmatched path has always meant — it degrades to
    letting requests through, never to rejecting them.
    """
    try:
        items = await get_catalogue().get_all()
        app.state.inference_type_map = {
            item["name"]: (item.get("endpoint_patterns") or [""])[0]
            for item in items
        }
        logger.info(
            "Inference type map loaded: %d types.", len(app.state.inference_type_map)
        )
    except Exception as exc:
        app.state.inference_type_map = {}
        logger.error(
            "Failed to load the inference type catalogue; per-service quota "
            "enforcement is disabled until it is reachable: %s", exc
        )


async def quota_guard(request: Request) -> None:
    """
    FastAPI dependency — enforces PPU budget and quota headers injected by the
    gateway before the request reaches any inference handler.

    X-Budget-Exhausted: true
        → HTTP 429, budget fully exhausted for this tenant.

    X-Quota-Exhausted: true | false
    X-Quota-Exhausted-Services: <type>[,<type>...]   (e.g. "asr" or "llm,asr")
        → When true: reads exhausted type names from X-Quota-Exhausted-Services.
        → If the incoming request's type matches any exhausted type → HTTP 429.
        → If none match → the request type is not exhausted, proceed.
    """
    if request.headers.get("X-Budget-Exhausted") == "true":
        raise HTTPException(
            status_code=429,
            detail={"error": "budget_exhausted", "message": "Budget Exhausted"},
        )

    if request.headers.get("X-Quota-Exhausted") == "true":
        services_raw = request.headers.get("X-Quota-Exhausted-Services", "")
        exhausted_set = {t.strip() for t in services_raw.split(",") if t.strip()}

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
