"""Notification/alert catalog read endpoint — Adopter-facing, ADMIN only.

One endpoint for both catalogs: ``type`` selects which rows of
configs_notification_alert come back (NOTIFICATION or ALERT), same response
shape either way. The alert catalog's PATCH lives separately in
app.routes.alert_catalog — this module is read-only.
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.enums.notification_management import NotificationType
from app.schemas.notification_management.catalog import CatalogResponse, ListCatalogResponse
from app.services.notification_management import catalog_service

router = APIRouter(
    tags=["Notifications & Alerts"],
)


@router.get("/catalog", response_model=ListCatalogResponse, response_model_exclude_none=True)
async def list_catalog(
    catalog_type: NotificationType = Query(..., alias="type"),
    session: AsyncSession = Depends(get_db),
) -> ListCatalogResponse:
    """List the notification or alert catalog: the seeded rows of the
    requested ``?type=``, each decorated with its display name/description
    and its currently saved recipient roles (and thresholds, for ALERT
    rows)."""
    items = await catalog_service.list_catalog(session, catalog_type)
    return ListCatalogResponse(success=True, data=CatalogResponse(items=items))
