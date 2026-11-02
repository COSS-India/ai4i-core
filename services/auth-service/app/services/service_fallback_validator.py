"""Catalogue checks for an Application's ``service_fallbacks`` map.

Every id must be a published, non-deleted service mapped to the Institution's
Tier, and every fallback must share its primary's task type. Raw SQL over the
platform-core session (``mm_services`` joined to ``mm_models`` for the task
type), same as tier_lookup / budget_usage — auth-service has no ORM models
for the core DB.
"""

from typing import Dict, List, Optional

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

_SERVICES_SQL = text(
    "SELECT s.service_id, lower(COALESCE(s.task_type, m.task->>'type')) AS task_type,"
    "       s.is_published, s.deleted_at, s.tier_ids"
    "  FROM mm_services s"
    "  LEFT JOIN mm_models m ON m.model_id = s.model_id AND m.version = s.model_version"
    " WHERE s.service_id = ANY(:service_ids)"
)


def _reject(code: str, message: str, service_id: Optional[str] = None) -> HTTPException:
    detail = {"code": code, "message": message}
    if service_id:
        detail["service_id"] = service_id
    return HTTPException(status_code=422, detail=detail)


def _check_service(sid: str, row, tier_id: str) -> None:
    if row is None:
        raise _reject("SERVICE_NOT_FOUND", f"Service '{sid}' does not exist.", sid)
    if row["deleted_at"] is not None or not row["is_published"]:
        raise _reject("SERVICE_NOT_PUBLISHED", f"Service '{sid}' is not published.", sid)
    if str(tier_id) not in [str(t) for t in (row["tier_ids"] or [])]:
        raise _reject("SERVICE_NOT_IN_TIER", f"Service '{sid}' is not available in the Institution's Tier.", sid)


async def validate_service_fallbacks(
    service_fallbacks: Dict[str, List[str]],
    tier_id: Optional[str],
    platform_core_db: Optional[AsyncSession],
) -> None:
    """Raise 422 (503 when the catalogue can't be read) if the map is invalid; {} is always valid."""
    if not service_fallbacks:
        return
    if not tier_id:
        raise _reject("NO_ACTIVE_TIER", "Service fallbacks need the Institution to be mapped to a Tier.")
    if platform_core_db is None:
        raise HTTPException(
            status_code=503,
            detail={"code": "SERVICE_CATALOGUE_UNAVAILABLE", "message": "Service fallbacks can't be validated right now."},
        )

    ids = sorted({sid for primary, fallbacks in service_fallbacks.items() for sid in (primary, *fallbacks)})
    rows = (await platform_core_db.execute(_SERVICES_SQL, {"service_ids": ids})).mappings().all()
    by_id = {row["service_id"]: row for row in rows}
    for sid in ids:
        _check_service(sid, by_id.get(sid), tier_id)
    for primary, fallbacks in service_fallbacks.items():
        for fb in fallbacks:
            if by_id[fb]["task_type"] != by_id[primary]["task_type"]:
                raise _reject("TASK_TYPE_MISMATCH", f"Fallback '{fb}' must have the same task type as '{primary}'.", fb)
