"""
Async repository for the AlertDefinition entity (and its child AlertAnnotations).

Pure data-access — no business rules, no HTTP concerns. Returns ORM instances
or scalars; the caller decides how to surface them.
"""

from typing import Iterable, List, Optional, Tuple

from sqlalchemy import delete, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.alert_management.alert_definition import (
    AlertAnnotation,
    AlertDefinition,
)


class AlertDefinitionRepository:
    """Persistence layer for `alert_definitions` (+ annotations child table)."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    # ── Reads ──

    async def get_by_id(self, definition_id: int) -> Optional[AlertDefinition]:
        result = await self._db.execute(
            select(AlertDefinition)
            .options(selectinload(AlertDefinition.annotations))
            .where(AlertDefinition.id == definition_id)
        )
        return result.scalar_one_or_none()

    async def get_by_name(self, name: str) -> Optional[AlertDefinition]:
        result = await self._db.execute(
            select(AlertDefinition).where(AlertDefinition.name == name)
        )
        return result.scalar_one_or_none()

    async def count(
        self,
        *,
        category: Optional[str] = None,
        severity: Optional[str] = None,
        enabled: Optional[bool] = None,
        alert_type: Optional[str] = None,
    ) -> int:
        stmt = select(func.count(AlertDefinition.id))
        if category is not None:
            stmt = stmt.where(AlertDefinition.category == category)
        if severity is not None:
            stmt = stmt.where(AlertDefinition.severity == severity)
        if enabled is not None:
            stmt = stmt.where(AlertDefinition.enabled == enabled)
        if alert_type is not None:
            stmt = stmt.where(AlertDefinition.alert_type == alert_type)
        result = await self._db.execute(stmt)
        return int(result.scalar() or 0)

    async def list(
        self,
        *,
        category: Optional[str] = None,
        severity: Optional[str] = None,
        enabled: Optional[bool] = None,
        alert_type: Optional[str] = None,
        offset: int = 0,
        limit: Optional[int] = None,
    ) -> List[AlertDefinition]:
        stmt = select(AlertDefinition).options(selectinload(AlertDefinition.annotations))
        if category is not None:
            stmt = stmt.where(AlertDefinition.category == category)
        if severity is not None:
            stmt = stmt.where(AlertDefinition.severity == severity)
        if enabled is not None:
            stmt = stmt.where(AlertDefinition.enabled == enabled)
        if alert_type is not None:
            stmt = stmt.where(AlertDefinition.alert_type == alert_type)
        stmt = stmt.order_by(desc(AlertDefinition.created_at)).offset(offset)
        if limit is not None:
            stmt = stmt.limit(limit)
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def list_enabled(self) -> List[AlertDefinition]:
        """Used by the sync service — only enabled definitions ship to Prometheus."""
        result = await self._db.execute(
            select(AlertDefinition)
            .options(selectinload(AlertDefinition.annotations))
            .where(AlertDefinition.enabled.is_(True))
            .order_by(AlertDefinition.name)
        )
        return list(result.scalars().all())

    # ── Writes ──

    async def add(self, definition: AlertDefinition) -> AlertDefinition:
        self._db.add(definition)
        await self._db.flush()
        return definition

    async def apply_updates(
        self, instance: AlertDefinition, data: dict
    ) -> AlertDefinition:
        for key, value in data.items():
            setattr(instance, key, value)
        await self._db.flush()
        return instance

    async def delete_by_id(self, definition_id: int) -> int:
        result = await self._db.execute(
            delete(AlertDefinition).where(AlertDefinition.id == definition_id)
        )
        return int(result.rowcount or 0)

    # ── Annotations (child table — atomic replace pattern) ──

    async def replace_annotations(
        self,
        definition: AlertDefinition,
        annotations: Iterable[Tuple[str, str]],
    ) -> None:
        """Replace all annotations for *definition* with the given (key, value) pairs.

        Uses delete + insert because the source service treated annotations as
        a small bounded set; concurrent updates aren't expected.
        """
        await self._db.execute(
            delete(AlertAnnotation).where(
                AlertAnnotation.alert_definition_id == definition.id
            )
        )
        for key, value in annotations:
            self._db.add(
                AlertAnnotation(
                    alert_definition_id=definition.id,
                    annotation_key=key,
                    annotation_value=value,
                )
            )
        await self._db.flush()

    async def commit(self) -> None:
        await self._db.commit()

    async def rollback(self) -> None:
        await self._db.rollback()
