"""Unit tests for alert-management services and PromQL builder utilities.

All external dependencies (DB, SQLAlchemy, Redis) are mocked so the tests run
with plain pytest — no running services required.

Import strategy
---------------
Service modules live under ``app/services/alert-management/`` (hyphenated
directory) and are loaded via ``importlib.import_module``.  SQLAlchemy-backed
ORM model/repo classes are stubbed before any app imports.
"""

from __future__ import annotations

import sys
import types
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import importlib

import pytest

# ── Module-level stubs ────────────────────────────────────────────────────────
# The sqlalchemy stub inserted by test_pii_management.py lacks ``text``.
# receiver_service.py does ``from sqlalchemy import text`` at module level, so
# we add it before loading that module.


def _stub(name: str, **attrs) -> types.ModuleType:
    mod = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(mod, k, v)
    sys.modules.setdefault(name, mod)
    return mod


# Patch the sqlalchemy stub to include ``text`` (no-op when real sqlalchemy is
# already loaded, since setdefault did not overwrite it).
if "sqlalchemy" in sys.modules and not hasattr(sys.modules["sqlalchemy"], "text"):
    sys.modules["sqlalchemy"].text = MagicMock

# ORM model stubs for alert-management
_stub("app.models.alert_management")
_stub("app.models.alert_management.alert_definition", AlertDefinition=MagicMock, AlertAnnotation=MagicMock)
_stub("app.models.alert_management.alert_history", AlertHistory=MagicMock)
_stub("app.models.alert_management.notification_receiver", NotificationReceiver=MagicMock)
_stub("app.models.alert_management.routing_rule", RoutingRule=MagicMock)

# Repository stubs
_stub("app.repositories.alert_management")
_stub("app.repositories.alert_management.alert_definition_repository", AlertDefinitionRepository=MagicMock)
_stub("app.repositories.alert_management.alert_history_repository", AlertHistoryRepository=MagicMock)
_stub("app.repositories.alert_management.notification_receiver_repository", NotificationReceiverRepository=MagicMock)
_stub("app.repositories.alert_management.routing_rule_repository", RoutingRuleRepository=MagicMock)

# ── Import service classes ────────────────────────────────────────────────────

_def_mod = importlib.import_module("app.services.alert-management.definition_service")
_rcv_mod = importlib.import_module("app.services.alert-management.receiver_service")
_rr_mod = importlib.import_module("app.services.alert-management.routing_rule_service")

AlertDefinitionService = _def_mod.AlertDefinitionService
NotificationReceiverService = _rcv_mod.NotificationReceiverService
RoutingRuleService = _rr_mod.RoutingRuleService

from app.core.exceptions import (  # noqa: E402
    DuplicateEntityError,
    EntityNotFoundError,
    ValidationError,
)
from app.schemas.alert_management.alert_definition import (  # noqa: E402
    AlertAnnotation,
    AlertDefinitionCreate,
    AlertDefinitionUpdate,
)
from app.schemas.alert_management.receiver import (  # noqa: E402
    NotificationReceiverCreate,
    NotificationReceiverUpdate,
)
from app.schemas.alert_management.routing_rule import (  # noqa: E402
    RoutingRuleCreate,
    RoutingRuleTimingUpdate,
    RoutingRuleUpdate,
)
from app.utils.promql_builder import (  # noqa: E402
    SIGNALS_CONFIG,
    alert_type_to_display,
    build_promql_from_threshold,
    inject_endpoint_into_promql,
    _normalize_tasks,
)


# ── ORM mock helpers ──────────────────────────────────────────────────────────

_NOW = datetime(2024, 6, 1, 12, 0, 0)


def _make_definition_orm(**overrides) -> MagicMock:
    d = MagicMock()
    d.id = 1
    d.name = "HighLatency"
    d.description = "Alert on high latency"
    d.promql_expr = 'rate(foo[5m]) > 0.5'
    d.threshold_value = 0.5
    d.threshold_unit = "s"
    d.category = "application"
    d.severity = "critical"
    d.urgency = "high"
    d.alert_type = "Latency"
    d.sub_category = None
    d.signal = None
    d.signal_metric = None
    d.condition_operator = None
    d.scope = None
    d.service = None
    d.evaluation_interval = "30s"
    d.for_duration = "5m"
    d.enabled = True
    d.created_at = _NOW
    d.updated_at = _NOW
    d.annotations = []
    for k, v in overrides.items():
        setattr(d, k, v)
    return d


def _make_receiver_orm(**overrides) -> MagicMock:
    r = MagicMock()
    r.id = 1
    r.receiver_name = "critical-application"
    r.rule_name = None
    r.description = None
    r.category = "application"
    r.severity = "critical"
    r.email_to = ["ops@example.com"]
    r.rbac_role = None
    r.alert_names = None
    r.tenant = None
    r.email_subject_template = None
    r.email_body_template = None
    r.enabled = True
    r.created_at = _NOW
    r.updated_at = _NOW
    for k, v in overrides.items():
        setattr(r, k, v)
    return r


def _make_routing_rule_orm(**overrides) -> MagicMock:
    rr = MagicMock()
    rr.id = 1
    rr.rule_name = "rule-1"
    rr.receiver_id = 1
    rr.match_severity = "critical"
    rr.match_category = "application"
    rr.match_alert_type = None
    rr.match_alert_names = None
    rr.match_tenant_id = None
    rr.group_by = ["alertname", "category", "severity"]
    rr.group_wait = "10s"
    rr.group_interval = "10s"
    rr.repeat_interval = "12h"
    rr.continue_routing = False
    rr.priority = 100
    rr.enabled = True
    rr.created_at = _NOW
    rr.updated_at = _NOW
    for k, v in overrides.items():
        setattr(rr, k, v)
    return rr


# ===========================================================================
# Section 1 — AlertDefinitionService
# ===========================================================================


def _make_def_svc() -> AlertDefinitionService:
    repo = MagicMock()
    repo.get_by_id = AsyncMock(return_value=None)
    repo.get_by_name = AsyncMock(return_value=None)
    repo.list = AsyncMock(return_value=[])
    repo.list_enabled = AsyncMock(return_value=[])
    repo.add = AsyncMock()
    repo.commit = AsyncMock()
    repo.replace_annotations = AsyncMock()
    repo.apply_updates = AsyncMock()
    repo.delete_by_id = AsyncMock()
    return AlertDefinitionService(repo=repo)


def _latency_create_payload(**overrides) -> AlertDefinitionCreate:
    defaults = dict(
        name="HighLatency",
        threshold_value=0.5,
        threshold_unit="s",
        category="application",
        severity="critical",
        urgency="high",
        alert_type="Latency",
    )
    defaults.update(overrides)
    return AlertDefinitionCreate(**defaults)


class TestAlertDefinitionServiceGet:
    @pytest.mark.asyncio
    async def test_get_not_found_raises(self):
        svc = _make_def_svc()
        with pytest.raises(EntityNotFoundError):
            await svc.get(99)

    @pytest.mark.asyncio
    async def test_get_returns_response(self):
        svc = _make_def_svc()
        svc._repo.get_by_id = AsyncMock(return_value=_make_definition_orm())
        result = await svc.get(1)
        assert result.id == 1
        assert result.name == "HighLatency"

    @pytest.mark.asyncio
    async def test_get_returns_correct_enabled_state(self):
        svc = _make_def_svc()
        svc._repo.get_by_id = AsyncMock(return_value=_make_definition_orm(enabled=False))
        result = await svc.get(1)
        assert result.enabled is False


class TestAlertDefinitionServiceList:
    @pytest.mark.asyncio
    async def test_list_returns_empty(self):
        svc = _make_def_svc()
        results = await svc.list()
        assert results == []

    @pytest.mark.asyncio
    async def test_list_enabled_only_uses_list_enabled_repo(self):
        svc = _make_def_svc()
        svc._repo.list_enabled = AsyncMock(return_value=[_make_definition_orm()])
        results = await svc.list(enabled_only=True)
        svc._repo.list_enabled.assert_awaited_once()
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_list_all_uses_list_repo(self):
        svc = _make_def_svc()
        svc._repo.list = AsyncMock(return_value=[_make_definition_orm(), _make_definition_orm(id=2, name="HighError")])
        results = await svc.list(enabled_only=False)
        svc._repo.list.assert_awaited_once()
        assert len(results) == 2


class TestAlertDefinitionServiceCreate:
    @pytest.mark.asyncio
    async def test_create_duplicate_name_raises(self):
        svc = _make_def_svc()
        svc._repo.get_by_name = AsyncMock(return_value=_make_definition_orm())
        payload = _latency_create_payload()
        with pytest.raises(DuplicateEntityError):
            await svc.create(payload)

    @pytest.mark.asyncio
    async def test_create_calls_add_and_commit(self):
        svc = _make_def_svc()
        refreshed = _make_definition_orm()
        svc._repo.get_by_id = AsyncMock(return_value=refreshed)
        payload = _latency_create_payload()
        await svc.create(payload)
        svc._repo.add.assert_awaited_once()
        svc._repo.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_create_returns_response(self):
        svc = _make_def_svc()
        refreshed = _make_definition_orm()
        svc._repo.get_by_id = AsyncMock(return_value=refreshed)
        payload = _latency_create_payload()
        result = await svc.create(payload)
        assert result.name == "HighLatency"

    @pytest.mark.asyncio
    async def test_create_with_annotations_calls_replace_annotations(self):
        svc = _make_def_svc()
        refreshed = _make_definition_orm()
        svc._repo.get_by_id = AsyncMock(return_value=refreshed)
        payload = _latency_create_payload(
            annotations=[AlertAnnotation(key="summary", value="High latency alert")]
        )
        await svc.create(payload)
        svc._repo.replace_annotations.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_create_infra_cpu_alert_builds_promql(self):
        svc = _make_def_svc()
        refreshed = _make_definition_orm(category="infrastructure", alert_type="CPU", promql_expr="cpu > 80")
        svc._repo.get_by_id = AsyncMock(return_value=refreshed)
        payload = AlertDefinitionCreate(
            name="HighCPU",
            threshold_value=80.0,
            threshold_unit="%",
            category="infrastructure",
            severity="warning",
            urgency="medium",
            alert_type="CPU",
        )
        result = await svc.create(payload)
        assert result.category == "infrastructure"


class TestAlertDefinitionServiceUpdate:
    @pytest.mark.asyncio
    async def test_update_not_found_raises(self):
        svc = _make_def_svc()
        with pytest.raises(EntityNotFoundError):
            await svc.update(99, AlertDefinitionUpdate())

    @pytest.mark.asyncio
    async def test_update_calls_apply_updates_and_commit(self):
        svc = _make_def_svc()
        existing = _make_definition_orm()
        svc._repo.get_by_id = AsyncMock(side_effect=[existing, existing])
        payload = AlertDefinitionUpdate(description="updated desc")
        await svc.update(1, payload)
        svc._repo.apply_updates.assert_awaited_once()
        svc._repo.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_update_with_annotations_calls_replace_annotations(self):
        svc = _make_def_svc()
        existing = _make_definition_orm()
        svc._repo.get_by_id = AsyncMock(side_effect=[existing, existing])
        payload = AlertDefinitionUpdate(
            annotations=[AlertAnnotation(key="impact", value="high")]
        )
        await svc.update(1, payload)
        svc._repo.replace_annotations.assert_awaited_once()


class TestAlertDefinitionServiceDelete:
    @pytest.mark.asyncio
    async def test_delete_not_found_raises(self):
        svc = _make_def_svc()
        with pytest.raises(EntityNotFoundError):
            await svc.delete(99)

    @pytest.mark.asyncio
    async def test_delete_calls_delete_and_commit(self):
        svc = _make_def_svc()
        svc._repo.get_by_id = AsyncMock(return_value=_make_definition_orm())
        await svc.delete(1)
        svc._repo.delete_by_id.assert_awaited_once_with(1)
        svc._repo.commit.assert_awaited_once()


class TestAlertDefinitionServiceSetEnabled:
    @pytest.mark.asyncio
    async def test_set_enabled_not_found_raises(self):
        svc = _make_def_svc()
        with pytest.raises(EntityNotFoundError):
            await svc.set_enabled(99, True)

    @pytest.mark.asyncio
    async def test_set_enabled_true_calls_apply_updates(self):
        svc = _make_def_svc()
        existing = _make_definition_orm(enabled=False)
        svc._repo.get_by_id = AsyncMock(side_effect=[existing, existing])
        await svc.set_enabled(1, True)
        svc._repo.apply_updates.assert_awaited_once_with(existing, {"enabled": True})
        svc._repo.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_set_enabled_false_stores_false(self):
        svc = _make_def_svc()
        existing = _make_definition_orm(enabled=True)
        svc._repo.get_by_id = AsyncMock(side_effect=[existing, existing])
        await svc.set_enabled(1, False)
        svc._repo.apply_updates.assert_awaited_once_with(existing, {"enabled": False})


class TestAlertDefinitionSignalToDisplay:
    def test_latency_signal_returns_label(self):
        assert AlertDefinitionService._signal_to_display("latency", "application") == "Latency"

    def test_error_rate_signal_returns_label(self):
        result = AlertDefinitionService._signal_to_display("error_rate", "application")
        assert result == "Error rate"

    def test_infra_cpu_returns_cpu(self):
        result = AlertDefinitionService._signal_to_display("cpu_utilization", "infrastructure")
        assert result == "CPU"

    def test_infra_memory_returns_memory(self):
        result = AlertDefinitionService._signal_to_display("memory_utilization", "infrastructure")
        assert result == "Memory"

    def test_unknown_signal_falls_back_to_raw(self):
        result = AlertDefinitionService._signal_to_display("some_custom", "application")
        assert result == "some_custom"

    def test_empty_signal_returns_none_or_empty(self):
        result = AlertDefinitionService._signal_to_display(None, "application")
        assert result is None or result == ""


# ===========================================================================
# Section 2 — NotificationReceiverService
# ===========================================================================


def _make_rcv_svc(auth_db=None) -> NotificationReceiverService:
    receiver_repo = MagicMock()
    receiver_repo.get_by_id = AsyncMock(return_value=None)
    receiver_repo.list = AsyncMock(return_value=[])
    receiver_repo.add = AsyncMock()
    receiver_repo.commit = AsyncMock()
    receiver_repo.apply_updates = AsyncMock()
    receiver_repo.delete_by_id = AsyncMock()
    receiver_repo.get_by_receiver_name = AsyncMock(return_value=None)

    routing_repo = MagicMock()
    routing_repo.list = AsyncMock(return_value=[])
    routing_repo.add = AsyncMock()
    routing_repo.get_by_rule_name = AsyncMock(return_value=None)

    return NotificationReceiverService(
        receiver_repo=receiver_repo,
        routing_rule_repo=routing_repo,
        auth_db=auth_db,
    )


class TestNotificationReceiverServiceGet:
    @pytest.mark.asyncio
    async def test_get_not_found_raises(self):
        svc = _make_rcv_svc()
        with pytest.raises(EntityNotFoundError):
            await svc.get(99)

    @pytest.mark.asyncio
    async def test_get_returns_response(self):
        svc = _make_rcv_svc()
        receiver = _make_receiver_orm()
        svc._repo.get_by_id = AsyncMock(return_value=receiver)
        result = await svc.get(1)
        assert result.id == 1
        assert result.receiver_name == "critical-application"

    @pytest.mark.asyncio
    async def test_get_returns_email_list(self):
        svc = _make_rcv_svc()
        receiver = _make_receiver_orm(email_to=["a@b.com", "c@d.com"])
        svc._repo.get_by_id = AsyncMock(return_value=receiver)
        result = await svc.get(1)
        assert "a@b.com" in result.email_to


class TestNotificationReceiverServiceList:
    @pytest.mark.asyncio
    async def test_list_returns_empty(self):
        svc = _make_rcv_svc()
        results = await svc.list()
        assert results == []

    @pytest.mark.asyncio
    async def test_list_returns_all_receivers(self):
        svc = _make_rcv_svc()
        svc._repo.list = AsyncMock(return_value=[_make_receiver_orm()])
        results = await svc.list()
        assert len(results) == 1


class TestNotificationReceiverServiceDelete:
    @pytest.mark.asyncio
    async def test_delete_not_found_raises(self):
        svc = _make_rcv_svc()
        with pytest.raises(EntityNotFoundError):
            await svc.delete(99)

    @pytest.mark.asyncio
    async def test_delete_calls_delete_and_commit(self):
        svc = _make_rcv_svc()
        svc._repo.get_by_id = AsyncMock(return_value=_make_receiver_orm())
        await svc.delete(1)
        svc._repo.delete_by_id.assert_awaited_once_with(1)
        svc._repo.commit.assert_awaited_once()


class TestNotificationReceiverServiceCreate:
    @pytest.mark.asyncio
    async def test_create_invalid_category_raises(self):
        svc = _make_rcv_svc()
        payload = NotificationReceiverCreate(
            category="invalid",
            severity="critical",
            email_to=["ops@example.com"],
        )
        with pytest.raises(ValidationError):
            await svc.create(payload)

    @pytest.mark.asyncio
    async def test_create_invalid_severity_raises(self):
        svc = _make_rcv_svc()
        payload = NotificationReceiverCreate(
            category="application",
            severity="unknown",
            email_to=["ops@example.com"],
        )
        with pytest.raises(ValidationError):
            await svc.create(payload)

    @pytest.mark.asyncio
    async def test_create_with_email_to_commits(self):
        svc = _make_rcv_svc()
        refreshed = _make_receiver_orm()
        svc._repo.get_by_id = AsyncMock(return_value=refreshed)
        payload = NotificationReceiverCreate(
            category="application",
            severity="critical",
            email_to=["ops@example.com"],
        )
        result = await svc.create(payload)
        svc._repo.add.assert_awaited_once()
        svc._repo.commit.assert_awaited_once()
        assert result.receiver_name == "critical-application"

    @pytest.mark.asyncio
    async def test_create_duplicate_receiver_name_raises(self):
        svc = _make_rcv_svc()
        svc._repo.get_by_receiver_name = AsyncMock(return_value=_make_receiver_orm())
        payload = NotificationReceiverCreate(
            category="application",
            severity="critical",
            email_to=["ops@example.com"],
        )
        with pytest.raises(DuplicateEntityError):
            await svc.create(payload)

    @pytest.mark.asyncio
    async def test_create_rbac_role_no_auth_db_raises(self):
        svc = _make_rcv_svc(auth_db=None)
        payload = NotificationReceiverCreate(
            category="application",
            severity="critical",
            rbac_role="ADMIN",
        )
        with pytest.raises((ValidationError, EntityNotFoundError)):
            await svc.create(payload)


class TestNotificationReceiverServiceGetEmailsByRole:
    @pytest.mark.asyncio
    async def test_get_emails_no_auth_db_raises_validation_error(self):
        svc = _make_rcv_svc(auth_db=None)
        with pytest.raises(ValidationError):
            await svc._get_emails_by_role("ADMIN")


class TestNotificationReceiverBuildReceiverName:
    def test_base_name_without_suffix(self):
        payload = NotificationReceiverCreate(
            category="application",
            severity="critical",
            email_to=["x@example.com"],
        )
        name, base, suffixes = NotificationReceiverService._build_receiver_name(payload)
        assert name == "critical-application"
        assert base == "critical-application"
        assert suffixes == []

    def test_name_with_alert_names_suffix(self):
        payload = NotificationReceiverCreate(
            category="application",
            severity="warning",
            email_to=["x@example.com"],
            alert_names=["HighLatency", "HighError"],
        )
        name, _, _ = NotificationReceiverService._build_receiver_name(payload)
        assert "alerts-" in name
        assert "HighError" in name

    def test_name_with_tenant_suffix(self):
        payload = NotificationReceiverCreate(
            category="infrastructure",
            severity="info",
            email_to=["x@example.com"],
            tenant="acme-corp",
        )
        name, _, _ = NotificationReceiverService._build_receiver_name(payload)
        assert "tenant-acme-corp" in name


# ===========================================================================
# Section 3 — RoutingRuleService
# ===========================================================================


def _make_rr_svc() -> RoutingRuleService:
    repo = MagicMock()
    repo.get_by_id = AsyncMock(return_value=None)
    repo.get_by_rule_name = AsyncMock(return_value=None)
    repo.list = AsyncMock(return_value=[])
    repo.add = AsyncMock()
    repo.commit = AsyncMock()
    repo.apply_updates = AsyncMock()
    repo.delete_by_id = AsyncMock()
    repo.bulk_update_timing = AsyncMock(return_value=3)
    return RoutingRuleService(repo=repo)


class TestRoutingRuleServiceGet:
    @pytest.mark.asyncio
    async def test_get_not_found_raises(self):
        svc = _make_rr_svc()
        with pytest.raises(EntityNotFoundError):
            await svc.get(99)

    @pytest.mark.asyncio
    async def test_get_returns_response(self):
        svc = _make_rr_svc()
        svc._repo.get_by_id = AsyncMock(return_value=_make_routing_rule_orm())
        result = await svc.get(1)
        assert result.id == 1
        assert result.rule_name == "rule-1"

    @pytest.mark.asyncio
    async def test_get_returns_correct_receiver_id(self):
        svc = _make_rr_svc()
        svc._repo.get_by_id = AsyncMock(return_value=_make_routing_rule_orm(receiver_id=42))
        result = await svc.get(1)
        assert result.receiver_id == 42


class TestRoutingRuleServiceList:
    @pytest.mark.asyncio
    async def test_list_returns_empty(self):
        svc = _make_rr_svc()
        results = await svc.list()
        assert results == []

    @pytest.mark.asyncio
    async def test_list_returns_all_rules(self):
        svc = _make_rr_svc()
        svc._repo.list = AsyncMock(return_value=[_make_routing_rule_orm(), _make_routing_rule_orm(id=2, rule_name="rule-2")])
        results = await svc.list()
        assert len(results) == 2


class TestRoutingRuleServiceCreate:
    @pytest.mark.asyncio
    async def test_create_duplicate_name_raises(self):
        svc = _make_rr_svc()
        svc._repo.get_by_rule_name = AsyncMock(return_value=_make_routing_rule_orm())
        payload = RoutingRuleCreate(rule_name="rule-1", receiver_id=1)
        with pytest.raises(DuplicateEntityError):
            await svc.create(payload)

    @pytest.mark.asyncio
    async def test_create_calls_add_and_commit(self):
        svc = _make_rr_svc()
        refreshed = _make_routing_rule_orm()
        svc._repo.get_by_id = AsyncMock(return_value=refreshed)
        payload = RoutingRuleCreate(rule_name="new-rule", receiver_id=2)
        await svc.create(payload)
        svc._repo.add.assert_awaited_once()
        svc._repo.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_create_returns_response(self):
        svc = _make_rr_svc()
        refreshed = _make_routing_rule_orm(rule_name="new-rule", receiver_id=2)
        svc._repo.get_by_id = AsyncMock(return_value=refreshed)
        payload = RoutingRuleCreate(rule_name="new-rule", receiver_id=2)
        result = await svc.create(payload)
        assert result.rule_name == "new-rule"
        assert result.receiver_id == 2


class TestRoutingRuleServiceUpdate:
    @pytest.mark.asyncio
    async def test_update_not_found_raises(self):
        svc = _make_rr_svc()
        with pytest.raises(EntityNotFoundError):
            await svc.update(99, RoutingRuleUpdate())

    @pytest.mark.asyncio
    async def test_update_duplicate_rule_name_raises(self):
        svc = _make_rr_svc()
        existing = _make_routing_rule_orm(id=1, rule_name="rule-1")
        clashing = _make_routing_rule_orm(id=2, rule_name="rule-2")
        svc._repo.get_by_id = AsyncMock(return_value=existing)
        svc._repo.get_by_rule_name = AsyncMock(return_value=clashing)
        payload = RoutingRuleUpdate(rule_name="rule-2")
        with pytest.raises(DuplicateEntityError):
            await svc.update(1, payload)

    @pytest.mark.asyncio
    async def test_update_calls_apply_and_commit(self):
        svc = _make_rr_svc()
        existing = _make_routing_rule_orm()
        svc._repo.get_by_id = AsyncMock(side_effect=[existing, existing])
        payload = RoutingRuleUpdate(priority=50)
        await svc.update(1, payload)
        svc._repo.apply_updates.assert_awaited_once()
        svc._repo.commit.assert_awaited_once()


class TestRoutingRuleServiceDelete:
    @pytest.mark.asyncio
    async def test_delete_not_found_raises(self):
        svc = _make_rr_svc()
        with pytest.raises(EntityNotFoundError):
            await svc.delete(99)

    @pytest.mark.asyncio
    async def test_delete_calls_delete_and_commit(self):
        svc = _make_rr_svc()
        svc._repo.get_by_id = AsyncMock(return_value=_make_routing_rule_orm())
        await svc.delete(1)
        svc._repo.delete_by_id.assert_awaited_once_with(1)
        svc._repo.commit.assert_awaited_once()


class TestRoutingRuleServiceUpdateTiming:
    @pytest.mark.asyncio
    async def test_update_timing_no_params_raises(self):
        svc = _make_rr_svc()
        payload = RoutingRuleTimingUpdate(category="application", severity="critical")
        with pytest.raises(ValidationError):
            await svc.update_timing(payload)

    @pytest.mark.asyncio
    async def test_update_timing_returns_affected_count(self):
        svc = _make_rr_svc()
        svc._repo.bulk_update_timing = AsyncMock(return_value=5)
        payload = RoutingRuleTimingUpdate(
            category="application",
            severity="critical",
            group_wait="30s",
        )
        count = await svc.update_timing(payload)
        assert count == 5
        svc._repo.commit.assert_awaited_once()


# ===========================================================================
# Section 4 — PromQL builder (pure functions, no DB)
# ===========================================================================


class TestBuildPromqlFromThreshold:
    def test_application_latency_builds_histogram_query(self):
        result = build_promql_from_threshold("application", "Latency", 0.5, "s")
        assert "histogram_quantile" in result
        assert "> 0.5" in result

    def test_application_error_rate_builds_rate_query(self):
        result = build_promql_from_threshold("application", "Error Rate", 0.05, "s")
        assert "status_code" in result
        assert "> 0.05" in result

    def test_infrastructure_cpu_builds_cpu_query(self):
        result = build_promql_from_threshold("infrastructure", "CPU", 80.0, "%")
        assert "node_cpu_seconds_total" in result
        assert "> 80.0" in result

    def test_infrastructure_memory_builds_memory_query(self):
        result = build_promql_from_threshold("infrastructure", "Memory", 90.0, "%")
        assert "node_memory_MemAvailable_bytes" in result
        assert "> 90.0" in result

    def test_infrastructure_disk_builds_disk_query(self):
        result = build_promql_from_threshold("infrastructure", "Disk", 85.0, "%")
        assert "node_filesystem_avail_bytes" in result
        assert "> 85.0" in result

    def test_invalid_application_type_raises(self):
        with pytest.raises(ValidationError):
            build_promql_from_threshold("application", "Disk", 80.0, "%")

    def test_invalid_infrastructure_type_raises(self):
        with pytest.raises(ValidationError):
            build_promql_from_threshold("infrastructure", "Latency", 0.5, "s")

    def test_invalid_category_raises(self):
        with pytest.raises(ValidationError):
            build_promql_from_threshold("unknown", "CPU", 80.0, "%")

    def test_error_rate_percent_unit_divides_by_100(self):
        result = build_promql_from_threshold("application", "error_rate", 10.0, "percent")
        assert "> 0.1" in result


class TestAlertTypeToDisplay:
    def test_latency_display(self):
        assert alert_type_to_display("Latency", "application") == "Latency"

    def test_error_rate_display(self):
        assert alert_type_to_display("Error Rate", "application") == "Error Rate"

    def test_cpu_display(self):
        assert alert_type_to_display("CPU", "infrastructure") == "CPU"

    def test_lowercase_latency_normalized(self):
        assert alert_type_to_display("latency", "application") == "Latency"

    def test_empty_alert_type_passthrough(self):
        assert alert_type_to_display("", "application") == ""


class TestNormalizeTasks:
    def test_empty_service_list_returns_none_or_empty(self):
        result = _normalize_tasks(None)
        assert result is None or result == []

    def test_single_task_returned(self):
        result = _normalize_tasks(["nmt"])
        assert result == ["nmt"]

    def test_service_suffix_stripped(self):
        result = _normalize_tasks(["nmt-service"])
        assert "nmt" in result

    def test_multiple_tasks_returned(self):
        result = _normalize_tasks(["nmt", "asr"])
        assert "nmt" in result
        assert "asr" in result


class TestInjectEndpointIntoPromql:
    def test_single_task_narrows_endpoint_selector(self):
        base = build_promql_from_threshold("application", "Latency", 0.5, "s")
        result = inject_endpoint_into_promql(base, ["nmt"])
        assert "nmt" in result

    def test_multiple_tasks_creates_or_pattern(self):
        base = build_promql_from_threshold("application", "Latency", 0.5, "s")
        result = inject_endpoint_into_promql(base, ["nmt", "asr"])
        assert "nmt" in result
        assert "asr" in result

    def test_original_broad_selector_replaced(self):
        base = build_promql_from_threshold("application", "Latency", 0.5, "s")
        assert '/.*inference.*"' in base
        result = inject_endpoint_into_promql(base, ["nmt"])
        assert "nmt" in result
