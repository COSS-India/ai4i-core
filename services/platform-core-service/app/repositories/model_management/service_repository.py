"""
Async repository for the Service entity.
"""

from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple
from uuid import UUID

from sqlalchemy import String, and_, cast, delete, desc, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.models.model_management.model import Model, VersionStatus
from app.models.model_management.service import Service
from app.models.pay_per_use.ppu_tier import PPUTier


# flag_modified is only load-bearing for callers that mutate an
# already-loaded JSON dict in place (instance.col["x"] = y) rather than
# reassigning the column outright — apply_updates() below always does the
# latter (plain setattr), which SQLAlchemy's own change-tracking already
# picks up regardless of this set. Still kept in sync defensively so a
# future in-place-mutation caller doesn't silently fail to persist — the 5
# JSONB columns below were added for ULCA schema alignment.
_JSON_COLUMNS = frozenset({
    "health_status", "benchmarks",
    "inference_api_key", "inference_schema", "async_api_details",
    "supported_input_formats", "supported_output_formats",
})


class ServiceRepository:
    """Persistence layer for `services`."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    # ── Reads ──

    async def get_by_uuid(self, uuid: UUID) -> Optional[Service]:
        result = await self._db.execute(
            select(Service).where(
                Service.id == uuid,
                Service.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def get_by_service_id(self, service_id: str) -> Optional[Service]:
        result = await self._db.execute(
            select(Service).where(
                Service.service_id == service_id,
                Service.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def get_by_name(self, name: str) -> Optional[Service]:
        result = await self._db.execute(select(Service).where(Service.name == name))
        return result.scalar_one_or_none()

    async def count_services(
        self,
        *,
        task_types: Optional[List[str]] = None,
        is_published: Optional[bool] = None,
        created_by: Optional[str] = None,
    ) -> int:
        """Return the total number of services matching the given filters (no pagination)."""
        stmt = select(func.count(Service.id)).join(
            Model,
            and_(
                Model.model_id == Service.model_id,
                Model.version == Service.model_version,
            ),
        ).where(Service.deleted_at.is_(None))
        if task_types:
            stmt = stmt.where(Model.task["type"].astext.in_(task_types))
        if is_published is not None:
            stmt = stmt.where(Service.is_published == is_published)
        if created_by is not None:
            stmt = stmt.where(Service.created_by == created_by)
        result = await self._db.execute(stmt)
        return int(result.scalar() or 0)

    async def list_services(
        self,
        *,
        task_types: Optional[List[str]] = None,
        is_published: Optional[bool] = None,
        created_by: Optional[str] = None,
        offset: int = 0,
        limit: Optional[int] = None,
    ) -> List[Tuple[Service, Model]]:
        """Return (service, model) tuples."""
        stmt = (
            select(Service, Model)
            .join(
                Model,
                and_(
                    Model.model_id == Service.model_id,
                    Model.version == Service.model_version,
                ),
            )
            .where(Service.deleted_at.is_(None))
        )
        if task_types:
            stmt = stmt.where(Model.task["type"].astext.in_(task_types))
        if is_published is not None:
            stmt = stmt.where(Service.is_published == is_published)
        if created_by is not None:
            stmt = stmt.where(Service.created_by == created_by)
        stmt = stmt.order_by(desc(Service.is_published), desc(Service.created_at))
        stmt = stmt.offset(offset)
        if limit is not None:
            stmt = stmt.limit(limit)
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
            Service.deleted_at.is_(None),
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
            Service.deleted_at.is_(None),
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def get_tier_names_by_ids(self, tier_ids: List[str]) -> Dict[str, str]:
        """Return {tier_id_str: tier_name} for the given list of UUID strings."""
        if not tier_ids:
            return {}
        result = await self._db.execute(
            select(cast(PPUTier.id, String).label("id_str"), PPUTier.name)
            .where(cast(PPUTier.id, String).in_(tier_ids))
        )
        return {row.id_str: row.name for row in result.all()}

    async def get_names_and_models_by_service_ids(
        self, service_ids: List[str]
    ) -> Dict[str, Tuple[str, str, str]]:
        """Return {service_id: (name, model_id, model_name)} for the given
        service ids — but ONLY for services whose backing model is currently
        an ACTIVE version in the Registry.

        model_id/model_name are resolved via mm_models — mm_services.model_id
        is an opaque hash (sha256(f"{name}:{version}")[:32], see
        app/utils/hashing.py), not a human-readable model name on its own.
        Inner join, filtered to Model.version_status == ACTIVE: a service
        backed by a DEPRECATED or (hard-)deleted model is excluded from the
        result exactly like a service that doesn't exist, so callers that
        treat "missing from this dict" as "not a real, current entry" get
        both cases handled by the same check. mm_models has no soft-delete
        column — a deleted model's row is simply gone (see
        ModelService.delete_model), so "not in mm_models" already means
        "deleted" with no extra filter needed for that part.

        Excludes soft-deleted services. Used by the model-consumption
        metering endpoint to resolve, for each service_id grouped from
        Prometheus, the display name plus the underlying model's stable
        identity (model_id) and display name — model_id is the aggregation
        key across services that share a model, since it's immutable (model
        names can't be renamed — see ModelService.update_model) while a
        service's own name can be.
        """
        if not service_ids:
            return {}
        result = await self._db.execute(
            select(Service.service_id, Service.name, Model.model_id, Model.name.label("model_name"))
            .join(Model, Model.model_id == Service.model_id)
            .where(
                Service.service_id.in_(service_ids),
                Service.deleted_at.is_(None),
                Model.version_status == VersionStatus.ACTIVE,
            )
        )
        return {row.service_id: (row.name, row.model_id, row.model_name) for row in result.all()}

    # ── Writes ──

    async def add(self, service: Service) -> Service:
        self._db.add(service)
        await self._db.flush()
        return service

    async def clear_try_it_default(self, *, task_type: str, exclude_service_id: str) -> None:
        """Unset is_try_it_default on every other service of this task_type,
        keeping the "at most one default per task_type" invariant."""
        await self._db.execute(
            update(Service)
            .where(
                Service.task_type == task_type,
                Service.service_id != exclude_service_id,
                Service.is_try_it_default.is_(True),
            )
            .values(is_try_it_default=False)
        )
        await self._db.flush()

    async def apply_updates(self, instance: Service, data: dict) -> Service:
        for key, value in data.items():
            setattr(instance, key, value)
            if key in _JSON_COLUMNS:
                flag_modified(instance, key)
        await self._db.flush()
        return instance

    async def delete_by_uuid(self, uuid: UUID) -> int:
        now = datetime.now(timezone.utc)
        result = await self._db.execute(
            update(Service)
            .where(
                Service.id == uuid,
                Service.deleted_at.is_(None),
            )
            .values(deleted_at=now)
        )
        await self._db.flush()
        return int(result.rowcount or 0)

    async def delete_by_service_id(self, service_id: str) -> int:
        now = datetime.now(timezone.utc)
        result = await self._db.execute(
            update(Service)
            .where(
                Service.service_id == service_id,
                Service.deleted_at.is_(None),
            )
            .values(deleted_at=now)
        )
        await self._db.flush()
        return int(result.rowcount or 0)

    async def delete_unpublished_for_model_version(
        self, model_id: str, model_version: str
    ) -> int:
        now = datetime.now(timezone.utc)
        result = await self._db.execute(
            update(Service)
            .where(
                Service.model_id == model_id,
                Service.model_version == model_version,
                Service.is_published.is_(False),
                Service.deleted_at.is_(None),
            )
            .values(deleted_at=now)
        )
        await self._db.flush()
        return int(result.rowcount or 0)

    async def commit(self) -> None:
        await self._db.commit()

    async def rollback(self) -> None:
        await self._db.rollback()
