"""Monitoring alert catalog PATCH — Adopter-facing, ADMIN only.

Separate from app.routes.alert_catalog (the metering NOTIFICATION/ALERT
PATCH) because monitoring alerts have their own model: no scope, Email
only, recipients are Adopter Admin and/or Moderator, thresholds are
value + unit bands. Reading the monitoring catalog is the shared
``GET /notification-alerts/catalog?type=MONITORING`` in
app.routes.notification.
"""

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.exceptions import InsufficientPermissionsError
from app.core.permissions import is_admin
from app.schemas.common import MessageMeta, error_responses
from app.schemas.notification_management.catalog import (
    MonitoringCatalogUpdate,
    UpdateMonitoringCatalogResponse,
)
from app.services.notification_management import monitoring_catalog_service

router = APIRouter(
    prefix="/notification-alerts",
    tags=["Notifications & Alerts"],
)


@router.patch("/monitoring-catalog/{name}", responses=error_responses(404))
async def update_monitoring_catalog(
    name: str,
    payload: MonitoringCatalogUpdate,
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> UpdateMonitoringCatalogResponse:
    """Update one monitoring alert by name: recipient roles (ADMIN /
    MODERATOR — the users holding them are resolved when an alert is sent)
    and/or threshold bands. Only the fields present in the body are
    changed. Adopter Admin only."""
    if not is_admin(request):
        raise InsufficientPermissionsError()
    updated_by = request.headers.get("X-User-Id")
    item = await monitoring_catalog_service.update_monitoring_catalog(
        session, name, payload, updated_by=updated_by
    )
    return UpdateMonitoringCatalogResponse(
        success=True, data=item, meta=MessageMeta(message=f"'{item.name}' updated.")
    )
