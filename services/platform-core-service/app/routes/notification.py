"""Notification/alert catalog read endpoint — Adopter-facing, ADMIN only.

One endpoint for both catalogs: ``type`` selects which rows of
configs_notification_alert come back (NOTIFICATION or ALERT), same response
shape either way. The alert catalog's PATCH lives separately in
app.routes.alert_catalog — this module is read-only.
"""

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.exceptions import InsufficientPermissionsError
from app.core.permissions import is_admin
from app.schemas.enums.notification_management import NotificationType
from app.schemas.notification_management.catalog import CatalogResponse, ListCatalogResponse
from app.services.notification_management import catalog_service

router = APIRouter(
    prefix="/notification-alerts",
    tags=["Notifications & Alerts"],
)


@router.get("/catalog", response_model=ListCatalogResponse, response_model_exclude_none=True)
async def list_catalog(
    request: Request,
    catalog_type: NotificationType = Query(..., alias="type"),
    session: AsyncSession = Depends(get_db),
) -> ListCatalogResponse:
    """List the notification or alert catalog: the seeded rows of the
    requested ``?type=``, each decorated with its display name/description,
    its scope (GLOBAL/INSTITUTION) and its currently saved channels/
    thresholds (thresholds only for ALERT rows). Adopter Admin only."""
    if not is_admin(request):
        raise InsufficientPermissionsError()
    items = await catalog_service.list_catalog(session, catalog_type)
    return ListCatalogResponse(success=True, data=CatalogResponse(items=items))
