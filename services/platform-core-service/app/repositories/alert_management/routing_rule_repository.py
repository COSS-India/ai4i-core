"""Async repository for the RoutingRule entity."""

from typing import List, Optional

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.alert_management.notification_receiver import NotificationReceiver
from app.models.alert_management.routing_rule import RoutingRule


class RoutingRuleRepository:
    """Persistence layer for `routing_rules`."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    # ── Reads ──

    async def get_by_id(self, rule_id: int) -> Optional[RoutingRule]:
        result = await self._db.execute(select(RoutingRule).where(RoutingRule.id == rule_id))
        return result.scalar_one_or_none()

    async def get_by_rule_name(self, rule_name: str) -> Optional[RoutingRule]:
        result = await self._db.execute(
            select(RoutingRule).where(RoutingRule.rule_name == rule_name)
        )
        return result.scalar_one_or_none()

    async def count(
        self,
        *,
        match_category: Optional[str] = None,
        match_severity: Optional[str] = None,
        match_alert_type: Optional[str] = None,
        enabled: Optional[bool] = None,
    ) -> int:
        stmt = select(func.count(RoutingRule.id))
        if match_category is not None:
            stmt = stmt.where(RoutingRule.match_category == match_category)
        if match_severity is not None:
            stmt = stmt.where(RoutingRule.match_severity == match_severity)
        if match_alert_type is not None:
            stmt = stmt.where(RoutingRule.match_alert_type == match_alert_type)
        if enabled is not None:
            stmt = stmt.where(RoutingRule.enabled == enabled)
        result = await self._db.execute(stmt)
        return int(result.scalar() or 0)

    async def list(
        self,
        *,
        match_category: Optional[str] = None,
        match_severity: Optional[str] = None,
        match_alert_type: Optional[str] = None,
        enabled: Optional[bool] = None,
        offset: int = 0,
        limit: Optional[int] = None,
    ) -> List[RoutingRule]:
        stmt = select(RoutingRule)
        if match_category is not None:
            stmt = stmt.where(RoutingRule.match_category == match_category)
        if match_severity is not None:
            stmt = stmt.where(RoutingRule.match_severity == match_severity)
        if match_alert_type is not None:
            stmt = stmt.where(RoutingRule.match_alert_type == match_alert_type)
        if enabled is not None:
            stmt = stmt.where(RoutingRule.enabled == enabled)
        stmt = stmt.order_by(RoutingRule.priority, RoutingRule.rule_name).offset(offset)
        if limit is not None:
            stmt = stmt.limit(limit)
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def list_enabled(self) -> List[RoutingRule]:
        """Used by the sync service — only enabled rules ship to Alertmanager."""
        result = await self._db.execute(
            select(RoutingRule)
            .where(RoutingRule.enabled.is_(True))
            .order_by(RoutingRule.priority, RoutingRule.rule_name)
        )
        return list(result.scalars().all())

    async def list_matching_for_timing_update(
        self,
        *,
        match_category: str,
        match_severity: str,
        match_alert_type: Optional[str] = None,
        priority: Optional[int] = None,
    ) -> List[RoutingRule]:
        """Used by the bulk timing-update endpoint to find affected rules."""
        stmt = select(RoutingRule).where(
            RoutingRule.match_category == match_category,
            RoutingRule.match_severity == match_severity,
        )
        if match_alert_type is not None:
            stmt = stmt.where(RoutingRule.match_alert_type == match_alert_type)
        if priority is not None:
            stmt = stmt.where(RoutingRule.priority == priority)
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    # ── Writes ──

    async def add(self, rule: RoutingRule) -> RoutingRule:
        self._db.add(rule)
        await self._db.flush()
        return rule

    async def apply_updates(self, instance: RoutingRule, data: dict) -> RoutingRule:
        for key, value in data.items():
            setattr(instance, key, value)
        await self._db.flush()
        return instance

    async def bulk_update_timing(
        self,
        *,
        match_category: str,
        match_severity: str,
        match_alert_type: Optional[str] = None,
        priority: Optional[int] = None,
        group_wait: Optional[str] = None,
        group_interval: Optional[str] = None,
        repeat_interval: Optional[str] = None,
    ) -> int:
        """Apply timing changes in one UPDATE; returns affected row count."""
        values = {
            k: v
            for k, v in {
                "group_wait": group_wait,
                "group_interval": group_interval,
                "repeat_interval": repeat_interval,
            }.items()
            if v is not None
        }
        if not values:
            return 0
        stmt = (
            update(RoutingRule)
            .where(
                RoutingRule.match_category == match_category,
                RoutingRule.match_severity == match_severity,
            )
            .values(**values)
        )
        if match_alert_type is not None:
            stmt = stmt.where(RoutingRule.match_alert_type == match_alert_type)
        if priority is not None:
            stmt = stmt.where(RoutingRule.priority == priority)
        result = await self._db.execute(stmt)
        return int(result.rowcount or 0)

    async def delete_by_id(self, rule_id: int) -> int:
        result = await self._db.execute(
            delete(RoutingRule).where(RoutingRule.id == rule_id)
        )
        return int(result.rowcount or 0)

    async def commit(self) -> None:
        await self._db.commit()

    async def rollback(self) -> None:
        await self._db.rollback()
