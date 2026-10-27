"""Catalogue checks for an Application's ``service_fallbacks`` map.

Shape checks (blank ids, duplicates, a service listed as its own fallback)
already ran in the request schema (normalize_service_fallbacks). This module
checks every id against the core DB (``mm_services``, joined to ``mm_models``
for the task type): it must exist, be published and not deleted, be mapped to
the tenant's Tier (explicitly — a service with no Tier doesn't qualify, same
as the picker's GET /services?tier_id= list), and every fallback must share
its primary's task type.

Raw SQL over the platform-core session, same as tier_lookup / budget_usage —
auth-service has no ORM models for the core DB.
"""

from typing import Dict, List, Optional

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

_SERVICES_SQL = text(
    """
    SELECT s.service_id,
           lower(COALESCE(s.task_type, m.task->>'type')) AS task_type,
           s.is_published,
           s.deleted_at,
           s.tier_ids
    FROM   mm_services s
    LEFT JOIN mm_models m ON m.model_id = s.model_id AND m.version = s.model_version
    WHERE  s.service_id = ANY(:service_ids)
    """
)


def _reject(code: str, message: str, service_id: Optional[str] = None) -> HTTPException:
    detail = {"code": code, "message": message}
    if service_id:
        detail["service_id"] = service_id
    return HTTPException(status_code=422, detail=detail)


async def validate_service_fallbacks(
    service_fallbacks: Dict[str, List[str]],
    tier_id: Optional[str],
    platform_core_db: Optional[AsyncSession],
) -> None:
    """Raise 422 (or 503 when the catalogue can't be read) if the map is invalid.

    An empty map is always valid — it clears the config.
    """
    if not service_fallbacks:
        return
    if not tier_id:
        raise _reject(
            "NO_ACTIVE_TIER",
            "Service fallbacks need the Institution to be mapped to a Tier.",
        )
    if platform_core_db is None:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "SERVICE_CATALOGUE_UNAVAILABLE",
                "message": "Service fallbacks can't be validated right now. Try again later.",
            },
        )

    ids = sorted({sid for primary, fbs in service_fallbacks.items() for sid in [primary, *fbs]})
    rows = (await platform_core_db.execute(_SERVICES_SQL, {"service_ids": ids})).mappings().all()
    by_id = {row["service_id"]: row for row in rows}

    for sid in ids:
        row = by_id.get(sid)
        if row is None:
            raise _reject("SERVICE_NOT_FOUND", f"Service '{sid}' does not exist.", sid)
        if row["deleted_at"] is not None or not row["is_published"]:
            raise _reject("SERVICE_NOT_PUBLISHED", f"Service '{sid}' is not published.", sid)
        # Must be explicitly mapped to the Institution's Tier — a service with
        # no Tier isn't offered in the picker, so it isn't accepted here either.
        tier_ids = [str(t) for t in (row["tier_ids"] or [])]
        if str(tier_id) not in tier_ids:
            raise _reject(
                "SERVICE_NOT_IN_TIER", f"Service '{sid}' is not available in the Institution's Tier.", sid
            )

    for primary, fallbacks in service_fallbacks.items():
        primary_type = by_id[primary]["task_type"]
        for fb in fallbacks:
            if by_id[fb]["task_type"] != primary_type:
                raise _reject(
                    "TASK_TYPE_MISMATCH",
                    f"Fallback '{fb}' ({by_id[fb]['task_type']}) must have the same task type "
                    f"as '{primary}' ({primary_type}).",
                    fb,
                )
