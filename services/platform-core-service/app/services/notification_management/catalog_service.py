"""Notification catalog reads.

The catalog GET is a join in code, not a serialiser over the table: each DB
row is decorated with its display name/description/detail line from
catalog_metadata.py, which the API never exposes for editing.
"""

from typing import List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification_management.config_notification_alert import (
    ConfigNotificationAlert,
)
from app.schemas.notification_management.catalog import NotificationCatalogItem
from app.services.notification_management.catalog_metadata import NOTIFICATION_METADATA


async def list_notification_catalog(session: AsyncSession) -> List[NotificationCatalogItem]:
    result = await session.execute(
        select(ConfigNotificationAlert).order_by(ConfigNotificationAlert.id)
    )
    rows = result.scalars().all()

    items = []
    for row in rows:
        meta = NOTIFICATION_METADATA.get(row.name)
        items.append(
            NotificationCatalogItem(
                name=row.name,
                display_name=meta.display_name if meta else row.name,
                description=meta.description if meta else "",
                type=row.type,
                module=row.module,
                channels=list(row.channels or []),
                is_enabled=row.is_enabled,
                recipient_roles=(row.config or {}).get("recipient_roles", {}),
            )
        )
    return items
