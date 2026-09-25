"""app/services/notification_management/catalog_service.py

Three things here are load-bearing and would fail quietly if broken:

**thresholds is None, not {}, for a NOTIFICATION row.** The route sets
response_model_exclude_none=True specifically so this key disappears from
the wire for notifications; if the service ever returns {} instead of None
here, thresholds re-appears on every notification response.

**scope is read straight off the column**, not derived — a regression that
hardcodes or drops it would silently mis-scope every notification.

**PATCH validation** (threshold key range/count) runs before any write — a
bad payload must not partially commit.

No database — the session is faked.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.core.exceptions import EntityNotFoundError, ValidationError
from app.schemas.enums.notification_management import NotificationType
from app.schemas.notification_management.catalog import CatalogUpdate, ThresholdBand
from app.services.notification_management import catalog_service as svc


def _bands(*pairs):
    """[(percentage, active), ...] -> [ThresholdBand, ...] for CatalogUpdate payloads."""
    return [ThresholdBand(percentage=p, active=a) for p, a in pairs]


# ── fakes ────────────────────────────────────────────────────────────────────


def _row(
    id=1,
    name="TIER_ASSIGNED",
    type="NOTIFICATION",
    module="TIER",
    channels=("EMAIL",),
    scope="INSTITUTION",
    config=None,
):
    r = MagicMock()
    r.id = id
    r.name = name
    r.type = type
    r.module = module
    r.channels = list(channels)
    r.scope = scope
    r.config = config if config is not None else {}
    return r


class _Session:
    """Fake AsyncSession. ``rows`` backs a list query, ``found`` a single lookup."""

    def __init__(self, rows=None, found=None):
        self.rows = rows or []
        self.found = found
        self.commits = 0
        self.refreshed = []

    async def execute(self, stmt):
        # Honour the statement's actual WHERE value rather than always
        # returning self.rows/self.found regardless of what was asked —
        # otherwise a dropped/broken filter in the service would go
        # unnoticed here. SQLAlchemy auto-names a bound param after the
        # column it filters on plus a counter, e.g. `type_1`/`name_1`.
        params = stmt.compile().params
        result = MagicMock()
        if "type_1" in params:
            result.scalars.return_value.all.return_value = [
                row for row in self.rows if row.type == params["type_1"]
            ]
        elif "name_1" in params:
            found = self.found if self.found is not None and self.found.name == params["name_1"] else None
            result.scalar_one_or_none.return_value = found
        else:
            raise AssertionError(f"fake _Session.execute doesn't recognize this query: {stmt}")
        return result

    async def commit(self):
        self.commits += 1

    async def refresh(self, row):
        self.refreshed.append(row)


# ── the wire shape thresholds omission depends on ────────────────────────────


class TestToCatalogItem:
    def test_thresholds_is_none_for_a_notification_row(self):
        item = svc._to_catalog_item(_row(type="NOTIFICATION", config={}))
        assert item.thresholds is None

    def test_thresholds_is_none_even_if_config_somehow_carries_the_key(self):
        # Defensive: a NOTIFICATION row must never expose thresholds, even if
        # stray data ended up in its config.
        item = svc._to_catalog_item(
            _row(type="NOTIFICATION", config={"thresholds": [{"percentage": 50, "active": True}]})
        )
        assert item.thresholds is None

    def test_thresholds_is_populated_for_an_alert_row(self):
        item = svc._to_catalog_item(
            _row(
                name="QUOTA_THRESHOLD", type="ALERT", module="QUOTA", scope="GLOBAL",
                config={"thresholds": [
                    {"percentage": 70, "active": False},
                    {"percentage": 80, "active": False},
                    {"percentage": 90, "active": False},
                ]},
            )
        )
        assert item.thresholds == _bands((70, False), (80, False), (90, False))

    def test_thresholds_defaults_to_empty_list_for_an_alert_row_with_no_config(self):
        item = svc._to_catalog_item(_row(type="ALERT", config={}))
        assert item.thresholds == []

    def test_thresholds_tolerates_the_pre_migration_dict_shape(self):
        # A row that hasn't gone through a3f5c7e9b1d3 yet (ai4iplatform_core
        # has multiple outstanding Alembic heads on release-2.7, so
        # `alembic upgrade head` isn't guaranteed to have run it) must still
        # read correctly rather than 500 on `ThresholdBand(**"70")`.
        item = svc._to_catalog_item(
            _row(
                name="QUOTA_THRESHOLD", type="ALERT", module="QUOTA",
                config={"thresholds": {"70": False, "80": True, "90": False}},
            )
        )
        assert item.thresholds == _bands((70, False), (80, True), (90, False))

    def test_scope_reads_the_column(self):
        item = svc._to_catalog_item(_row(scope="GLOBAL"))
        assert item.scope == "GLOBAL"

    def test_unknown_name_falls_back_to_the_raw_enum_value(self):
        # A name not in NOTIFICATION_METADATA (shouldn't happen in practice)
        # must not 500 the whole catalog read.
        item = svc._to_catalog_item(_row(name="SOME_FUTURE_TYPE", scope="GLOBAL"))
        assert item.display_name == "SOME_FUTURE_TYPE"
        assert item.description == ""


# ── list_catalog ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestListCatalog:
    async def test_returns_projected_items_in_query_order(self):
        rows = [_row(id=1, name="TIER_ASSIGNED"), _row(id=2, name="TIER_CHANGED", scope="GLOBAL")]
        items = await svc.list_catalog(_Session(rows=rows), NotificationType.NOTIFICATION)
        assert [i.name for i in items] == ["TIER_ASSIGNED", "TIER_CHANGED"]

    async def test_empty_catalog_is_an_empty_list(self):
        items = await svc.list_catalog(_Session(rows=[]), NotificationType.NOTIFICATION)
        assert items == []

    async def test_alert_type_rows_carry_thresholds(self):
        rows = [_row(
            name="QUOTA_THRESHOLD", type="ALERT", scope="GLOBAL",
            config={"thresholds": [{"percentage": 50, "active": True}]},
        )]
        items = await svc.list_catalog(_Session(rows=rows), NotificationType.ALERT)
        assert items[0].thresholds == _bands((50, True))


# ── update_catalog ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestUpdateCatalog:
    async def test_unknown_name_is_not_found(self):
        with pytest.raises(EntityNotFoundError):
            await svc.update_catalog(_Session(found=None), "NOT_A_NAME", CatalogUpdate())

    async def test_missing_row_is_not_found(self):
        # A legal enum value with no matching row — distinct from an
        # unrecognized name entirely (test above).
        with pytest.raises(EntityNotFoundError):
            await svc.update_catalog(_Session(found=None), "QUOTA_THRESHOLD", CatalogUpdate())

    async def test_thresholds_is_rejected_for_a_notification_row(self):
        row = _row(id=1, name="TIER_ASSIGNED", type="NOTIFICATION")
        with pytest.raises(ValidationError):
            await svc.update_catalog(
                _Session(found=row), row.name, CatalogUpdate(thresholds=_bands((50, True)))
            )

    async def test_scope_is_updated(self):
        row = _row(id=1, name="TIER_ASSIGNED", type="NOTIFICATION", scope="INSTITUTION")
        session = _Session(found=row)
        item = await svc.update_catalog(
            session, row.name, CatalogUpdate(scope="GLOBAL")
        )
        assert row.scope == "GLOBAL"
        assert item.scope == "GLOBAL"

    async def test_thresholds_write_into_config_without_touching_scope(self):
        row = _row(
            id=3, name="BUDGET_THRESHOLD", type="ALERT", scope="GLOBAL",
            config={"thresholds": [
                {"percentage": 70, "active": False},
                {"percentage": 80, "active": False},
                {"percentage": 90, "active": False},
            ]},
        )
        session = _Session(found=row)
        await svc.update_catalog(
            session, row.name, CatalogUpdate(thresholds=_bands((70, True), (80, True), (90, False)))
        )
        assert row.config == {"thresholds": [
            {"percentage": 70, "active": True},
            {"percentage": 80, "active": True},
            {"percentage": 90, "active": False},
        ]}
        assert row.scope == "GLOBAL", "scope must survive untouched"

    async def test_thresholds_is_a_wholesale_replacement_not_a_merge(self):
        # No stable key to merge a partial update against once percentage
        # itself is editable — a PATCH always sends and stores exactly the
        # 3 bands it names, in full.
        row = _row(
            id=2, name="QUOTA_THRESHOLD", type="ALERT", scope="GLOBAL",
            config={"thresholds": [
                {"percentage": 50, "active": True},
                {"percentage": 75, "active": True},
                {"percentage": 90, "active": True},
            ]},
        )
        session = _Session(found=row)
        await svc.update_catalog(
            session, row.name, CatalogUpdate(thresholds=_bands((60, True), (85, False), (95, True)))
        )
        assert row.config == {"thresholds": [
            {"percentage": 60, "active": True},
            {"percentage": 85, "active": False},
            {"percentage": 95, "active": True},
        ]}

    async def test_wrong_number_of_bands_is_rejected(self):
        row = _row(id=2, name="QUOTA_THRESHOLD", type="ALERT")
        with pytest.raises(ValidationError):
            await svc.update_catalog(
                _Session(found=row), row.name,
                CatalogUpdate(thresholds=_bands((10, True), (20, True))),  # 2, not THRESHOLD_BAND_COUNT
            )

    async def test_duplicate_band_percentages_are_rejected(self):
        row = _row(id=2, name="QUOTA_THRESHOLD", type="ALERT")
        with pytest.raises(ValidationError):
            await svc.update_catalog(
                _Session(found=row), row.name,
                CatalogUpdate(thresholds=_bands((70, True), (70, False), (90, True))),
            )

    async def test_band_percentage_out_of_range_is_rejected(self):
        row = _row(id=2, name="QUOTA_THRESHOLD", type="ALERT")
        with pytest.raises(ValidationError):
            await svc.update_catalog(
                _Session(found=row), row.name,
                CatalogUpdate(thresholds=_bands((70, True), (80, True), (100, True))),
            )

    async def test_channels_are_replaced(self):
        row = _row(id=2, name="QUOTA_THRESHOLD", type="ALERT", channels=("EMAIL",))
        session = _Session(found=row)
        await svc.update_catalog(session, row.name, CatalogUpdate(channels=["EMAIL", "SMS"]))
        assert row.channels == ["EMAIL", "SMS"]

    async def test_omitted_fields_are_left_alone(self):
        row = _row(
            id=2, name="QUOTA_THRESHOLD", type="ALERT", scope="GLOBAL",
            config={"thresholds": [{"percentage": 50, "active": True}]},
        )
        session = _Session(found=row)
        await svc.update_catalog(session, row.name, CatalogUpdate())
        assert row.scope == "GLOBAL"
        assert row.config == {"thresholds": [{"percentage": 50, "active": True}]}

    async def test_commits_and_refreshes_on_success(self):
        row = _row(id=2, name="QUOTA_THRESHOLD", type="ALERT")
        session = _Session(found=row)
        await svc.update_catalog(session, row.name, CatalogUpdate(channels=["EMAIL"]))
        assert session.commits == 1
        assert session.refreshed == [row]

    async def test_updated_by_is_recorded(self):
        row = _row(id=2, name="QUOTA_THRESHOLD", type="ALERT")
        session = _Session(found=row)
        await svc.update_catalog(
            session, row.name, CatalogUpdate(channels=["EMAIL"]), updated_by="u42"
        )
        assert row.updated_by == "u42"

    async def test_updated_by_omitted_leaves_the_column_untouched(self):
        row = _row(id=2, name="QUOTA_THRESHOLD", type="ALERT")
        row.updated_by = "someone-else"
        session = _Session(found=row)
        await svc.update_catalog(session, row.name, CatalogUpdate(channels=["EMAIL"]))
        assert row.updated_by == "someone-else"

    async def test_returns_the_updated_item(self):
        row = _row(
            id=2, name="QUOTA_THRESHOLD", type="ALERT", scope="GLOBAL",
            config={"thresholds": [{"percentage": 50, "active": True}]},
        )
        session = _Session(found=row)
        item = await svc.update_catalog(
            session, row.name, CatalogUpdate(scope="GLOBAL")
        )
        assert item.scope == "GLOBAL"
        assert item.thresholds == _bands((50, True))
        assert item.id == 2
