"""Alert catalog endpoints — Adopter-facing, ADMIN only.

New module, deliberately separate from app.routes.alert: that file is the
unrelated Prometheus/Alertmanager-style alerting feature (definitions,
receivers, routing-rules, history) and is not touched here.

This is the Notifications-and-Alerts-design alert catalog: the 2 ALERT-type
rows of configs_notification_alert (QUOTA_THRESHOLD, BUDGET_THRESHOLD),
read via GET and configured via PATCH — the alert-side counterpart of
app.routes.notification's GET /notifications/catalog.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.common import MessageMeta, error_responses
from app.schemas.notification_management.catalog import (
    AlertCatalogResponse,
    AlertCatalogUpdate,
    ListAlertCatalogResponse,
    UpdateAlertCatalogResponse,
)
from app.services.notification_management import catalog_service

router = APIRouter(
    prefix="/alerts",
    tags=["Alerts - Catalog"],
)


@router.get("/catalog", response_model=ListAlertCatalogResponse)
async def list_alert_catalog(
    session: AsyncSession = Depends(get_db),
) -> ListAlertCatalogResponse:
    """List the alert catalog: the seeded ALERT-type rows (Quota Threshold,
    Budget Threshold), each decorated with its display name/description and
    its currently saved recipient roles and threshold bands."""
    items = await catalog_service.list_alert_catalog(session)
    return ListAlertCatalogResponse(success=True, data=AlertCatalogResponse(alerts=items))


@router.patch("/catalog/{name}", responses=error_responses(404))
async def update_alert_catalog(
    name: str,
    payload: AlertCatalogUpdate,
    session: AsyncSession = Depends(get_db),
) -> UpdateAlertCatalogResponse:
    """Update one alert catalog row: is_enabled, channels, recipient_roles
    and/or thresholds. Only the fields present in the body are changed —
    recipient_roles/thresholds each replace their own config key wholesale
    without disturbing the other."""
    item = await catalog_service.update_alert_catalog(session, name, payload)
    return UpdateAlertCatalogResponse(
        success=True, data=item, meta=MessageMeta(message=f"Alert '{name}' updated.")
    )
