import json
from typing import Any, Dict, Optional
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query

from utils.health_status_cache import health_status_cache_key


router = APIRouter(prefix="/internal", tags=["Internal"])


@router.get(
    "/health-status",
    responses={
        404: {"description": "Health status not found in cache"},
        500: {"description": "Invalid health status cache entry"},
        503: {"description": "Redis not initialized"},
    },
)
async def get_health_status(
    service_id: Annotated[
        str,
        Query(..., min_length=1, description="Service identifier (service name)"),
    ],
) -> Dict[str, Any]:
    """
    Lightweight internal endpoint for routing decisions.

    Contract:
      - Pure cache read (Redis) for low latency; no DB reads, no live probes.
      - Returns health state and last-check timestamp for the given service_id.
    """
    from main import redis_client  # type: ignore

    if not redis_client:
        raise HTTPException(status_code=503, detail="Redis client not initialized")

    raw: Optional[bytes] = await redis_client.get(health_status_cache_key(service_id))
    if not raw:
        raise HTTPException(status_code=404, detail="Health status not found")

    try:
        text = raw.decode("utf-8") if isinstance(raw, (bytes, bytearray)) else str(raw)
        data = json.loads(text)
        # Ensure service_id is echoed back even if cache was written differently.
        if isinstance(data, dict) and "service_id" not in data:
            data["service_id"] = service_id
        return data
    except Exception:
        raise HTTPException(status_code=500, detail="Invalid health status cache entry")

