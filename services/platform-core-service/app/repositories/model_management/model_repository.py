"""
Async repository for the Model entity.

Pure data-access — no business rules, no HTTP concerns. Returns ORM
instances or scalars; the caller decides how to surface them.
"""

from dataclasses import dataclass, replace
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from sqlalchemy import asc, case, delete, desc, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.models.model_management.model import Model, VersionStatus
from app.models.model_management.service import Service
from app.utils.route_helpers import range_end_exclusive, range_start


@dataclass
class ModelListFilters:
    """Filters shared by ModelRepository.list_models / count_models."""

    name: Optional[str] = None
    version: Optional[str] = None
    task_types: Optional[List[str]] = None
    provider_name: Optional[str] = None
    version_status: Optional[str] = None
    created_from: "date | datetime | None" = None
    created_to: "date | datetime | None" = None
    created_by: Optional[str] = None
    include_deprecated: bool = True


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _contains(column, value: str):
    """Case-insensitive substring match with LIKE wildcards escaped."""
    return column.ilike(f"%{_escape_like(value)}%", escape="\\")



def _apply_model_filters(stmt, filters: ModelListFilters):
    """Single source of truth for model list/count WHERE clauses."""
    f = filters
    if f.task_types:
        stmt = stmt.where(
            func.lower(Model.task["type"].astext).in_([t.lower() for t in f.task_types])
        )
    if f.name:
        stmt = stmt.where(_contains(Model.name, f.name))
    if f.version:
        stmt = stmt.where(_contains(Model.version, f.version))
    if f.provider_name:
        stmt = stmt.where(_contains(Model.submitter["name"].astext, f.provider_name))
    if f.version_status == "active":
        stmt = stmt.where(Model.version_status == VersionStatus.ACTIVE)
    elif f.version_status == "deprecated":
        stmt = stmt.where(Model.version_status == VersionStatus.DEPRECATED)
    elif not f.include_deprecated:
        stmt = stmt.where(Model.version_status == VersionStatus.ACTIVE)
    if f.created_by is not None:
        stmt = stmt.where(Model.created_by == f.created_by)
    if f.created_from is not None:
        stmt = stmt.where(Model.created_at >= range_start(f.created_from))
    if f.created_to is not None:
        stmt = stmt.where(Model.created_at < range_end_exclusive(f.created_to))
    return stmt


def _sort_model_expressions() -> Dict[str, Any]:
    service_count = (
        select(func.count(Service.id))
        .where(Service.model_id == Model.model_id)
        .where(Service.deleted_at.is_(None))
        .scalar_subquery()
    )
    return {
        "name": func.lower(Model.name),
        "version": func.lower(Model.version),
        "taskType": func.lower(Model.task["type"].astext),
        "providerName": func.lower(Model.submitter["name"].astext),
        "status": Model.version_status,
        "createdAt": Model.created_at,
        "noOfServices": service_count,
    }


def _model_list_order_by(sort_by: Optional[str], sort_order: str) -> list:
    """ORDER BY terms. Default: newest first. Model.id is the tie-breaker."""
    if sort_by is None:
        priority = case((Model.version_status == VersionStatus.ACTIVE, 0), else_=1)
        return [desc(Model.created_at), priority, Model.model_id]
    exprs = _sort_model_expressions()
    if sort_by not in exprs:
        raise ValueError(f"Unsupported sort key: {sort_by}")
    expr = exprs[sort_by]
    ordered = desc(expr) if sort_order == "desc" else asc(expr)
    return [ordered.nulls_last(), Model.model_id]


def _merge_model_filters(
    filters: Optional[ModelListFilters],
    task_types: Optional[List[str]],
    include_deprecated: bool,
    version_status: Optional[str],
    created_by: Optional[str],
) -> ModelListFilters:
    """Fold legacy keyword params into a ModelListFilters for unified handling."""
    merged = replace(filters) if filters else ModelListFilters()
    if task_types:
        merged.task_types = task_types
    if version_status is not None:
        merged.version_status = version_status
    if not include_deprecated and merged.version_status is None:
        merged.include_deprecated = False
    if created_by is not None:
        merged.created_by = created_by
    return merged


# JSONB-backed columns — must call flag_modified() after in-place mutation.
_JSON_COLUMNS = frozenset(
    {
        "task",
        "languages",
        "domain",
        "inference_endpoint",
        "benchmarks",
        "submitter",
        "training_dataset",
    }
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
        filters: Optional[ModelListFilters] = None,
        task_types: Optional[List[str]] = None,
        version_status: Optional[str] = None,
        created_by: Optional[str] = None,
    ) -> int:
        """Return the total number of models matching the given filters (no pagination)."""
        merged = _merge_model_filters(
            filters, task_types, True, version_status, created_by
        )
        stmt = _apply_model_filters(select(func.count(Model.id)), merged)
        result = await self._db.execute(stmt)
        return int(result.scalar() or 0)

    async def count_models_by_task_type(self) -> Dict[str, int]:
        """Model versions per task type, lower-cased — count_models' grain
        and case-insensitive match, for every task type in one query."""
        task_type = func.lower(Model.task["type"].astext)
        stmt = select(task_type, func.count(Model.id)).group_by(task_type)
        result = await self._db.execute(stmt)
        return {t: int(n) for t, n in result.all() if t}

    async def get_model_names(
        self, model_ids: List[str], *, task_types: Optional[List[str]] = None
    ) -> Dict[str, str]:
        """Return {model_id: name} for the given ids — UNFILTERED on
        version_status: a DEPRECATED version is still live and can still be
        serving traffic (deprecating is the normal step before activating a
        replacement version — see get_names_and_models_by_service_ids for
        the identical reasoning), so it must not be treated as a ghost.
        mm_models has no soft-delete column, so a hard-deleted model_id is
        simply absent from this dict — that's the only case excluded on
        version_status grounds (see ModelService.delete_model).

        `task_types`, when given, additionally excludes any model_id whose
        registry row's task type isn't in the list — so a model_id serving
        LLM-chat traffic while registered under a different task type (a
        registry data error, not a deleted model) is ALSO absent from the
        returned dict, same as a genuinely deleted id. This matters for the
        model-consumption KPI pair: `registry_model_count` counts model
        VERSIONS filtered to task_types=["llm"] for `total_models`, and this
        method backs `active_models` (see model_breakdown) — without the
        same filter here, a non-llm-tagged model actively serving /chat
        traffic would count toward `active_models` but never toward
        `total_models`, breaking the "active is a subset of total"
        invariant those two KPIs are meant to hold.

        Used by the model-consumption metering endpoint to validate the
        Prometheus-native `model_id` label (see MetricsCollector, ai4i-core
        1.0.18+) against the current Registry state — a model_id with no
        entry here is a genuine ghost (deleted, stale/never-existent, or —
        with `task_types` given — registered under a different task type)
        and its traffic is excluded from the model-level rollup.
        """
        if not model_ids:
            return {}
        stmt = select(Model.model_id, Model.name).where(Model.model_id.in_(model_ids))
        if task_types:
            # Case-insensitive: this filter now runs with all 11
            # TaskTypeEnum values (previously always just ["llm"], where a
            # casing mismatch could never surface), and an exact JSONB
            # match against whatever case a row happens to be stored in
            # would silently ghost that model_id here while /api/v1/models
            # (TaskSpecLenient) still renders it normally — see
            # metering_service.py's model_breakdown for the ghost-drop
            # consequence.
            stmt = stmt.where(
                func.lower(Model.task["type"].astext).in_([t.lower() for t in task_types])
            )
        result = await self._db.execute(stmt)
        return {row.model_id: row.name for row in result.all()}

    async def list_models(
        self,
        *,
        filters: Optional[ModelListFilters] = None,
        sort_by: Optional[str] = None,
        sort_order: str = "asc",
        offset: int = 0,
        limit: Optional[int] = None,
        task_types: Optional[List[str]] = None,
        include_deprecated: bool = True,
        version_status: Optional[str] = None,
        created_by: Optional[str] = None,
    ) -> List[Model]:
        merged = _merge_model_filters(
            filters, task_types, include_deprecated, version_status, created_by
        )
        stmt = _apply_model_filters(select(Model), merged)
        stmt = stmt.order_by(*_model_list_order_by(sort_by, sort_order))
        stmt = stmt.offset(offset)
        if limit is not None:
            stmt = stmt.limit(limit)
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def get_service_counts_by_model_ids(
        self, model_ids: List[str]
    ) -> Dict[str, int]:
        """Return {model_id: service_count} for active (non-deleted) services."""
        if not model_ids:
            return {}
        stmt = (
            select(Service.model_id, func.count(Service.id).label("cnt"))
            .where(Service.model_id.in_(model_ids))
            .where(Service.deleted_at.is_(None))
            .group_by(Service.model_id)
        )
        result = await self._db.execute(stmt)
        return {row.model_id: row.cnt for row in result.all()}

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
