"""Catalog PATCH — Adopter-facing, ADMIN only. One endpoint for both
NOTIFICATION-type and ALERT-type rows of configs_notification_alert,
selected by the same required ``?type=`` query param the GET uses.

New module, deliberately separate from app.routes.alert: that file is the
unrelated Prometheus/Alertmanager-style alerting feature (definitions,
receivers, routing-rules, history) and is not touched here.

Reading either catalog is the single ``GET /catalog?type=`` endpoint in
app.routes.notification. This module's PATCH updates channels/recipient_roles
for any catalog row by name, plus thresholds for the 2 ALERT-type rows
(QUOTA_THRESHOLD, BUDGET_THRESHOLD) — thresholds only exist on those, so the
service rejects them when ``type=NOTIFICATION``.
"""

from fastapi import APIRouter, Depends, Query

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.common import MessageMeta, error_responses
from app.schemas.enums.notification_management import NotificationType
from app.schemas.notification_management.catalog import CatalogUpdate, UpdateCatalogResponse
from app.services.notification_management import catalog_service

router = APIRouter(
    tags=["Notifications & Alerts"],
)


@router.patch("/catalog/{name}", responses=error_responses(404))
async def update_catalog(
    name: str,
    payload: CatalogUpdate,
    catalog_type: NotificationType = Query(..., alias="type"),
    session: AsyncSession = Depends(get_db),
) -> UpdateCatalogResponse:
    """Update one catalog row (NOTIFICATION or ALERT, per ``?type=``):
    channels, recipient_roles and/or thresholds. Only the fields present in
    the body are changed — recipient_roles/thresholds are independent
    (recipient_roles is its own column; thresholds is the only key left in
    config) so setting one never disturbs the other. thresholds is rejected
    when ``type=NOTIFICATION``. Within recipient_roles/thresholds, existing
    keys are never dropped — a key omitted from the body is kept and simply
    defaults to False."""
    item = await catalog_service.update_catalog(session, name, catalog_type, payload)
    return UpdateCatalogResponse(
        success=True, data=item, meta=MessageMeta(message=f"'{name}' updated.")
    )
