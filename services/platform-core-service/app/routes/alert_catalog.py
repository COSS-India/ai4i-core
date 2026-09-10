"""Catalog PATCH — Adopter-facing, ADMIN only. One endpoint for both
NOTIFICATION-type and ALERT-type rows of configs_notification_alert,
addressed by the row's own ``id`` — the same id the GET returns — rather
than a caller-supplied type.

New module, deliberately separate from app.routes.alert: that file is the
unrelated Prometheus/Alertmanager-style alerting feature (definitions,
receivers, routing-rules, history) and is not touched here.

Reading either catalog is the single ``GET /catalog?type=`` endpoint in
app.routes.notification. This module's PATCH updates channels/recipient_roles
for any catalog row, plus thresholds for the 2 ALERT-type rows
(QUOTA_THRESHOLD, BUDGET_THRESHOLD) — thresholds only exist on those, so the
service rejects them for a NOTIFICATION-type row.
"""

from fastapi import APIRouter, Depends, Request

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.common import MessageMeta, error_responses
from app.schemas.notification_management.catalog import CatalogUpdate, UpdateCatalogResponse
from app.services.notification_management import catalog_service

router = APIRouter(
    tags=["Notifications & Alerts"],
)


@router.patch("/catalog/{id}", responses=error_responses(404))
async def update_catalog(
    id: int,
    payload: CatalogUpdate,
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> UpdateCatalogResponse:
    """Update one catalog row by id (NOTIFICATION or ALERT — whichever that
    id actually is): channels, recipient_roles and/or thresholds. Only the
    fields present in the body are changed — recipient_roles/thresholds are
    independent (recipient_roles is its own column; thresholds is the only
    key left in config) so setting one never disturbs the other. thresholds
    is rejected for a NOTIFICATION-type row. Within recipient_roles/
    thresholds, existing keys are never dropped or reset — a key omitted
    from the body keeps its current value."""
    updated_by = request.headers.get("X-User-Id")
    item = await catalog_service.update_catalog(session, id, payload, updated_by=updated_by)
    return UpdateCatalogResponse(
        success=True, data=item, meta=MessageMeta(message=f"'{item.name}' updated.")
    )
