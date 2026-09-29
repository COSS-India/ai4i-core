"""app/services/notification_management/monitoring_catalog_service.py

Load-bearing behaviour: selecting a role only stores the selection in
recipient_roles — no user lookup, no recipient snapshot (who it means is
resolved at send time, ai4i_core.kafka.recipients.
RecipientResolver.for_roles); thresholds are validated against the row's
own fixed unit and replace its band rows (severity from the top); non-monitoring names are a 404 here.

No database — the session is faked, and fails on any query it doesn't
expect (including one against the dropped monitoring_alert_recipient).
"""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.exceptions import EntityNotFoundError, ValidationError
from app.schemas.notification_management.catalog import (
    MonitoringCatalogUpdate,
    MonitoringThresholdBand,
)
from app.services.notification_management import monitoring_catalog_service as svc
from app.services.notification_management.thresholds import severities_from_top


def _row(name="LATENCY_P95", type="MONITORING", unit="SECONDS", recipient_roles=None):
    r = MagicMock()
    r.id = 10
    r.name = name
    r.type = type
    r.module = "MONITORING"
    r.channels = ["EMAIL"]
    r.scope = "GLOBAL"
    r.recipient_roles = recipient_roles if recipient_roles is not None else {"ADMIN": True, "MODERATOR": False}
    r.unit = unit
    return r


def _band(value, active, unit, severity):
    return SimpleNamespace(band_value=Decimal(str(value)), active=active, unit=unit, severity=severity)


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


class _BandStore:
    def __init__(self):
        self.bands = defaultdict(list)

    def seed(self, row):
        self.bands[row.id] = [_band(v, False, row.unit, "INFO") for v in (2, 5, 10)]

    async def load(self, session, ids):
        return {i: list(self.bands[i]) for i in ids}

    async def replace(self, session, notification_id, bands, unit, actor):
        ordered = sorted(bands, key=lambda b: b[0])
        self.bands[notification_id] = [
            _band(v, a, unit, s.value) for (v, a), s in zip(ordered, severities_from_top(len(ordered)))
        ]


@pytest.fixture(autouse=True)
def store(monkeypatch):
    bands = _BandStore()
    monkeypatch.setattr(svc, "load_bands", bands.load)
    monkeypatch.setattr(svc, "replace_bands", bands.replace)
    refreshed = []

    async def after_settings(names):
        refreshed.append(list(names))

    monkeypatch.setattr(svc, "after_settings_write", after_settings)
    bands.refreshed = refreshed
    return bands


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
    async def test_thresholds_replace_the_band_rows(self, store):
        row = _row()
        store.seed(row)
        item = await svc.update_monitoring_catalog(
            _Session(row), "LATENCY_P95",
            MonitoringCatalogUpdate(monitoring_thresholds=_bands(12, 3, 6, active=True)),
        )
        assert [(b.band_value, b.unit, b.severity) for b in store.bands[10]] == [
            (3, "SECONDS", "INFO"), (6, "SECONDS", "WARNING"), (12, "SECONDS", "CRITICAL"),
        ]
        assert [b.value for b in item.monitoring_thresholds] == [3, 6, 12]
        assert store.refreshed == [["LATENCY_P95"]]

    async def test_two_bands_are_accepted(self, store):
        row = _row()
        store.seed(row)
        await svc.update_monitoring_catalog(
            _Session(row), "LATENCY_P95", MonitoringCatalogUpdate(monitoring_thresholds=_bands(2, 4)),
        )
        assert [b.severity for b in store.bands[10]] == ["WARNING", "CRITICAL"]

    @pytest.mark.parametrize("bands", [
        [],                                        # no band
        _bands(*range(1, 12)),                     # 11 bands
        _bands(1, 1, 2),                           # duplicate values
        _bands(0, 1, 2),                           # non-positive
        _bands(1, 2, 3, unit="PERCENT"),           # unit differs from the row's
    ])
    async def test_invalid_thresholds_are_rejected(self, store, bands):
        row = _row()
        store.seed(row)
        with pytest.raises(ValidationError):
            await svc.update_monitoring_catalog(
                _Session(row), "LATENCY_P95", MonitoringCatalogUpdate(monitoring_thresholds=bands),
            )

    async def test_percent_over_100_is_rejected(self, store):
        row = _row(name="ERROR_RATE_4XX", unit="PERCENT")
        store.seed(row)
        with pytest.raises(ValidationError):
            await svc.update_monitoring_catalog(
                _Session(row), "ERROR_RATE_4XX",
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
