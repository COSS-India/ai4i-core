"""app/services/notification_management/subscription_service.py

Load-bearing behavior:

**A GLOBAL-scope row's effective subscription is always on and locked**,
computed from the catalog row's own scope, never from the stored
tenant_notification_subscription bit — and that stored bit must never be
touched by a mere read.

**Toggling subscribed is rejected for a GLOBAL-scope row** (409) — there is
no unsubscribe option to change while a row is GLOBAL.

**Recipients are wholesale-replaced and validated against the tenant** —
an id that doesn't resolve to an active user of this same institution must
be rejected, not silently accepted.

No database — both sessions (primary + auth) are faked.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.core.exceptions import AppError, EntityNotFoundError, ValidationError
from app.models.notification_management.tenant_notification_subscription import (
    TenantNotificationSubscription,
)
from app.services.notification_management import subscription_service as svc


def _catalog_row(id=1, name="TIER_ASSIGNED", type="NOTIFICATION", scope="INSTITUTION", channels=("EMAIL",)):
    r = MagicMock()
    r.id = id
    r.name = name
    r.type = type
    r.scope = scope
    r.channels = list(channels)
    return r


def _sub_row(notification_id=1, tenant_id="7", subscribed=False, recipients=None):
    row = TenantNotificationSubscription(
        notification_id=notification_id,
        tenant_id=tenant_id,
        subscribed=subscribed,
        recipients=list(recipients or []),
    )
    return row


class _Session:
    """Fake primary AsyncSession. ``catalog_rows`` backs the catalog list/get
    query, ``sub_rows`` the tenant_notification_subscription query."""

    def __init__(self, catalog_rows=None, sub_rows=None):
        self.catalog_rows = catalog_rows or []
        self.sub_rows = sub_rows or []
        self.added = []
        self.commits = 0
        self.refreshed = []

    async def execute(self, stmt):
        params = stmt.compile().params
        result = MagicMock()
        if "id_1" in params:
            match = next((r for r in self.catalog_rows if r.id == params["id_1"]), None)
            result.scalar_one_or_none.return_value = match
        elif "tenant_id_1" in params and "notification_id_1" in params:
            match = next(
                (
                    r for r in self.sub_rows
                    if r.notification_id == params["notification_id_1"] and r.tenant_id == params["tenant_id_1"]
                ),
                None,
            )
            result.scalar_one_or_none.return_value = match
        elif "tenant_id_1" in params:
            result.scalars.return_value.all.return_value = [
                r for r in self.sub_rows if r.tenant_id == params["tenant_id_1"]
            ]
        elif "type_1" in params:
            result.scalars.return_value.all.return_value = [
                r for r in self.catalog_rows if r.type == params["type_1"]
            ]
        else:
            result.scalars.return_value.all.return_value = list(self.catalog_rows)
        return result

    def add(self, row):
        self.added.append(row)
        self.sub_rows.append(row)

    async def commit(self):
        self.commits += 1

    async def refresh(self, row):
        self.refreshed.append(row)


class _AuthSession:
    def __init__(self, active_user_ids):
        self.active_user_ids = set(active_user_ids)

    async def execute(self, stmt, params):
        recipients = params["recipients"]
        result = MagicMock()
        result.all.return_value = [(uid,) for uid in recipients if uid in self.active_user_ids]
        return result


@pytest.mark.asyncio
class TestListSubscriptions:
    async def test_global_row_is_always_subscribed_and_locked(self):
        session = _Session(catalog_rows=[_catalog_row(id=1, scope="GLOBAL")], sub_rows=[])
        items = await svc.list_subscriptions(session, tenant_id="7")
        assert items[0].subscribed is True
        assert items[0].locked is True

    async def test_institution_row_reads_the_stored_bit(self):
        session = _Session(
            catalog_rows=[_catalog_row(id=1, scope="INSTITUTION")],
            sub_rows=[_sub_row(notification_id=1, tenant_id="7", subscribed=True)],
        )
        items = await svc.list_subscriptions(session, tenant_id="7")
        assert items[0].subscribed is True
        assert items[0].locked is False

    async def test_missing_subscription_row_reads_as_unsubscribed(self):
        # A tenant created after the seed migration has no row yet — must
        # not 500, must read as unsubscribed with no recipients.
        session = _Session(catalog_rows=[_catalog_row(id=1, scope="INSTITUTION")], sub_rows=[])
        items = await svc.list_subscriptions(session, tenant_id="7")
        assert items[0].subscribed is False
        assert items[0].recipients == []

    async def test_delivery_channel_and_notification_id_are_present(self):
        session = _Session(catalog_rows=[_catalog_row(id=42, channels=("EMAIL",))], sub_rows=[])
        items = await svc.list_subscriptions(session, tenant_id="7")
        assert items[0].notification_id == 42
        assert items[0].delivery_channel == ["EMAIL"]

    async def test_another_tenants_row_is_not_leaked(self):
        session = _Session(
            catalog_rows=[_catalog_row(id=1, scope="INSTITUTION")],
            sub_rows=[_sub_row(notification_id=1, tenant_id="other-tenant", subscribed=True)],
        )
        items = await svc.list_subscriptions(session, tenant_id="7")
        assert items[0].subscribed is False


@pytest.mark.asyncio
class TestUpdateSubscriptionState:
    async def test_unknown_notification_id_is_not_found(self):
        session = _Session(catalog_rows=[])
        with pytest.raises(EntityNotFoundError):
            await svc.update_subscription_state(
                session, tenant_id="7", notification_id=999, subscribed=True
            )

    async def test_global_scope_toggle_is_rejected(self):
        session = _Session(catalog_rows=[_catalog_row(id=1, scope="GLOBAL")], sub_rows=[])
        with pytest.raises(AppError) as exc_info:
            await svc.update_subscription_state(
                session, tenant_id="7", notification_id=1, subscribed=False
            )
        assert exc_info.value.status_code == 409

    async def test_subscribing_creates_a_row_when_none_existed(self):
        session = _Session(catalog_rows=[_catalog_row(id=1, scope="INSTITUTION")], sub_rows=[])
        item = await svc.update_subscription_state(
            session, tenant_id="7", notification_id=1, subscribed=True, updated_by="u1"
        )
        assert item.subscribed is True
        assert session.added[0].tenant_id == "7"
        assert session.added[0].updated_by == "u1"
        assert session.commits == 1

    async def test_unsubscribing_flips_an_existing_row(self):
        existing = _sub_row(notification_id=1, tenant_id="7", subscribed=True)
        session = _Session(catalog_rows=[_catalog_row(id=1, scope="INSTITUTION")], sub_rows=[existing])
        item = await svc.update_subscription_state(
            session, tenant_id="7", notification_id=1, subscribed=False
        )
        assert item.subscribed is False
        assert existing.subscribed is False
        assert session.added == [], "must update the existing row, not create a second one"


@pytest.mark.asyncio
class TestUpdateSubscriptionRecipients:
    async def test_unknown_notification_id_is_not_found(self):
        session = _Session(catalog_rows=[])
        with pytest.raises(EntityNotFoundError):
            await svc.update_subscription_recipients(
                session, tenant_id="7", notification_id=999, recipients=[], auth_db=_AuthSession([])
            )

    async def test_recipient_not_in_tenant_is_rejected(self):
        session = _Session(catalog_rows=[_catalog_row(id=1)], sub_rows=[])
        auth_db = _AuthSession(active_user_ids=["u1"])
        with pytest.raises(ValidationError):
            await svc.update_subscription_recipients(
                session, tenant_id="7", notification_id=1,
                recipients=["u1", "not-in-tenant"], auth_db=auth_db,
            )
        assert session.commits == 0, "a rejected recipient must not partially commit"

    async def test_valid_recipients_replace_wholesale(self):
        existing = _sub_row(notification_id=1, tenant_id="7", recipients=["old-admin"])
        session = _Session(catalog_rows=[_catalog_row(id=1)], sub_rows=[existing])
        auth_db = _AuthSession(active_user_ids=["u1", "u2"])
        item = await svc.update_subscription_recipients(
            session, tenant_id="7", notification_id=1, recipients=["u1", "u2"], auth_db=auth_db,
        )
        assert item.recipients == ["u1", "u2"]
        assert existing.recipients == ["u1", "u2"]

    async def test_empty_recipients_list_skips_validation(self):
        session = _Session(catalog_rows=[_catalog_row(id=1)], sub_rows=[])
        item = await svc.update_subscription_recipients(
            session, tenant_id="7", notification_id=1, recipients=[], auth_db=None,
        )
        assert item.recipients == []

    async def test_recipients_survive_regardless_of_current_scope(self):
        # AC: recipients added while a row is Global-scope stay intact if it
        # later reverts to Institution scope — recipients edits must not be
        # scope-gated.
        session = _Session(catalog_rows=[_catalog_row(id=1, scope="GLOBAL")], sub_rows=[])
        auth_db = _AuthSession(active_user_ids=["u1"])
        item = await svc.update_subscription_recipients(
            session, tenant_id="7", notification_id=1, recipients=["u1"], auth_db=auth_db,
        )
        assert item.recipients == ["u1"]
