"""
Async repository for the Service entity.
"""

from typing import List, Optional, Tuple
from uuid import UUID

from sqlalchemy import and_, delete, desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.models.model import Model
from app.models.service import Service


_JSON_COLUMNS = frozenset({"health_status", "benchmarks", "policy"})


class ServiceRepository:
    """Persistence layer for `services`."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    # ── Reads ──

    async def get_by_uuid(self, uuid: UUID) -> Optional[Service]:
        result = await self._db.execute(select(Service).where(Service.id == uuid))
        return result.scalar_one_or_none()

    async def get_by_service_id(self, service_id: str) -> Optional[Service]:
        result = await self._db.execute(
            select(Service).where(Service.service_id == service_id)
        )
        return result.scalar_one_or_none()

    async def get_by_name(self, name: str) -> Optional[Service]:
        result = await self._db.execute(select(Service).where(Service.name == name))
        return result.scalar_one_or_none()

    async def list_services(
        self,
        *,
        task_type: Optional[str] = None,
        is_published: Optional[bool] = None,
        created_by: Optional[str] = None,
    ) -> List[Tuple[Service, Model]]:
        """Return (service, model) tuples joined on (model_id, model_version)."""
        stmt = select(Service, Model).join(
            Model,
            and_(
                Model.model_id == Service.model_id,
                Model.version == Service.model_version,
            ),
        )
        if task_type:
            stmt = stmt.where(Model.task["type"].astext == task_type)
        if is_published is not None:
            stmt = stmt.where(Service.is_published == is_published)
        if created_by is not None:
            stmt = stmt.where(Service.created_by == created_by)
        stmt = stmt.order_by(desc(Service.is_published), desc(Service.created_at))
        result = await self._db.execute(stmt)
        return [(svc, model) for svc, model in result.all()]

    async def list_published_for_model_version(
        self, model_id: str, model_version: str
    ) -> List[str]:
        """Return service_ids of published services for (model_id, model_version)."""
        stmt = select(Service.service_id).where(
            Service.model_id == model_id,
            Service.model_version == model_version,
            Service.is_published.is_(True),
        )
        result = await self._db.execute(stmt)
        return [row[0] for row in result.fetchall()]

    async def list_unpublished_for_model_version(
        self, model_id: str, model_version: str
    ) -> List[Service]:
        stmt = select(Service).where(
            Service.model_id == model_id,
            Service.model_version == model_version,
            Service.is_published.is_(False),
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    # ── Writes ──

    async def add(self, service: Service) -> Service:
        self._db.add(service)
        await self._db.flush()
        return service

    async def apply_updates(self, instance: Service, data: dict) -> Service:
        for key, value in data.items():
            setattr(instance, key, value)
            if key in _JSON_COLUMNS:
                flag_modified(instance, key)
        await self._db.flush()
        return instance

    async def delete_by_uuid(self, uuid: UUID) -> int:
        result = await self._db.execute(delete(Service).where(Service.id == uuid))
        return int(result.rowcount or 0)

    async def delete_unpublished_for_model_version(
        self, model_id: str, model_version: str
    ) -> int:
        result = await self._db.execute(
            delete(Service).where(
                Service.model_id == model_id,
                Service.model_version == model_version,
                Service.is_published.is_(False),
            )
        )
        return int(result.rowcount or 0)

    async def commit(self) -> None:
        await self._db.commit()

    async def rollback(self) -> None:
        await self._db.rollback()
