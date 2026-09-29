"""app/services/notification_management/monitoring_catalog_service.py

Load-bearing behaviour: selecting a role only stores the selection in
recipient_roles — no user lookup, no recipient snapshot (who it means is
resolved at send time, ai4i_core.kafka.recipients.
resolve_monitoring_recipients); thresholds are validated against the row's
own fixed unit; non-monitoring names are a 404 here.

No database — the session is faked, and fails on any query it doesn't
expect (including one against the dropped monitoring_alert_recipient).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.exceptions import EntityNotFoundError, ValidationError
from app.schemas.notification_management.catalog import (
    MonitoringCatalogUpdate,
    MonitoringThresholdBand,
)
from app.services.notification_management import monitoring_catalog_service as svc


def _row(name="LATENCY_P95", type="MONITORING", unit="SECONDS", recipient_roles=None):
    r = MagicMock()
    r.id = 10
    r.name = name
    r.type = type
    r.module = "MONITORING"
    r.channels = ["EMAIL"]
    r.scope = "GLOBAL"
    r.recipient_roles = recipient_roles if recipient_roles is not None else {"ADMIN": True, "MODERATOR": False}
    r.config = {"monitoring_thresholds": [
        {"value": v, "unit": unit, "active": False} for v in (2, 5, 10)
    ]}
    return r


class _Session:
    """Fake core-db session: the catalog row lookup is the only query the
    monitoring PATCH may issue."""

    def __init__(self, row):
        self.row = row
        self.queries = []
        self.commits = 0

    async def execute(self, stmt):
        sql = str(stmt)
        self.queries.append(sql)
        if "monitoring_alert_recipient" in sql or "FROM configs_notification_alert" not in sql:
            raise AssertionError(f"unexpected query: {sql}")
        result = MagicMock()
        result.scalar_one_or_none.return_value = self.row
        return result

    def add_all(self, objs):
        raise AssertionError("the monitoring PATCH must not insert recipient rows")

    async def commit(self):
        self.commits += 1

    async def refresh(self, row):
        pass


def _bands(*values, unit="SECONDS", active=False):
    return [MonitoringThresholdBand(value=v, unit=unit, active=active) for v in values]


@pytest.fixture(autouse=True)
def _no_redis():
    with patch.object(svc, "get_redis_client", return_value=MagicMock(publish=AsyncMock())):
        yield


@pytest.mark.asyncio
class TestRecipients:
    async def test_role_change_needs_no_user_lookup(self):
        # Review scenario: recipients used to be frozen into user ids here
        # (and a missing auth DB 503'd the save). Now the PATCH stores only
        # the selection; users are resolved when an alert is sent, so a
        # later role grant / revoke / deactivation needs no re-save.
        row = _row(recipient_roles={"ADMIN": False, "MODERATOR": False})
        session = _Session(row)
        item = await svc.update_monitoring_catalog(
            session, "LATENCY_P95", MonitoringCatalogUpdate(recipient_roles={"ADMIN": True}),
            updated_by="u1",
        )
        assert row.recipient_roles == {"ADMIN": True, "MODERATOR": False}
        assert item.recipient_roles == {"ADMIN": True, "MODERATOR": False}
        assert len(session.queries) == 1  # the row lookup — nothing else
        assert session.commits == 1

    async def test_selecting_moderator_merges_with_the_stored_selection(self):
        session = _Session(_row())
        item = await svc.update_monitoring_catalog(
            session, "LATENCY_P95", MonitoringCatalogUpdate(recipient_roles={"MODERATOR": True}),
        )
        assert item.recipient_roles == {"ADMIN": True, "MODERATOR": True}

    async def test_deselecting_every_role_is_stored(self):
        row = _row()
        await svc.update_monitoring_catalog(
            _Session(row), "LATENCY_P95", MonitoringCatalogUpdate(recipient_roles={"ADMIN": False}),
        )
        assert row.recipient_roles == {"ADMIN": False, "MODERATOR": False}

    async def test_tenant_admin_is_rejected(self):
        session = _Session(_row())
        with pytest.raises(ValidationError):
            await svc.update_monitoring_catalog(
                session, "LATENCY_P95", MonitoringCatalogUpdate(recipient_roles={"TENANT ADMIN": True}),
            )
        assert session.commits == 0

    async def test_response_carries_no_recipient_snapshot(self):
        item = await svc.update_monitoring_catalog(
            _Session(_row()), "LATENCY_P95", MonitoringCatalogUpdate(recipient_roles={"MODERATOR": True}),
        )
        assert "recipients" not in item.model_dump()


@pytest.mark.asyncio
class TestThresholds:
    async def test_thresholds_are_replaced(self):
        row = _row()
        await svc.update_monitoring_catalog(
            _Session(row), "LATENCY_P95",
            MonitoringCatalogUpdate(monitoring_thresholds=_bands(3, 6, 12, active=True)),
        )
        assert row.config["monitoring_thresholds"] == [
            {"value": v, "unit": "SECONDS", "active": True} for v in (3, 6, 12)
        ]

    @pytest.mark.parametrize("bands", [
        _bands(1, 2),                              # wrong count
        _bands(1, 1, 2),                           # duplicate values
        _bands(0, 1, 2),                           # non-positive
        _bands(1, 2, 3, unit="PERCENT"),           # unit differs from the row's
    ])
    async def test_invalid_thresholds_are_rejected(self, bands):
        with pytest.raises(ValidationError):
            await svc.update_monitoring_catalog(
                _Session(_row()), "LATENCY_P95", MonitoringCatalogUpdate(monitoring_thresholds=bands),
            )

    async def test_percent_over_100_is_rejected(self):
        with pytest.raises(ValidationError):
            await svc.update_monitoring_catalog(
                _Session(_row(name="ERROR_RATE_4XX", unit="PERCENT")), "ERROR_RATE_4XX",
                MonitoringCatalogUpdate(monitoring_thresholds=_bands(5, 10, 101, unit="PERCENT")),
            )


@pytest.mark.asyncio
class TestLookup:
    @pytest.mark.parametrize("name", ["QUOTA_THRESHOLD", "NOT_A_NAME"])
    async def test_non_monitoring_name_is_not_found(self, name):
        with pytest.raises(EntityNotFoundError):
            await svc.update_monitoring_catalog(_Session(None), name, MonitoringCatalogUpdate())

    async def test_missing_row_is_not_found(self):
        with pytest.raises(EntityNotFoundError):
            await svc.update_monitoring_catalog(_Session(None), "LATENCY_P95", MonitoringCatalogUpdate())


def test_value_rejects_strings_and_bools():
    for bad in ("5", True):
        with pytest.raises(ValueError):
            MonitoringThresholdBand(value=bad, unit="SECONDS", active=False)
