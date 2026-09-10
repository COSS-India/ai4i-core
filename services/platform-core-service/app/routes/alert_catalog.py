"""Alert catalog PATCH — Adopter-facing, ADMIN only.

New module, deliberately separate from app.routes.alert: that file is the
unrelated Prometheus/Alertmanager-style alerting feature (definitions,
receivers, routing-rules, history) and is not touched here.

This is the Notifications-and-Alerts-design alert catalog: the 2 ALERT-type
rows of configs_notification_alert (QUOTA_THRESHOLD, BUDGET_THRESHOLD).
Reading either catalog is the single ``GET /catalog?type=`` endpoint in
app.routes.notification — this module only adds the alert-specific PATCH
(recipient-role/threshold legality validation that a NOTIFICATION-type row
doesn't need).
"""

from fastapi import APIRouter, Depends

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.common import MessageMeta, error_responses
from app.schemas.notification_management.catalog import CatalogUpdate, UpdateCatalogResponse
from app.services.notification_management import catalog_service

router = APIRouter(
    prefix="/alerts",
    tags=["Notifications & Alerts"],
)


@router.patch("/catalog/{name}", responses=error_responses(404))
async def update_alert_catalog(
    name: str,
    payload: CatalogUpdate,
    session: AsyncSession = Depends(get_db),
) -> UpdateCatalogResponse:
    """Update one alert catalog row: channels, recipient_roles and/or
    thresholds. Only the fields present in the body are changed —
    recipient_roles/thresholds are independent (recipient_roles is its own
    column; thresholds is the only key left in config) so setting one never
    disturbs the other."""
    item = await catalog_service.update_alert_catalog(session, name, payload)
    return UpdateCatalogResponse(
        success=True, data=item, meta=MessageMeta(message=f"Alert '{name}' updated.")
    )
