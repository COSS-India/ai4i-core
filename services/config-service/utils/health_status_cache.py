import json
import logging
from datetime import datetime, timezone
from typing import Any, Iterable

logger = logging.getLogger(__name__)


def health_status_cache_key(service_id: str) -> str:
    return f"internal:health-status:{service_id}"


def compute_health_state(*, total_instances: int, healthy_instances: int) -> str:
    """
    Map instance counts to a routing-oriented health state:
      - healthy: all instances healthy (and at least 1 instance exists)
      - degraded: some healthy, some unhealthy
      - unhealthy: instances exist but none are healthy
      - unknown: no instances were observed (e.g., registry empty/unavailable)
    """
    if total_instances <= 0:
        return "unknown"
    if healthy_instances <= 0:
        return "unhealthy"
    if healthy_instances >= total_instances:
        return "healthy"
    return "degraded"


async def cache_health_snapshots(
    redis_conn: Any,
    *,
    results: Iterable[Any],
    health_check_interval: int,
) -> None:
    """
    Store a lightweight per-service health snapshot in Redis for internal consumers.

    Contract:
      - no DB reads
      - no live probes
      - safe to call inside periodic monitor loop
    """
    if not redis_conn:
        return

    cache_ttl_seconds = max(int(health_check_interval) * 2, 30)
    now = datetime.now(timezone.utc).isoformat()

    for r in results or []:
        try:
            total_instances = int(getattr(r, "total_instances", 0) or 0)
            healthy_instances = int(getattr(r, "healthy_instances", 0) or 0)
            state = compute_health_state(
                total_instances=total_instances,
                healthy_instances=healthy_instances,
            )

            service_id = getattr(r, "service_name", None) or ""
            if not service_id:
                continue

            payload = {
                "service_id": service_id,
                "state": state,
                "last_check": now,
                "total_instances": total_instances,
                "healthy_instances": healthy_instances,
            }

            await redis_conn.set(
                health_status_cache_key(service_id),
                json.dumps(payload),
                ex=cache_ttl_seconds,
            )
        except Exception as exc:
            logger.debug(
                "Failed caching health snapshot for %s: %s",
                getattr(r, "service_name", "(unknown)"),
                exc,
            )

