"""Async repository for the NotificationReceiver entity."""

from typing import List, Optional

from sqlalchemy import delete, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.alert_management.notification_receiver import NotificationReceiver


class NotificationReceiverRepository:
    """Persistence layer for `notification_receivers`."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    # ── Reads ──

    async def get_by_id(self, receiver_id: int) -> Optional[NotificationReceiver]:
        result = await self._db.execute(
            select(NotificationReceiver).where(NotificationReceiver.id == receiver_id)
        )
        return result.scalar_one_or_none()

    async def get_by_receiver_name(self, name: str) -> Optional[NotificationReceiver]:
        result = await self._db.execute(
            select(NotificationReceiver).where(
                NotificationReceiver.receiver_name == name
            )
        )
        return result.scalar_one_or_none()

    async def count(
        self,
        *,
        category: Optional[str] = None,
        severity: Optional[str] = None,
        enabled: Optional[bool] = None,
        tenant: Optional[str] = None,
    ) -> int:
        stmt = select(func.count(NotificationReceiver.id))
        if category is not None:
            stmt = stmt.where(NotificationReceiver.category == category)
        if severity is not None:
            stmt = stmt.where(NotificationReceiver.severity == severity)
        if enabled is not None:
            stmt = stmt.where(NotificationReceiver.enabled == enabled)
        if tenant is not None:
            stmt = stmt.where(NotificationReceiver.tenant == tenant)
        result = await self._db.execute(stmt)
        return int(result.scalar() or 0)

    async def list(
        self,
        *,
        category: Optional[str] = None,
        severity: Optional[str] = None,
        enabled: Optional[bool] = None,
        tenant: Optional[str] = None,
        offset: int = 0,
        limit: Optional[int] = None,
    ) -> List[NotificationReceiver]:
        stmt = select(NotificationReceiver)
        if category is not None:
            stmt = stmt.where(NotificationReceiver.category == category)
        if severity is not None:
            stmt = stmt.where(NotificationReceiver.severity == severity)
        if enabled is not None:
            stmt = stmt.where(NotificationReceiver.enabled == enabled)
        if tenant is not None:
            stmt = stmt.where(NotificationReceiver.tenant == tenant)
        stmt = stmt.order_by(desc(NotificationReceiver.created_at)).offset(offset)
        if limit is not None:
            stmt = stmt.limit(limit)
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def list_enabled(self) -> List[NotificationReceiver]:
        """Used by the sync service — only enabled receivers ship to Alertmanager."""
        result = await self._db.execute(
            select(NotificationReceiver)
            .where(NotificationReceiver.enabled.is_(True))
            .order_by(NotificationReceiver.receiver_name)
        )
        return list(result.scalars().all())

    # ── Writes ──

    async def add(self, receiver: NotificationReceiver) -> NotificationReceiver:
        self._db.add(receiver)
        await self._db.flush()
        return receiver

    async def apply_updates(
        self, instance: NotificationReceiver, data: dict
    ) -> NotificationReceiver:
        for key, value in data.items():
            setattr(instance, key, value)
        await self._db.flush()
        return instance

    async def delete_by_id(self, receiver_id: int) -> int:
        result = await self._db.execute(
            delete(NotificationReceiver).where(NotificationReceiver.id == receiver_id)
        )
        return int(result.rowcount or 0)

    async def commit(self) -> None:
        await self._db.commit()

    async def rollback(self) -> None:
        await self._db.rollback()
