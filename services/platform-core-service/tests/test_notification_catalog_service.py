"""app/services/notification_management/catalog_service.py

Three things here are load-bearing and would fail quietly if broken:

**Column separation.** recipient_roles is its own jsonb column, config is
thresholds-only. A regression that writes recipient_roles back into config
(or vice versa) would silently resurrect the old single-blob shape and lose
data on the next PATCH that only sets the other field.

**thresholds is None, not {}, for a NOTIFICATION row.** The route sets
response_model_exclude_none=True specifically so this key disappears from
the wire for notifications; if the service ever returns {} instead of None
here, thresholds re-appears on every notification response.

**PATCH validation** (legal recipient roles per ALERT name, threshold key
range/count) runs before any write — a bad payload must not partially
commit.

No database — the session is faked.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.core.exceptions import EntityNotFoundError, ValidationError
from app.schemas.enums.notification_management import NotificationType
from app.schemas.notification_management.catalog import CatalogUpdate
from app.services.notification_management import catalog_service as svc


# ── fakes ────────────────────────────────────────────────────────────────────


def _row(
    id=1,
    name="TIER_ASSIGNED",
    type="NOTIFICATION",
    module="TIER",
    channels=("EMAIL",),
    recipient_roles=None,
    config=None,
):
    r = MagicMock()
    r.id = id
    r.name = name
    r.type = type
    r.module = module
    r.channels = list(channels)
    r.recipient_roles = recipient_roles if recipient_roles is not None else {}
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
            _row(type="NOTIFICATION", config={"thresholds": {"50": True}})
        )
        assert item.thresholds is None

    def test_thresholds_is_populated_for_an_alert_row(self):
        item = svc._to_catalog_item(
            _row(
                name="QUOTA_THRESHOLD", type="ALERT", module="QUOTA",
                config={"thresholds": {"50": False, "75": False, "90": False}},
            )
        )
        assert item.thresholds == {"50": False, "75": False, "90": False}

    def test_thresholds_defaults_to_empty_dict_for_an_alert_row_with_no_config(self):
        item = svc._to_catalog_item(_row(type="ALERT", config={}))
        assert item.thresholds == {}

    def test_recipient_roles_reads_the_column_not_config(self):
        item = svc._to_catalog_item(
            _row(
                recipient_roles={"TENANT ADMIN": True},
                config={"recipient_roles": {"ADMIN": True}},  # stale shape, must be ignored
            )
        )
        assert item.recipient_roles == {"TENANT ADMIN": True}

    def test_unknown_name_falls_back_to_the_raw_enum_value(self):
        # A name not in NOTIFICATION_METADATA (shouldn't happen in practice)
        # must not 500 the whole catalog read.
        item = svc._to_catalog_item(_row(name="SOME_FUTURE_TYPE"))
        assert item.display_name == "SOME_FUTURE_TYPE"
        assert item.description == ""


# ── list_catalog ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestListCatalog:
    async def test_returns_projected_items_in_query_order(self):
        rows = [_row(id=1, name="TIER_ASSIGNED"), _row(id=2, name="TIER_CHANGED")]
        items = await svc.list_catalog(_Session(rows=rows), NotificationType.NOTIFICATION)
        assert [i.name for i in items] == ["TIER_ASSIGNED", "TIER_CHANGED"]

    async def test_empty_catalog_is_an_empty_list(self):
        items = await svc.list_catalog(_Session(rows=[]), NotificationType.NOTIFICATION)
        assert items == []

    async def test_alert_type_rows_carry_thresholds(self):
        rows = [_row(name="QUOTA_THRESHOLD", type="ALERT", config={"thresholds": {"50": True}})]
        items = await svc.list_catalog(_Session(rows=rows), NotificationType.ALERT)
        assert items[0].thresholds == {"50": True}


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
                _Session(found=row), row.name, CatalogUpdate(thresholds={"50": True})
            )

    async def test_legal_recipient_role_allowed_for_a_notification_row(self):
        row = _row(id=1, name="TIER_ASSIGNED", type="NOTIFICATION")
        session = _Session(found=row)
        item = await svc.update_catalog(
            session, row.name, CatalogUpdate(recipient_roles={"TENANT ADMIN": True})
        )
        assert row.recipient_roles == {"TENANT ADMIN": True}
        assert item.thresholds is None

    async def test_illegal_recipient_role_is_rejected_for_a_notification_row(self):
        # NOTIFICATION rows are restricted to ADMIN / TENANT ADMIN too, same
        # as ALERT rows — a typo'd or unsupported role must not silently
        # pass and leave the notification addressed to nobody.
        row = _row(id=1, name="TIER_ASSIGNED", type="NOTIFICATION")
        with pytest.raises(ValidationError):
            await svc.update_catalog(
                _Session(found=row), row.name, CatalogUpdate(recipient_roles={"TENANT_ADMIN": True})
            )

    async def test_recipient_roles_write_to_the_column_not_config(self):
        row = _row(id=2, name="QUOTA_THRESHOLD", type="ALERT", config={"thresholds": {"50": False}})
        session = _Session(found=row)
        await svc.update_catalog(
            session, row.name, CatalogUpdate(recipient_roles={"TENANT ADMIN": True})
        )
        assert row.recipient_roles == {"TENANT ADMIN": True}
        assert row.config == {"thresholds": {"50": False}}, "thresholds must survive untouched"

    async def test_illegal_recipient_role_is_rejected(self):
        # Per LEGAL_RECIPIENT_ROLES, only TENANT ADMIN / ADMIN are legal
        # for QUOTA_THRESHOLD.
        row = _row(id=2, name="QUOTA_THRESHOLD", type="ALERT")
        with pytest.raises(ValidationError):
            await svc.update_catalog(
                _Session(found=row), row.name, CatalogUpdate(recipient_roles={"MODERATOR": True})
            )

    async def test_thresholds_write_into_config_without_touching_recipient_roles(self):
        row = _row(
            id=3, name="BUDGET_THRESHOLD", type="ALERT",
            recipient_roles={"ADMIN": True}, config={"thresholds": {"50": False}},
        )
        session = _Session(found=row)
        await svc.update_catalog(
            session, row.name, CatalogUpdate(thresholds={"50": True, "75": True})
        )
        assert row.config == {"thresholds": {"50": True, "75": True}}
        assert row.recipient_roles == {"ADMIN": True}, "recipient_roles must survive untouched"

    async def test_partial_recipient_roles_update_keeps_other_keys_at_their_current_value(self):
        # Existing row already has both legal roles set true. A PATCH naming
        # only one of them must not touch the other — it stays True, it
        # isn't reset to False just for being omitted.
        row = _row(
            id=2, name="QUOTA_THRESHOLD", type="ALERT",
            recipient_roles={"TENANT ADMIN": True, "ADMIN": True},
        )
        session = _Session(found=row)
        await svc.update_catalog(
            session, row.name, CatalogUpdate(recipient_roles={"ADMIN": False})
        )
        assert row.recipient_roles == {"TENANT ADMIN": True, "ADMIN": False}

    async def test_partial_thresholds_update_keeps_other_keys_at_their_current_value(self):
        row = _row(
            id=2, name="QUOTA_THRESHOLD", type="ALERT",
            config={"thresholds": {"50": True, "75": True, "90": True}},
        )
        session = _Session(found=row)
        await svc.update_catalog(session, row.name, CatalogUpdate(thresholds={"90": False}))
        assert row.config == {"thresholds": {"50": True, "75": True, "90": False}}

    async def test_too_many_threshold_keys_is_rejected(self):
        row = _row(id=2, name="QUOTA_THRESHOLD", type="ALERT")
        thresholds = {str(n): True for n in (10, 20, 30, 40, 50, 60)}  # 6 > MAX_THRESHOLD_KEYS
        with pytest.raises(ValidationError):
            await svc.update_catalog(
                _Session(found=row), row.name, CatalogUpdate(thresholds=thresholds)
            )

    async def test_threshold_key_out_of_range_is_rejected(self):
        row = _row(id=2, name="QUOTA_THRESHOLD", type="ALERT")
        with pytest.raises(ValidationError):
            await svc.update_catalog(
                _Session(found=row), row.name, CatalogUpdate(thresholds={"100": True})
            )

    async def test_non_digit_threshold_key_is_rejected(self):
        row = _row(id=2, name="QUOTA_THRESHOLD", type="ALERT")
        with pytest.raises(ValidationError):
            await svc.update_catalog(
                _Session(found=row), row.name, CatalogUpdate(thresholds={"fifty": True})
            )

    async def test_channels_are_replaced(self):
        row = _row(id=2, name="QUOTA_THRESHOLD", type="ALERT", channels=("EMAIL",))
        session = _Session(found=row)
        await svc.update_catalog(session, row.name, CatalogUpdate(channels=["EMAIL", "SMS"]))
        assert row.channels == ["EMAIL", "SMS"]

    async def test_omitted_fields_are_left_alone(self):
        row = _row(
            id=2, name="QUOTA_THRESHOLD", type="ALERT",
            recipient_roles={"ADMIN": True}, config={"thresholds": {"50": True}},
        )
        session = _Session(found=row)
        await svc.update_catalog(session, row.name, CatalogUpdate())
        assert row.recipient_roles == {"ADMIN": True}
        assert row.config == {"thresholds": {"50": True}}

    async def test_commits_and_refreshes_on_success(self):
        row = _row(id=2, name="QUOTA_THRESHOLD", type="ALERT")
        session = _Session(found=row)
        await svc.update_catalog(session, row.name, CatalogUpdate(recipient_roles={"ADMIN": True}))
        assert session.commits == 1
        assert session.refreshed == [row]

    async def test_updated_by_is_recorded(self):
        row = _row(id=2, name="QUOTA_THRESHOLD", type="ALERT")
        session = _Session(found=row)
        await svc.update_catalog(
            session, row.name, CatalogUpdate(recipient_roles={"ADMIN": True}), updated_by="u42"
        )
        assert row.updated_by == "u42"

    async def test_updated_by_omitted_leaves_the_column_untouched(self):
        row = _row(id=2, name="QUOTA_THRESHOLD", type="ALERT")
        row.updated_by = "someone-else"
        session = _Session(found=row)
        await svc.update_catalog(session, row.name, CatalogUpdate(recipient_roles={"ADMIN": True}))
        assert row.updated_by == "someone-else"

    async def test_returns_the_updated_item(self):
        row = _row(id=2, name="QUOTA_THRESHOLD", type="ALERT", config={"thresholds": {"50": True}})
        session = _Session(found=row)
        item = await svc.update_catalog(
            session, row.name, CatalogUpdate(recipient_roles={"ADMIN": True})
        )
        assert item.recipient_roles == {"ADMIN": True}
        assert item.thresholds == {"50": True}
        assert item.id == 2
