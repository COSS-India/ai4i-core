"""Catalog PATCH — Adopter-facing, ADMIN only. One endpoint for both
NOTIFICATION-type and ALERT-type rows of configs_notification_alert,
addressed by the row's own ``name`` — unique, stable and meaningful,
unlike the bigserial ``id`` (whose values depend on seed history and can
differ across environments).

New module, deliberately separate from app.routes.alert: that file is the
unrelated Prometheus/Alertmanager-style alerting feature (definitions,
receivers, routing-rules, history) and is not touched here.

Reading either catalog is the single ``GET /notification-alerts/catalog?type=``
endpoint in app.routes.notification. This module's PATCH updates
channels/scope for any catalog row, plus thresholds for the 2 ALERT-type
rows (QUOTA_THRESHOLD, BUDGET_THRESHOLD) — thresholds only exist on those,
so the service rejects them for a NOTIFICATION-type row. The row's own
stored ``type`` decides what's valid, never something the caller asserts.
"""

from fastapi import APIRouter, Depends, Request

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.exceptions import InsufficientPermissionsError
from app.core.permissions import is_admin
from app.schemas.common import MessageMeta, error_responses
from app.schemas.notification_management.catalog import CatalogUpdate, UpdateCatalogResponse
from app.services.notification_management import catalog_service

router = APIRouter(
    prefix="/notification-alerts",
    tags=["Notifications & Alerts"],
)


@router.patch("/catalog/{name}", responses=error_responses(404))
async def update_catalog(
    name: str,
    payload: CatalogUpdate,
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> UpdateCatalogResponse:
    """Update one catalog row by name (NOTIFICATION or ALERT — whichever
    that name actually is): channels, scope and/or thresholds. Only the
    fields present in the body are changed. thresholds is rejected for a
    NOTIFICATION-type row. Adopter Admin only."""
    if not is_admin(request):
        raise InsufficientPermissionsError()
    updated_by = request.headers.get("X-User-Id")
    item = await catalog_service.update_catalog(session, name, payload, updated_by=updated_by)
    return UpdateCatalogResponse(
        success=True, data=item, meta=MessageMeta(message=f"'{item.name}' updated.")
    )
