"""
Async repository for the Model entity.

Pure data-access — no business rules, no HTTP concerns. Returns ORM
instances or scalars; the caller decides how to surface them.
"""

from typing import List, Optional, Tuple
from uuid import UUID

from sqlalchemy import case, delete, desc, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.models.model_management.model import Model, VersionStatus


# JSONB-backed columns — must call flag_modified() after in-place mutation.
_JSON_COLUMNS = frozenset(
    {"task", "languages", "domain", "inference_endpoint", "benchmarks", "submitter"}
)


class ModelRepository:
    """Persistence layer for `models`."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    # ── Reads ──

    async def get_by_uuid(self, uuid: UUID) -> Optional[Model]:
        result = await self._db.execute(select(Model).where(Model.id == uuid))
        return result.scalar_one_or_none()

    async def get_by_id_version(
        self, model_id: str, version: str
    ) -> Optional[Model]:
        result = await self._db.execute(
            select(Model).where(Model.model_id == model_id, Model.version == version)
        )
        return result.scalar_one_or_none()

    async def get_by_name_version(self, name: str, version: str) -> Optional[Model]:
        result = await self._db.execute(
            select(Model).where(Model.name == name, Model.version == version)
        )
        return result.scalar_one_or_none()

    async def get_default_version(self, model_id: str) -> Optional[Model]:
        """Return the latest ACTIVE version, falling back to latest DEPRECATED."""
        priority = case(
            (Model.version_status == VersionStatus.ACTIVE, 0),
            else_=1,
        )
        result = await self._db.execute(
            select(Model)
            .where(Model.model_id == model_id)
            .order_by(priority, desc(Model.created_at))
        )
        return result.scalars().first()

    async def count_active_versions(
        self, name: str, exclude_version: Optional[str] = None
    ) -> int:
        """Count ACTIVE versions for *name*, optionally excluding one version."""
        stmt = select(func.count(Model.id)).where(
            Model.name == name, Model.version_status == VersionStatus.ACTIVE
        )
        if exclude_version:
            stmt = stmt.where(Model.version != exclude_version)
        result = await self._db.execute(stmt)
        return int(result.scalar() or 0)

    async def count_models(
        self,
        *,
        task_type: Optional[str] = None,
        version_status: Optional[str] = None,
        model_name: Optional[str] = None,
        created_by: Optional[str] = None,
    ) -> int:
        """Return the total number of models matching the given filters (no pagination)."""
        stmt = select(func.count(Model.id))
        if task_type:
            stmt = stmt.where(Model.task["type"].astext == task_type)
        if model_name:
            stmt = stmt.where(func.lower(Model.name) == func.lower(model_name))
        if version_status == "active":
            stmt = stmt.where(Model.version_status == VersionStatus.ACTIVE)
        elif version_status == "deprecated":
            stmt = stmt.where(Model.version_status == VersionStatus.DEPRECATED)
        if created_by is not None:
            stmt = stmt.where(Model.created_by == created_by)
        result = await self._db.execute(stmt)
        return int(result.scalar() or 0)

    async def list_models(
        self,
        *,
        task_type: Optional[str] = None,
        include_deprecated: bool = True,
        version_status: Optional[str] = None,
        model_name: Optional[str] = None,
        created_by: Optional[str] = None,
        offset: int = 0,
        limit: Optional[int] = None,
    ) -> List[Model]:
        priority = case(
            (Model.version_status == VersionStatus.ACTIVE, 0),
            else_=1,
        )
        stmt = select(Model)
        if task_type:
            stmt = stmt.where(Model.task["type"].astext == task_type)
        if model_name:
            stmt = stmt.where(func.lower(Model.name) == func.lower(model_name))
        # version_status takes precedence over include_deprecated
        if version_status == "active":
            stmt = stmt.where(Model.version_status == VersionStatus.ACTIVE)
        elif version_status == "deprecated":
            stmt = stmt.where(Model.version_status == VersionStatus.DEPRECATED)
        elif not include_deprecated:
            stmt = stmt.where(Model.version_status == VersionStatus.ACTIVE)
        if created_by is not None:
            stmt = stmt.where(Model.created_by == created_by)
        stmt = stmt.order_by(desc(Model.created_at), priority, Model.model_id)
        stmt = stmt.offset(offset)
        if limit is not None:
            stmt = stmt.limit(limit)
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    # ── Writes ──

    async def add(self, model: Model) -> Model:
        self._db.add(model)
        await self._db.flush()
        return model

    async def apply_updates(self, instance: Model, data: dict) -> Model:
        """Apply *data* to an ORM instance, flagging JSONB mutations."""
        for key, value in data.items():
            setattr(instance, key, value)
            if key in _JSON_COLUMNS:
                flag_modified(instance, key)
        await self._db.flush()
        return instance

    async def refresh(self, instance: Model) -> Model:
        """Refresh an instance from DB to avoid expired-attribute lazy loads."""
        await self._db.refresh(instance)
        return instance

    async def get_by_model_id(self, model_id: str) -> Optional[Model]:
        result = await self._db.execute(
            select(Model).where(Model.model_id == model_id)
        )
        return result.scalar_one_or_none()

    async def delete_by_uuid(self, uuid: UUID) -> int:
        result = await self._db.execute(delete(Model).where(Model.id == uuid))
        return int(result.rowcount or 0)

    async def delete_by_model_id(self, model_id: str) -> int:
        result = await self._db.execute(
            delete(Model).where(Model.model_id == model_id)
        )
        return int(result.rowcount or 0)

    async def commit(self) -> None:
        await self._db.commit()

    async def rollback(self) -> None:
        await self._db.rollback()
