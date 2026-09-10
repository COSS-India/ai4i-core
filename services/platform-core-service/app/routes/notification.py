"""Notification catalog endpoints — Adopter-facing, ADMIN only."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.notification_management.catalog import (
    ListNotificationCatalogResponse,
    NotificationCatalogResponse,
)
from app.services.notification_management import catalog_service

router = APIRouter(
    prefix="/notifications",
    tags=["Notifications"],
)


@router.get("/catalog", response_model=ListNotificationCatalogResponse)
async def list_notification_catalog(
    session: AsyncSession = Depends(get_db),
) -> ListNotificationCatalogResponse:
    """List the notification catalog: the seeded notification types, each
    decorated with its display name/description and its currently saved
    recipient roles (empty until an Adopter Admin configures it)."""
    items = await catalog_service.list_notification_catalog(session)
    return ListNotificationCatalogResponse(
        success=True, data=NotificationCatalogResponse(notifications=items)
    )
