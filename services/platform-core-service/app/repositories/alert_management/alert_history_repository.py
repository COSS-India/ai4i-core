"""Async repository for the AlertHistory entity (append-only audit log)."""

from datetime import datetime
from typing import Iterable, List, Optional, Tuple

from sqlalchemy import desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.alert_management.alert_history import AlertHistory


class AlertHistoryRepository:
    """Persistence layer for `alert_history`.

    Reads are paginated with filters; writes are append-only batches coming
    from the Alertmanager webhook.
    """

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    # ── Writes ──

    async def add(self, entry: AlertHistory) -> AlertHistory:
        self._db.add(entry)
        await self._db.flush()
        return entry

    async def bulk_add(self, entries: Iterable[AlertHistory]) -> int:
        """Append a batch from one webhook payload. Returns inserted-row count."""
        entries_list = list(entries)
        if not entries_list:
            return 0
        self._db.add_all(entries_list)
        await self._db.flush()
        return len(entries_list)

    # ── Reads ──

    async def count(
        self,
        *,
        category: Optional[str] = None,
        severity: Optional[str] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        search: Optional[str] = None,
    ) -> int:
        stmt = select(func.count(AlertHistory.id))
        stmt = self._apply_filters(stmt, category, severity, date_from, date_to, search)
        result = await self._db.execute(stmt)
        return int(result.scalar() or 0)

    async def list(
        self,
        *,
        category: Optional[str] = None,
        severity: Optional[str] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        search: Optional[str] = None,
        offset: int = 0,
        limit: int = 50,
    ) -> Tuple[List[AlertHistory], int]:
        """Returns (items, total_count). Total is the same filter set sans pagination."""
        base_stmt = select(AlertHistory)
        base_stmt = self._apply_filters(base_stmt, category, severity, date_from, date_to, search)

        # Total count first
        total = await self.count(
            category=category,
            severity=severity,
            date_from=date_from,
            date_to=date_to,
            search=search,
        )

        stmt = base_stmt.order_by(desc(AlertHistory.triggered_at)).offset(offset).limit(limit)
        result = await self._db.execute(stmt)
        return list(result.scalars().all()), total

    # ── Helpers ──

    @staticmethod
    def _apply_filters(
        stmt,
        category: Optional[str],
        severity: Optional[str],
        date_from: Optional[datetime],
        date_to: Optional[datetime],
        search: Optional[str],
    ):
        if category is not None:
            stmt = stmt.where(AlertHistory.category == category.lower())
        if severity is not None:
            stmt = stmt.where(AlertHistory.severity == severity.lower())
        if date_from is not None:
            stmt = stmt.where(AlertHistory.triggered_at >= date_from)
        if date_to is not None:
            stmt = stmt.where(AlertHistory.triggered_at <= date_to)
        if search:
            pattern = f"%{search}%"
            stmt = stmt.where(
                or_(
                    AlertHistory.alert_name.ilike(pattern),
                    AlertHistory.notified_display.ilike(pattern),
                )
            )
        return stmt

    async def commit(self) -> None:
        await self._db.commit()

    async def rollback(self) -> None:
        await self._db.rollback()
