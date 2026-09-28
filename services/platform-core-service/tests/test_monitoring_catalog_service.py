"""app/services/notification_management/monitoring_catalog_service.py

Load-bearing behaviour: selecting a role resolves it to concrete user ids
and rebuilds monitoring_alert_recipient wholesale; a failed resolution
leaves the row untouched; thresholds are validated against the row's own
fixed unit; non-monitoring names are a 404 here.

No database — both sessions are faked.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.exceptions import AppError, EntityNotFoundError, ValidationError
from app.models.notification_management.monitoring_alert_recipient import (
    MonitoringAlertRecipient,
)
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
    """Fake core-db session: a row lookup, a recipient delete, recipient
    inserts via add_all, and the recipient id listing afterwards."""

    def __init__(self, row):
        self.row = row
        self.recipients: list[MonitoringAlertRecipient] = []
        self.commits = 0

    async def execute(self, stmt):
        sql = str(stmt)
        result = MagicMock()
        if sql.startswith("DELETE FROM monitoring_alert_recipient"):
            self.recipients = []
        elif "FROM configs_notification_alert" in sql:
            result.scalar_one_or_none.return_value = self.row
        elif "FROM monitoring_alert_recipient" in sql:
            result.scalars.return_value.all.return_value = [r.user_id for r in self.recipients]
        else:
            raise AssertionError(f"unexpected query: {sql}")
        return result

    def add_all(self, objs):
        self.recipients.extend(objs)

    async def commit(self):
        self.commits += 1

    async def refresh(self, row):
        pass


def _auth_db(*users):
    """users: (user_id, role) pairs the auth DB returns for the role query."""
    db = MagicMock()
    result = MagicMock()
    result.all.return_value = [SimpleNamespace(user_id=u, role=r) for u, r in users]
    db.execute = AsyncMock(return_value=result)
    return db


def _bands(*values, unit="SECONDS", active=False):
    return [MonitoringThresholdBand(value=v, unit=unit, active=active) for v in values]


@pytest.fixture(autouse=True)
def _no_redis():
    with patch.object(svc, "get_redis_client", return_value=MagicMock(publish=AsyncMock())):
        yield


@pytest.mark.asyncio
class TestRecipients:
    async def test_selecting_moderator_saves_admin_and_moderator_user_ids(self):
        session = _Session(_row())
        auth_db = _auth_db(("1", "ADMIN"), ("2", "ADMIN"), ("7", "MODERATOR"))
        item = await svc.update_monitoring_catalog(
            session, "LATENCY_P95", MonitoringCatalogUpdate(recipient_roles={"MODERATOR": True}),
            auth_db=auth_db, updated_by="u1",
        )
        params = auth_db.execute.call_args.args[1]
        assert params == {"roles": ["ADMIN", "MODERATOR"]}
        assert [(r.user_id, r.role) for r in session.recipients] == [
            ("1", "ADMIN"), ("2", "ADMIN"), ("7", "MODERATOR"),
        ]
        assert item.recipients == ["1", "2", "7"]
        assert item.recipient_roles == {"ADMIN": True, "MODERATOR": True}

    async def test_user_with_both_roles_is_saved_once(self):
        session = _Session(_row(recipient_roles={"ADMIN": True, "MODERATOR": True}))
        auth_db = _auth_db(("1", "ADMIN"), ("1", "MODERATOR"))
        item = await svc.update_monitoring_catalog(
            session, "LATENCY_P95", MonitoringCatalogUpdate(recipient_roles={}), auth_db=auth_db,
        )
        assert item.recipients == ["1"]
        assert session.recipients[0].role == "ADMIN"

    async def test_deselecting_every_role_clears_recipients_without_hitting_auth_db(self):
        session = _Session(_row())
        session.recipients = [MonitoringAlertRecipient(notification_id=10, user_id="1", role="ADMIN")]
        item = await svc.update_monitoring_catalog(
            session, "LATENCY_P95", MonitoringCatalogUpdate(recipient_roles={"ADMIN": False}), auth_db=None,
        )
        assert item.recipients == []

    async def test_tenant_admin_is_rejected(self):
        with pytest.raises(ValidationError):
            await svc.update_monitoring_catalog(
                _Session(_row()), "LATENCY_P95",
                MonitoringCatalogUpdate(recipient_roles={"TENANT ADMIN": True}), auth_db=_auth_db(),
            )

    async def test_missing_auth_db_is_503_and_leaves_row_untouched(self):
        row = _row(recipient_roles={"ADMIN": False, "MODERATOR": False})
        session = _Session(row)
        with pytest.raises(AppError) as exc:
            await svc.update_monitoring_catalog(
                session, "LATENCY_P95", MonitoringCatalogUpdate(recipient_roles={"ADMIN": True}), auth_db=None,
            )
        assert exc.value.status_code == 503
        assert row.recipient_roles == {"ADMIN": False, "MODERATOR": False}
        assert session.commits == 0


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
