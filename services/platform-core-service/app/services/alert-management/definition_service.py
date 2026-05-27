"""Alert-definition domain service.

CRUD + enable-toggle for alert rules. Builds PromQL from the request (via
``app.utils.promql_builder``) and persists through ``AlertDefinitionRepository``.

Rewritten from alert-management-service/alert_management.py:1014-1621 — the
asyncpg/raw-SQL paths become SQLAlchemy-repo calls; ``organization`` and audit
logging are dropped; ``HTTPException`` becomes platform-core's typed exceptions.

This service does NOT trigger config sync — the route layer calls
``SyncService.sync_configuration`` after a successful write so the service
stays free of cross-service coupling.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.core.exceptions import DuplicateEntityError, EntityNotFoundError
from app.models.alert_management.alert_definition import AlertDefinition
from app.repositories.alert_management.alert_definition_repository import (
    AlertDefinitionRepository,
)
from app.schemas.alert_management.alert_definition import (
    AlertDefinitionCreate,
    AlertDefinitionResponse,
    AlertDefinitionUpdate,
)
from app.utils.promql_builder import (
    SIGNALS_CONFIG,
    _normalize_tasks,
    alert_type_to_display,
    build_promql_from_signal_config,
    build_promql_from_threshold,
    inject_endpoint_into_promql,
)

_INFRA_SIGNAL_DISPLAY = {
    "cpu_utilization": "CPU",
    "memory_utilization": "Memory",
    "disk_utilization": "Disk",
}


class AlertDefinitionService:
    """Business logic for alert definitions."""

    def __init__(self, repo: AlertDefinitionRepository) -> None:
        self._repo = repo

    # ── Reads ──

    async def get(self, definition_id: int) -> AlertDefinitionResponse:
        definition = await self._repo.get_by_id(definition_id)
        if not definition:
            raise EntityNotFoundError(f"Alert definition {definition_id} not found")
        return self._to_response(definition)

    async def list(self, *, enabled_only: bool = False) -> List[AlertDefinitionResponse]:
        definitions = (
            await self._repo.list_enabled()
            if enabled_only
            else await self._repo.list()
        )
        return [self._to_response(d) for d in definitions]

    # ── Writes ──

    async def create(self, data: AlertDefinitionCreate) -> AlertDefinitionResponse:
        existing = await self._repo.get_by_name(data.name.strip())
        if existing:
            raise DuplicateEntityError(
                f"An alert definition with name '{data.name}' already exists "
                f"(id={existing.id}). Alert names must be globally unique."
            )

        promql_expr, alert_type_display, signal_fields = self._build_promql_for_create(data)
        tasks_list = _normalize_tasks(data.service)

        definition = AlertDefinition(
            name=data.name.strip(),
            description=data.description,
            promql_expr=promql_expr,
            threshold_value=data.threshold_value,
            threshold_unit=data.threshold_unit,
            category=data.category,
            severity=data.severity,
            urgency=data.urgency,
            alert_type=alert_type_display,
            sub_category=signal_fields.get("sub_category"),
            signal=signal_fields.get("signal"),
            signal_metric=signal_fields.get("signal_metric"),
            condition_operator=signal_fields.get("condition_operator"),
            scope=data.scope,
            service=tasks_list or None,
            evaluation_interval=data.evaluation_interval,
            for_duration=data.for_duration,
            enabled=data.enabled if data.enabled is not None else True,
        )
        await self._repo.add(definition)
        if data.annotations:
            await self._repo.replace_annotations(
                definition, [(a.key, a.value) for a in data.annotations]
            )
        await self._repo.commit()

        refreshed = await self._repo.get_by_id(definition.id)
        return self._to_response(refreshed)

    async def update(
        self, definition_id: int, data: AlertDefinitionUpdate
    ) -> AlertDefinitionResponse:
        definition = await self._repo.get_by_id(definition_id)
        if not definition:
            raise EntityNotFoundError(f"Alert definition {definition_id} not found")

        updates = self._build_update_dict(definition, data)
        await self._repo.apply_updates(definition, updates)

        if data.annotations is not None:
            await self._repo.replace_annotations(
                definition, [(a.key, a.value) for a in data.annotations]
            )
        await self._repo.commit()

        refreshed = await self._repo.get_by_id(definition_id)
        return self._to_response(refreshed)

    async def delete(self, definition_id: int) -> None:
        definition = await self._repo.get_by_id(definition_id)
        if not definition:
            raise EntityNotFoundError(f"Alert definition {definition_id} not found")
        await self._repo.delete_by_id(definition_id)
        await self._repo.commit()

    async def set_enabled(self, definition_id: int, enabled: bool) -> AlertDefinitionResponse:
        definition = await self._repo.get_by_id(definition_id)
        if not definition:
            raise EntityNotFoundError(f"Alert definition {definition_id} not found")
        await self._repo.apply_updates(definition, {"enabled": enabled})
        await self._repo.commit()
        refreshed = await self._repo.get_by_id(definition_id)
        return self._to_response(refreshed)

    # ── PromQL build helpers ──

    def _build_promql_for_create(self, data: AlertDefinitionCreate):
        """Returns (promql_expr, alert_type_display, signal_fields dict)."""
        use_signal_config = all(
            [data.sub_category, data.signal, data.signal_metric, data.condition_operator]
        )
        tasks_list = _normalize_tasks(data.service)

        if use_signal_config:
            promql = build_promql_from_signal_config(
                category=data.category,
                sub_category=data.sub_category,
                signal=data.signal,
                signal_metric=data.signal_metric,
                condition_operator=data.condition_operator,
                threshold_value=data.threshold_value,
                threshold_unit=data.threshold_unit,
            )
            if tasks_list:
                promql = inject_endpoint_into_promql(promql, tasks_list)
            alert_type_display = self._signal_to_display(data.signal, data.category)
            signal_fields = {
                "sub_category": (data.sub_category or "").strip() or None,
                "signal": (data.signal or "").strip() or None,
                "signal_metric": (data.signal_metric or "").strip() or None,
                "condition_operator": (data.condition_operator or "").strip() or None,
            }
        else:
            promql = build_promql_from_threshold(
                category=data.category,
                alert_type=data.alert_type,
                threshold_value=data.threshold_value,
                threshold_unit=data.threshold_unit,
            )
            if tasks_list:
                promql = inject_endpoint_into_promql(promql, tasks_list)
            alert_type_display = alert_type_to_display(data.alert_type, data.category)
            signal_fields = {}

        return promql, alert_type_display, signal_fields

    def _build_update_dict(
        self, existing: AlertDefinition, data: AlertDefinitionUpdate
    ) -> Dict[str, Any]:
        """Compute the column updates for a PATCH, rebuilding PromQL when needed."""
        updates: Dict[str, Any] = {}

        # Effective values (new value or existing).
        effective_services = (
            data.service if data.service is not None else (existing.service or [])
        )
        eff_sub = data.sub_category if data.sub_category is not None else existing.sub_category
        eff_signal = data.signal if data.signal is not None else existing.signal
        eff_metric = data.signal_metric if data.signal_metric is not None else existing.signal_metric
        eff_op = data.condition_operator if data.condition_operator is not None else existing.condition_operator
        use_signal_path = all([eff_sub, eff_signal, eff_metric, eff_op])

        threshold_or_type_changed = any(
            v is not None
            for v in (data.threshold_value, data.threshold_unit, data.alert_type, data.category)
        )
        signal_path_changed = any(
            v is not None
            for v in (data.sub_category, data.signal, data.signal_metric, data.condition_operator)
        )
        service_changed = data.service is not None

        if threshold_or_type_changed or service_changed or signal_path_changed:
            category = data.category if data.category is not None else existing.category
            thresh_val = (
                data.threshold_value if data.threshold_value is not None else existing.threshold_value
            )
            thresh_unit = (
                data.threshold_unit if data.threshold_unit is not None else existing.threshold_unit
            )
            tasks_list = _normalize_tasks(effective_services)

            if use_signal_path and thresh_val is not None and thresh_unit is not None:
                promql = build_promql_from_signal_config(
                    category=category,
                    sub_category=eff_sub,
                    signal=eff_signal,
                    signal_metric=eff_metric,
                    condition_operator=eff_op,
                    threshold_value=float(thresh_val),
                    threshold_unit=thresh_unit,
                )
                if tasks_list:
                    promql = inject_endpoint_into_promql(promql, tasks_list)
                updates["promql_expr"] = promql
                updates["alert_type"] = self._signal_to_display(eff_signal, category)
            elif not use_signal_path:
                alert_type = data.alert_type if data.alert_type is not None else existing.alert_type
                if thresh_val is not None and thresh_unit is not None and alert_type:
                    promql = build_promql_from_threshold(
                        category=category,
                        alert_type=alert_type,
                        threshold_value=float(thresh_val),
                        threshold_unit=thresh_unit,
                    )
                    if tasks_list:
                        promql = inject_endpoint_into_promql(promql, tasks_list)
                    updates["promql_expr"] = promql

        # Plain field updates.
        for field in (
            "description",
            "threshold_value",
            "threshold_unit",
            "category",
            "severity",
            "urgency",
            "alert_type",
            "sub_category",
            "signal",
            "signal_metric",
            "condition_operator",
            "scope",
            "evaluation_interval",
            "for_duration",
            "enabled",
        ):
            value = getattr(data, field)
            if value is not None:
                updates.setdefault(field, value)
        if data.service is not None:
            updates["service"] = _normalize_tasks(data.service) or None

        return updates

    @staticmethod
    def _signal_to_display(signal: Optional[str], category: Optional[str]) -> Optional[str]:
        sig_key = (signal or "").strip().lower().replace(" ", "_")
        if (category or "").lower() == "infrastructure" and sig_key in _INFRA_SIGNAL_DISPLAY:
            return _INFRA_SIGNAL_DISPLAY[sig_key]
        return SIGNALS_CONFIG.get(sig_key, {}).get("label") or signal

    # ── Mapping ──

    @staticmethod
    def _to_response(definition: AlertDefinition) -> AlertDefinitionResponse:
        annotations = [
            {"key": a.annotation_key, "value": a.annotation_value}
            for a in (definition.annotations or [])
        ]
        return AlertDefinitionResponse(
            id=definition.id,
            name=definition.name,
            description=definition.description,
            promql_expr=definition.promql_expr,
            threshold_value=definition.threshold_value,
            threshold_unit=definition.threshold_unit,
            category=definition.category,
            severity=definition.severity,
            urgency=definition.urgency,
            alert_type=definition.alert_type,
            sub_category=definition.sub_category,
            signal=definition.signal,
            signal_metric=definition.signal_metric,
            condition_operator=definition.condition_operator,
            scope=definition.scope,
            service=definition.service or None,
            evaluation_interval=definition.evaluation_interval,
            for_duration=definition.for_duration,
            enabled=bool(definition.enabled),
            created_at=definition.created_at,
            updated_at=definition.updated_at,
            annotations=annotations,
        )
