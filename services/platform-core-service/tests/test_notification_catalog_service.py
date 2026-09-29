"""app/services/notification_management/catalog_service.py

Load-bearing behaviour pinned here:

**Bands are rows.** Thresholds come from notification_alert_threshold, not
JSON on the catalog row. A PATCH replaces the editable bands wholesale with
severity counted from the top (highest CRITICAL, second WARNING, rest INFO).

**thresholds is None, not [], for a NOTIFICATION row.** The route drops
None keys, so a NOTIFICATION response never shows thresholds.

**The ADMIN/scope invariant.** recipient_roles["ADMIN"] is forced off while
INSTITUTION, whatever a payload or a stale stored value says.

**GLOBAL -> INSTITUTION resets every tenant's subscription** — and the
affected tenants' shared cache values are refreshed.

**Every write refreshes the shared settings snapshot** after the commit.

No database — the session and the band store are faked.
"""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from app.core.exceptions import EntityNotFoundError, ValidationError
from app.schemas.enums.notification_management import NotificationScope, NotificationType
from app.schemas.notification_management.catalog import CatalogUpdate, ThresholdBand
from app.services.notification_management import catalog_service as svc
from app.services.notification_management.thresholds import severities_from_top


def _bands(*pairs):
    """[(percentage, active), ...] -> [ThresholdBand, ...] for CatalogUpdate payloads."""
    return [ThresholdBand(percentage=p, active=a) for p, a in pairs]


def _row(
    id=1,
    name="TIER_ASSIGNED",
    type="NOTIFICATION",
    module="TIER",
    channels=("EMAIL",),
    scope="INSTITUTION",
    recipient_roles=None,
):
    r = MagicMock()
    r.id = id
    r.name = name
    r.type = type
    r.module = module
    r.channels = list(channels)
    r.scope = scope
    r.recipient_roles = recipient_roles if recipient_roles is not None else {"ADMIN": False, "TENANT ADMIN": False}
    return r


def _band(value, active=True, unit="PERCENT", severity="INFO"):
    b = MagicMock()
    b.band_value = Decimal(str(value))
    b.active = active
    b.unit = unit
    b.severity = severity
    return b


class _BandStore:
    """Stands in for thresholds.load_bands / replace_bands."""

    def __init__(self):
        self.bands = defaultdict(list)
        self.replaced = []

    async def load(self, session, notification_ids):
        return {nid: sorted(self.bands[nid], key=lambda b: b.band_value) for nid in notification_ids}

    async def replace(self, session, notification_id, bands, unit, actor):
        ordered = sorted(bands, key=lambda b: b[0])
        severities = severities_from_top(len(ordered))
        self.bands[notification_id] = [
            _band(value, active, unit, severity.value) for (value, active), severity in zip(ordered, severities)
        ]
        self.replaced.append((notification_id, ordered, unit, actor))


class _Session:
    """Fake AsyncSession. ``rows`` backs a list query, ``found`` a single lookup."""

    def __init__(self, rows=None, found=None, subscribed_tenants=("7", "9")):
        self.rows = rows or []
        self.found = found
        self.commits = 0
        self.refreshed = []
        self.subscription_resets = []
        self.subscribed_tenants = list(subscribed_tenants)

    async def execute(self, stmt):
        params = stmt.compile().params
        result = MagicMock()
        if "type_1" in params:
            result.scalars.return_value.all.return_value = [row for row in self.rows if row.type == params["type_1"]]
        elif "name_1" in params:
            found = self.found if self.found is not None and self.found.name == params["name_1"] else None
            result.scalar_one_or_none.return_value = found
        elif "subscribed" in params:
            self.subscription_resets.append(dict(params))
            result.scalars.return_value.all.return_value = self.subscribed_tenants
        else:
            raise AssertionError(f"fake _Session.execute doesn't recognize this query: {stmt}")
        return result

    async def commit(self):
        self.commits += 1

    async def refresh(self, row):
        self.refreshed.append(row)


@pytest.fixture(autouse=True)
def bands(monkeypatch):
    store = _BandStore()
    monkeypatch.setattr(svc, "load_bands", store.load)
    monkeypatch.setattr(svc, "replace_bands", store.replace)
    return store


@pytest.fixture(autouse=True)
def refreshes(monkeypatch):
    calls = {"settings": [], "subscriptions": []}

    async def after_settings(names):
        calls["settings"].append(list(names))

    async def after_subscriptions(tenant_ids):
        calls["subscriptions"].append(list(tenant_ids))

    monkeypatch.setattr(svc, "after_settings_write", after_settings)
    monkeypatch.setattr(svc, "after_subscription_write", after_subscriptions)
    return calls


# ── projection ───────────────────────────────────────────────────────────────


class TestToCatalogItem:
    def test_thresholds_is_none_for_a_notification_row(self):
        item = svc._to_catalog_item(_row(type="NOTIFICATION"), [_band(100)])
        assert item.thresholds is None
        assert item.monitoring_thresholds is None

    def test_thresholds_are_read_from_band_rows_for_an_alert_row(self):
        item = svc._to_catalog_item(
            _row(name="QUOTA_THRESHOLD", type="ALERT", module="QUOTA", scope="GLOBAL"),
            [_band(70, False), _band(80, True), _band(90, False)],
        )
        assert [(b.percentage, b.active) for b in item.thresholds] == [(70, False), (80, True), (90, False)]

    def test_alert_row_with_no_bands_is_an_empty_list(self):
        item = svc._to_catalog_item(_row(name="QUOTA_THRESHOLD", type="ALERT", module="QUOTA", scope="GLOBAL"))
        assert item.thresholds == []

    def test_monitoring_row_carries_value_and_unit(self):
        item = svc._to_catalog_item(
            _row(id=12, name="LATENCY_P95", type="MONITORING", module="MONITORING", scope="GLOBAL",
                 recipient_roles={"ADMIN": True, "MODERATOR": False}),
            [_band(2, unit="SECONDS"), _band(Decimal("5.5"), True, "SECONDS")],
        )
        assert item.thresholds is None
        assert [(b.value, b.unit.value, b.active) for b in item.monitoring_thresholds] == [
            (2, "SECONDS", True), (5.5, "SECONDS", True),
        ]
        assert item.display_name == "P95 Latency"

    def test_recipient_roles_and_scope_are_the_stored_columns(self):
        item = svc._to_catalog_item(_row(scope="INSTITUTION", recipient_roles={"ADMIN": True, "TENANT ADMIN": True}))
        assert item.recipient_roles == {"ADMIN": True, "TENANT ADMIN": True}
        assert item.scope.value == "INSTITUTION"


# ── list ─────────────────────────────────────────────────────────────────────


class TestListCatalog:
    @pytest.mark.asyncio
    async def test_filters_by_type_in_query_order(self, bands):
        rows = [
            _row(id=1, name="TIER_ASSIGNED"),
            _row(id=8, name="QUOTA_THRESHOLD", type="ALERT", module="QUOTA", scope="GLOBAL"),
            _row(id=2, name="TIER_CHANGED", scope="GLOBAL"),
        ]
        bands.bands[8] = [_band(80)]
        items = await svc.list_catalog(_Session(rows=rows), NotificationType.NOTIFICATION)
        assert [i.name for i in items] == ["TIER_ASSIGNED", "TIER_CHANGED"]

        alerts = await svc.list_catalog(_Session(rows=rows), NotificationType.ALERT)
        assert [b.percentage for b in alerts[0].thresholds] == [80]

    @pytest.mark.asyncio
    async def test_empty_catalog_is_an_empty_list(self):
        assert await svc.list_catalog(_Session(rows=[]), NotificationType.ALERT) == []


# ── update ───────────────────────────────────────────────────────────────────


def _alert(**kwargs):
    base = dict(id=8, name="QUOTA_THRESHOLD", type="ALERT", module="QUOTA", scope="GLOBAL")
    base.update(kwargs)
    return _row(**base)


class TestUpdateCatalog:
    @pytest.mark.asyncio
    async def test_unknown_name_is_not_found(self):
        with pytest.raises(EntityNotFoundError):
            await svc.update_catalog(_Session(), "NOT_A_NAME", CatalogUpdate())

    @pytest.mark.asyncio
    async def test_missing_row_is_not_found(self):
        with pytest.raises(EntityNotFoundError):
            await svc.update_catalog(_Session(found=None), "TIER_ASSIGNED", CatalogUpdate())

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "payload",
        [
            CatalogUpdate(recipient_roles={"MODERATOR": True}),
            CatalogUpdate(scope=NotificationScope.INSTITUTION),
            CatalogUpdate(channels=["EMAIL", "SMS"]),
        ],
        ids=["recipient_roles", "scope", "channels"],
    )
    async def test_metering_patch_404s_a_monitoring_row_and_saves_nothing(self, payload):
        # Monitoring rows are written only through PATCH /monitoring-catalog/{name}.
        row = _row(id=12, name="LATENCY_P95", type="MONITORING", module="MONITORING", scope="GLOBAL",
                   recipient_roles={"ADMIN": True, "MODERATOR": False})
        session = _Session(found=row)
        with pytest.raises(EntityNotFoundError):
            await svc.update_catalog(session, row.name, payload)
        assert row.scope == "GLOBAL"
        assert row.recipient_roles == {"ADMIN": True, "MODERATOR": False}

    @pytest.mark.asyncio
    async def test_thresholds_are_rejected_for_a_notification_row(self):
        row = _row()
        with pytest.raises(ValidationError):
            await svc.update_catalog(_Session(found=row), row.name, CatalogUpdate(thresholds=_bands((50, True))))

    @pytest.mark.asyncio
    async def test_thresholds_replace_the_band_rows_with_severity_from_the_top(self, bands, refreshes):
        row = _alert()
        item = await svc.update_catalog(
            _Session(found=row), row.name, CatalogUpdate(thresholds=_bands((90, True), (50, False), (75, True))),
            updated_by="admin-1",
        )
        notification_id, ordered, unit, actor = bands.replaced[0]
        assert notification_id == 8 and unit == "PERCENT" and actor == "admin-1"
        assert [(int(v), a) for v, a in ordered] == [(50, False), (75, True), (90, True)]
        assert [b.severity for b in bands.bands[8]] == ["INFO", "WARNING", "CRITICAL"]
        assert [(b.percentage, b.active) for b in item.thresholds] == [(50, False), (75, True), (90, True)]
        assert refreshes["settings"] == [["QUOTA_THRESHOLD"]]

    @pytest.mark.asyncio
    @pytest.mark.parametrize("count", [1, 2, 10])
    async def test_one_to_ten_bands_are_accepted(self, bands, count):
        row = _alert()
        payload = CatalogUpdate(thresholds=_bands(*[(p, True) for p in range(1, count + 1)]))
        await svc.update_catalog(_Session(found=row), row.name, payload)
        assert len(bands.bands[8]) == count

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "pairs",
        [
            [],
            [(p, True) for p in range(1, 12)],   # 11 bands
            [(50, True), (50, False)],            # duplicate
            [(0, True)],                          # below range
            [(100, True)],                        # above range
        ],
    )
    async def test_invalid_band_lists_are_rejected(self, bands, pairs):
        row = _alert()
        with pytest.raises(ValidationError):
            await svc.update_catalog(_Session(found=row), row.name, CatalogUpdate(thresholds=_bands(*pairs)))
        assert bands.replaced == []

    @pytest.mark.asyncio
    async def test_scope_is_updated(self):
        row = _row(scope="INSTITUTION")
        item = await svc.update_catalog(_Session(found=row), row.name, CatalogUpdate(scope="GLOBAL"))
        assert item.scope.value == "GLOBAL"

    @pytest.mark.asyncio
    async def test_partial_recipient_roles_update_keeps_other_keys(self):
        row = _row(scope="GLOBAL", recipient_roles={"ADMIN": True, "TENANT ADMIN": False})
        item = await svc.update_catalog(
            _Session(found=row), row.name, CatalogUpdate(recipient_roles={"TENANT ADMIN": True})
        )
        assert item.recipient_roles == {"ADMIN": True, "TENANT ADMIN": True}

    @pytest.mark.asyncio
    async def test_illegal_recipient_role_is_rejected(self):
        row = _row()
        with pytest.raises(ValidationError):
            await svc.update_catalog(_Session(found=row), row.name, CatalogUpdate(recipient_roles={"MODERATOR": True}))

    @pytest.mark.asyncio
    async def test_channels_are_replaced(self):
        row = _row()
        item = await svc.update_catalog(_Session(found=row), row.name, CatalogUpdate(channels=["EMAIL", "SMS"]))
        assert [c.value for c in item.channels] == ["EMAIL", "SMS"]

    @pytest.mark.asyncio
    async def test_commits_refreshes_and_records_updated_by(self, refreshes):
        row = _row()
        session = _Session(found=row)
        await svc.update_catalog(session, row.name, CatalogUpdate(channels=["EMAIL"]), updated_by="admin-1")
        assert session.commits == 1 and session.refreshed == [row]
        assert row.updated_by == "admin-1"
        assert refreshes["settings"] == [["TIER_ASSIGNED"]]


class TestAdminScopeInvariant:
    @pytest.mark.asyncio
    async def test_scope_change_to_institution_clears_admin(self):
        row = _row(scope="GLOBAL", recipient_roles={"ADMIN": True, "TENANT ADMIN": True})
        item = await svc.update_catalog(_Session(found=row), row.name, CatalogUpdate(scope="INSTITUTION"))
        assert item.recipient_roles["ADMIN"] is False

    @pytest.mark.asyncio
    async def test_payload_cannot_force_admin_true_while_institution(self):
        row = _row(scope="INSTITUTION")
        item = await svc.update_catalog(_Session(found=row), row.name, CatalogUpdate(recipient_roles={"ADMIN": True}))
        assert item.recipient_roles["ADMIN"] is False

    @pytest.mark.asyncio
    async def test_admin_can_be_selected_while_global(self):
        row = _row(scope="GLOBAL")
        item = await svc.update_catalog(_Session(found=row), row.name, CatalogUpdate(recipient_roles={"ADMIN": True}))
        assert item.recipient_roles["ADMIN"] is True


class TestScopeTransitionResetsTenantSubscriptions:
    @pytest.mark.asyncio
    async def test_global_to_institution_resets_every_tenant_and_refreshes_them(self, refreshes):
        row = _row(id=7, scope="GLOBAL")
        session = _Session(found=row, subscribed_tenants=["3", "4"])
        await svc.update_catalog(session, row.name, CatalogUpdate(scope="INSTITUTION"), updated_by="admin-1")
        assert len(session.subscription_resets) == 1
        reset = session.subscription_resets[0]
        assert reset["subscribed"] is False and reset["notification_id_1"] == 7
        assert reset["updated_by"] == "admin-1"
        assert "recipients" not in reset
        assert refreshes["subscriptions"] == [["3", "4"]]

    @pytest.mark.asyncio
    async def test_institution_to_global_does_not_reset(self, refreshes):
        row = _row(scope="INSTITUTION")
        session = _Session(found=row)
        await svc.update_catalog(session, row.name, CatalogUpdate(scope="GLOBAL"))
        assert session.subscription_resets == [] and refreshes["subscriptions"] == []

    @pytest.mark.asyncio
    async def test_resending_the_same_scope_does_not_reset(self):
        row = _row(scope="INSTITUTION")
        session = _Session(found=row)
        await svc.update_catalog(session, row.name, CatalogUpdate(scope="INSTITUTION"))
        assert session.subscription_resets == []

    @pytest.mark.asyncio
    async def test_scenario_3_reverting_to_institution_resets_again(self):
        row = _row(scope="INSTITUTION")
        session = _Session(found=row)
        await svc.update_catalog(session, row.name, CatalogUpdate(scope="GLOBAL"))
        await svc.update_catalog(session, row.name, CatalogUpdate(scope="INSTITUTION"))
        assert len(session.subscription_resets) == 1
