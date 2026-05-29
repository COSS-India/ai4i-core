"""Routing-rule domain service.

CRUD plus a bulk timing-update used by ``PATCH /alerts/routing-rules/timing``,
which applies group_wait / group_interval / repeat_interval to all rules
matching a (category, severity[, alert_type, priority]) filter.

Rewritten from alert-management-service/alert_management.py:1956-2745.
``organization`` dropped; sync triggering is the route layer's job.
"""

from __future__ import annotations

from typing import List

from app.core.exceptions import DuplicateEntityError, EntityNotFoundError, ValidationError
from app.models.alert_management.routing_rule import RoutingRule
from app.repositories.alert_management.routing_rule_repository import RoutingRuleRepository
from app.schemas.alert_management.routing_rule import (
    RoutingRuleCreate,
    RoutingRuleResponse,
    RoutingRuleTimingUpdate,
    RoutingRuleUpdate,
)


class RoutingRuleService:
    """Business logic for routing rules."""

    def __init__(self, repo: RoutingRuleRepository) -> None:
        self._repo = repo

    # ── Reads ──

    async def get(self, rule_id: int) -> RoutingRuleResponse:
        rule = await self._repo.get_by_id(rule_id)
        if not rule:
            raise EntityNotFoundError(f"Routing rule {rule_id} not found")
        return self._to_response(rule)

    async def list(self) -> List[RoutingRuleResponse]:
        return [self._to_response(r) for r in await self._repo.list()]

    # ── Writes ──

    async def create(self, data: RoutingRuleCreate) -> RoutingRuleResponse:
        if await self._repo.get_by_rule_name(data.rule_name):
            raise DuplicateEntityError(
                f"Routing rule with name '{data.rule_name}' already exists."
            )
        rule = RoutingRule(
            rule_name=data.rule_name,
            receiver_id=data.receiver_id,
            match_severity=data.match_severity,
            match_category=data.match_category,
            match_alert_type=data.match_alert_type,
            match_alert_names=data.match_alert_names,
            match_tenant_id=data.match_tenant_id,
            group_by=data.group_by,
            group_wait=data.group_wait,
            group_interval=data.group_interval,
            repeat_interval=data.repeat_interval,
            continue_routing=data.continue_routing,
            priority=data.priority,
        )
        await self._repo.add(rule)
        await self._repo.commit()
        refreshed = await self._repo.get_by_id(rule.id)
        return self._to_response(refreshed)

    async def update(
        self, rule_id: int, data: RoutingRuleUpdate
    ) -> RoutingRuleResponse:
        rule = await self._repo.get_by_id(rule_id)
        if not rule:
            raise EntityNotFoundError(f"Routing rule {rule_id} not found")

        # Guard rule_name uniqueness if it's changing.
        if data.rule_name is not None and data.rule_name != rule.rule_name:
            clash = await self._repo.get_by_rule_name(data.rule_name)
            if clash and clash.id != rule_id:
                raise DuplicateEntityError(
                    f"Routing rule with name '{data.rule_name}' already exists."
                )

        updates = {
            field: getattr(data, field)
            for field in (
                "rule_name",
                "receiver_id",
                "match_severity",
                "match_category",
                "match_alert_type",
                "match_alert_names",
                "match_tenant_id",
                "group_by",
                "group_wait",
                "group_interval",
                "repeat_interval",
                "continue_routing",
                "priority",
                "enabled",
            )
            if getattr(data, field) is not None
        }
        await self._repo.apply_updates(rule, updates)
        await self._repo.commit()
        refreshed = await self._repo.get_by_id(rule_id)
        return self._to_response(refreshed)

    async def delete(self, rule_id: int) -> None:
        rule = await self._repo.get_by_id(rule_id)
        if not rule:
            raise EntityNotFoundError(f"Routing rule {rule_id} not found")
        await self._repo.delete_by_id(rule_id)
        await self._repo.commit()

    async def update_timing(self, data: RoutingRuleTimingUpdate) -> int:
        """Bulk-apply timing params to all rules matching the filter. Returns affected count."""
        if not any([data.group_wait, data.group_interval, data.repeat_interval]):
            raise ValidationError(
                "At least one of group_wait, group_interval, repeat_interval must be provided"
            )
        affected = await self._repo.bulk_update_timing(
            match_category=data.category,
            match_severity=data.severity,
            match_alert_type=data.alert_type,
            priority=data.priority,
            group_wait=data.group_wait,
            group_interval=data.group_interval,
            repeat_interval=data.repeat_interval,
        )
        await self._repo.commit()
        return affected

    # ── Mapping ──

    @staticmethod
    def _to_response(rule: RoutingRule) -> RoutingRuleResponse:
        return RoutingRuleResponse(
            id=rule.id,
            rule_name=rule.rule_name,
            receiver_id=rule.receiver_id,
            match_severity=rule.match_severity,
            match_category=rule.match_category,
            match_alert_type=rule.match_alert_type,
            match_alert_names=rule.match_alert_names,
            match_tenant_id=rule.match_tenant_id,
            group_by=rule.group_by or [],
            group_wait=rule.group_wait,
            group_interval=rule.group_interval,
            repeat_interval=rule.repeat_interval,
            continue_routing=bool(rule.continue_routing),
            priority=rule.priority,
            enabled=bool(rule.enabled),
            created_at=rule.created_at,
            updated_at=rule.updated_at,
        )
