"""Alert config sync service.

Reconciles the alert tables into Prometheus + Alertmanager config files and
triggers a hot reload. Owns the periodic background loop and the mutex that
keeps manual + periodic syncs from overlapping.

Replaces the standalone alert-config-sync-service. The HTTP ``POST /sync`` hop
is gone — alert CRUD routes call ``sync_configuration(blocking=False)`` directly,
and the lifespan starts ``run_periodic_loop``.

Rewritten from alert-config-sync-service/main.py:143-1335. ``organization`` is
dropped; DB access goes through the SQLAlchemy repos / sessions; config comes
from ``settings``; auth_db reads use raw ``text()`` against the secondary session.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import settings
from app.core.database import get_auth_session_factory, get_primary_session_factory
from app.models.alert_management.alert_definition import AlertDefinition
from app.models.alert_management.notification_receiver import NotificationReceiver
from app.models.alert_management.routing_rule import RoutingRule
from app.repositories.alert_management.alert_definition_repository import (
    AlertDefinitionRepository,
)
from app.repositories.alert_management.notification_receiver_repository import (
    NotificationReceiverRepository,
)
from app.repositories.alert_management.routing_rule_repository import RoutingRuleRepository
from app.utils.config_renderer import (
    build_smtp_global_config,
    generate_alertmanager_yaml,
    generate_prometheus_alerts_yaml,
    trigger_alertmanager_reload,
    trigger_prometheus_reload,
    write_yaml_file,
)

logger = logging.getLogger(__name__)

# auth_db (ai4iplatform_auth) schema: users.id (UUID PK), users.tenant_id → tenants.id,
# user_role.user_id → users.id, user_role.role_id → roles.id, roles.id (PK), roles.name.

# tenant_id lookup by organisation name (tenants PK is `id`).
_SQL_TENANT_ID = text(
    """
    SELECT id FROM tenants
    WHERE LOWER(TRIM(organisation)) = LOWER(TRIM(:tenant_name))
    LIMIT 1
    """
)
# TENANT ADMIN emails for a tenant id.
_SQL_TENANT_ADMIN_EMAILS_BY_ID = text(
    """
    SELECT u.email
    FROM users u
    JOIN user_role ur ON ur.user_id = u.id
    JOIN roles r ON r.id = ur.role_id
    WHERE u.tenant_id = :tenant_id
      AND u.is_active = true
      AND COALESCE(u.is_tenant_active, true) = true
      AND r.name = 'TENANT ADMIN'
      AND u.email IS NOT NULL AND u.email != ''
    """
)
# Emails by RBAC role.
_SQL_EMAILS_BY_ROLE = text(
    """
    SELECT DISTINCT u.email
    FROM users u
    INNER JOIN user_role ur ON ur.user_id = u.id
    INNER JOIN roles r ON r.id = ur.role_id
    WHERE r.name = :role_name
      AND u.is_active = true
      AND u.email IS NOT NULL AND u.email != ''
    ORDER BY u.email
    """
)


class SyncService:
    """Generates + reloads Prometheus/Alertmanager config from the alert tables."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._in_progress = False

    # ── Public entrypoints ──

    async def sync_configuration(self, *, blocking: bool = True) -> bool:
        """Run one full sync cycle. Returns True if both reloads succeeded.

        ``blocking=True`` (manual sync) waits for the lock; ``blocking=False``
        (periodic sync) skips this cycle if a sync is already running.
        """
        if not self._validate_paths():
            logger.warning(
                "Alert sync skipped: PROMETHEUS_*/ALERTMANAGER_* paths/URLs not configured"
            )
            return False

        if blocking:
            try:
                await asyncio.wait_for(self._lock.acquire(), timeout=10.0)
            except asyncio.TimeoutError:
                logger.warning("Could not acquire sync lock within timeout")
                return False
        else:
            try:
                await asyncio.wait_for(self._lock.acquire(), timeout=0.1)
            except asyncio.TimeoutError:
                logger.debug("Sync in progress; skipping periodic cycle")
                return False

        try:
            self._in_progress = True
            return await self._do_sync()
        finally:
            self._in_progress = False
            if self._lock.locked():
                self._lock.release()

    async def run_periodic_loop(self) -> None:
        """Background loop — initial blocking sync, then non-blocking every SYNC_INTERVAL."""
        try:
            await self.sync_configuration(blocking=True)
        except Exception as exc:
            logger.error("Initial alert sync failed: %s", exc, exc_info=True)

        interval = settings.sync_interval or 60
        while True:
            try:
                await asyncio.sleep(interval)
                await self.sync_configuration(blocking=False)
            except asyncio.CancelledError:
                logger.info("Alert sync loop cancelled; stopping")
                raise
            except Exception as exc:
                logger.error("Periodic alert sync failed: %s", exc, exc_info=True)

    # ── Orchestration ──

    async def _do_sync(self) -> bool:
        logger.info("Starting alert configuration sync...")
        primary_factory = get_primary_session_factory()
        auth_factory = get_auth_session_factory()

        async with primary_factory() as session:
            definitions = await self._fetch_definitions(session)
            receivers = await self._fetch_receivers(session)
            routing_rules = await self._fetch_rules(session)

        logger.info(
            "Fetched %d alert definitions, %d receivers, %d routing rules",
            len(definitions),
            len(receivers),
            len(routing_rules),
        )

        # Resolve emails from auth_db (best-effort; falls back to DEFAULT_RECEIVER_EMAILS).
        default_admin_emails = await self._fetch_emails_by_role("ADMIN", auth_factory)
        roles_needed = {
            (r.get("rbac_role") or "").strip() or "ADMIN"
            for r in receivers
            if not (r.get("tenant") or "").strip()
        }
        role_emails_map: Dict[str, List[str]] = {"ADMIN": default_admin_emails}
        for role in roles_needed:
            if role != "ADMIN":
                role_emails_map[role] = await self._fetch_emails_by_role(role, auth_factory)

        tenant_resolution_map: Dict[str, Tuple[str, List[str]]] = {}
        for tname in {(r.get("tenant") or "").strip() for r in receivers if (r.get("tenant") or "").strip()}:
            resolved = await self._resolve_tenant(tname, auth_factory)
            if resolved:
                tenant_resolution_map[tname] = resolved

        # Render.
        application_alerts = generate_prometheus_alerts_yaml(definitions, category="application")
        infrastructure_alerts = generate_prometheus_alerts_yaml(definitions, category="infrastructure")
        smtp_config = build_smtp_global_config(
            smtp_smarthost=settings.smtp_smarthost,
            smtp_from=settings.smtp_from,
            smtp_auth_username=settings.smtp_auth_username,
            smtp_auth_password=settings.smtp_auth_password,
        )
        alertmanager_config = generate_alertmanager_yaml(
            receivers,
            routing_rules,
            default_admin_emails=default_admin_emails,
            tenant_resolution_map=tenant_resolution_map,
            role_emails_map=role_emails_map,
            history_webhook_url=settings.alert_history_webhook_url,
            environment=settings.environment,
            smtp_config=smtp_config,
        )

        # Write.
        await write_yaml_file(settings.prometheus_application_alerts_path, application_alerts)
        await write_yaml_file(settings.prometheus_infrastructure_alerts_path, infrastructure_alerts)
        await write_yaml_file(settings.alertmanager_config_path, alertmanager_config, validate=False)

        # Reload.
        prometheus_ok = await trigger_prometheus_reload(settings.prometheus_url)
        alertmanager_ok = await trigger_alertmanager_reload(settings.alertmanager_url)

        if prometheus_ok and alertmanager_ok:
            logger.info("Alert configuration sync completed successfully")
        else:
            logger.warning("Alert configuration sync completed with warnings")
        return prometheus_ok and alertmanager_ok

    # ── Data fetch (primary DB → render-friendly dicts) ──

    async def _fetch_definitions(self, session: AsyncSession) -> List[Dict[str, Any]]:
        repo = AlertDefinitionRepository(session)
        return [self._definition_to_dict(d) for d in await repo.list_enabled()]

    async def _fetch_receivers(self, session: AsyncSession) -> List[Dict[str, Any]]:
        repo = NotificationReceiverRepository(session)
        return [self._receiver_to_dict(r) for r in await repo.list_enabled()]

    async def _fetch_rules(self, session: AsyncSession) -> List[Dict[str, Any]]:
        repo = RoutingRuleRepository(session)
        return [self._rule_to_dict(r) for r in await repo.list_enabled()]

    @staticmethod
    def _definition_to_dict(d: AlertDefinition) -> Dict[str, Any]:
        return {
            "id": d.id,
            "name": d.name,
            "description": d.description,
            "promql_expr": d.promql_expr,
            "category": d.category,
            "severity": d.severity,
            "urgency": d.urgency,
            "alert_type": d.alert_type,
            "sub_category": d.sub_category,
            "signal": d.signal,
            "signal_metric": d.signal_metric,
            "condition_operator": d.condition_operator,
            "scope": d.scope,
            "service": d.service or [],
            "evaluation_interval": d.evaluation_interval,
            "for_duration": d.for_duration,
            "threshold_value": d.threshold_value,
            "threshold_unit": d.threshold_unit,
            "annotations": [
                {"key": a.annotation_key, "value": a.annotation_value}
                for a in (d.annotations or [])
            ],
        }

    @staticmethod
    def _receiver_to_dict(r: NotificationReceiver) -> Dict[str, Any]:
        return {
            "id": r.id,
            "receiver_name": r.receiver_name,
            "rule_name": r.rule_name,
            "category": r.category,
            "severity": r.severity,
            "email_to": list(r.email_to or []),
            "rbac_role": r.rbac_role,
            "alert_names": list(r.alert_names or []) or None,
            "tenant": r.tenant,
            "email_subject_template": r.email_subject_template,
            "email_body_template": r.email_body_template,
        }

    @staticmethod
    def _rule_to_dict(r: RoutingRule) -> Dict[str, Any]:
        return {
            "id": r.id,
            "rule_name": r.rule_name,
            "receiver_id": r.receiver_id,
            "match_severity": r.match_severity,
            "match_category": r.match_category,
            "match_alert_type": r.match_alert_type,
            "match_alert_names": list(r.match_alert_names or []) or None,
            "match_tenant_id": r.match_tenant_id,
            "group_by": list(r.group_by or []) or None,
            "group_wait": r.group_wait,
            "group_interval": r.group_interval,
            "repeat_interval": r.repeat_interval,
            "priority": r.priority,
        }

    # ── auth_db email resolution (best-effort) ──

    async def _fetch_emails_by_role(
        self, role_name: str, auth_factory: Optional[async_sessionmaker[AsyncSession]]
    ) -> List[str]:
        fallback = self._default_emails() if role_name == "ADMIN" else []
        if auth_factory is None:
            return fallback
        try:
            async with auth_factory() as session:
                result = await session.execute(_SQL_EMAILS_BY_ROLE, {"role_name": role_name})
                emails = [row[0] for row in result.fetchall() if row[0]]
            return emails or fallback
        except Exception as exc:
            logger.warning("Could not fetch %s emails from auth_db: %s", role_name, exc)
            return fallback

    async def _resolve_tenant(
        self, tenant_name: str, auth_factory: Optional[async_sessionmaker[AsyncSession]]
    ) -> Optional[Tuple[str, List[str]]]:
        if auth_factory is None:
            return None
        try:
            async with auth_factory() as session:
                row = (await session.execute(_SQL_TENANT_ID, {"tenant_name": tenant_name})).first()
                if not row:
                    return None
                tenant_id = str(row[0])
                emails_result = await session.execute(
                    _SQL_TENANT_ADMIN_EMAILS_BY_ID, {"tenant_id": row[0]}
                )
                emails = [r[0] for r in emails_result.fetchall() if r[0]]
            return tenant_id, emails
        except Exception as exc:
            logger.warning("Failed to resolve tenant '%s': %s", tenant_name, exc)
            return None

    @staticmethod
    def _default_emails() -> List[str]:
        raw = settings.default_receiver_emails or ""
        return [e.strip() for e in raw.split(",") if e.strip()]

    @staticmethod
    def _validate_paths() -> bool:
        return all(
            [
                settings.prometheus_application_alerts_path,
                settings.prometheus_infrastructure_alerts_path,
                settings.alertmanager_config_path,
                settings.prometheus_url,
                settings.alertmanager_url,
            ]
        )
