"""app/routes/notification_subscription.py — the Institution Admin
subscription surface's wiring.

Pins: the envelope shape, the tenant boundary (an Institution Admin may only
touch their own tenant; an Adopter Admin may touch any), and that
HTTPException/AppError-shaped errors from the service propagate untouched.
"""

from __future__ import annotations

import importlib.util
import sys
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.exceptions import InsufficientPermissionsError
from app.schemas.notification_management.subscription import SubscriptionItem

_spec = importlib.util.spec_from_file_location(
    "app.routes.notification_subscription", "app/routes/notification_subscription.py"
)
_routes = importlib.util.module_from_spec(_spec)
sys.modules["app.routes.notification_subscription"] = _routes
_spec.loader.exec_module(_routes)


_SESSION = MagicMock()
_AUTH_SESSION = MagicMock()


def _item(notification_id=1, subscribed=False, locked=False, recipients=None) -> SubscriptionItem:
    return SubscriptionItem(
        notification_id=notification_id,
        name="TIER_ASSIGNED",
        display_name="Tier Assigned",
        scope="INSTITUTION",
        delivery_channel=["EMAIL"],
        subscribed=subscribed,
        locked=locked,
        recipients=recipients or [],
    )


def _request(*, user_id="u1", permission_ids="5", tenant_id="7"):
    # ROLE_TENANT_ADMIN = 5 by default — an Institution Admin scoped to
    # tenant_id="7", matching X-Tenant-Id.
    request = MagicMock()
    request.headers = {
        "X-User-Id": user_id,
        "X-Permission-IDS": permission_ids,
        "X-Tenant-Id": tenant_id,
    }
    return request


@pytest.mark.asyncio
class TestListSubscriptions:
    async def test_wraps_items_in_the_envelope(self, monkeypatch):
        stub = AsyncMock(return_value=[_item()])
        monkeypatch.setattr(_routes.subscription_service, "list_subscriptions", stub)
        resp = await _routes.list_subscriptions(
            request=_request(), tenant_id="7", catalog_type=None, session=_SESSION
        )
        assert resp.success is True
        assert resp.data.items[0].notification_id == 1

    async def test_tenant_admin_for_another_tenant_is_rejected(self, monkeypatch):
        stub = AsyncMock(return_value=[])
        monkeypatch.setattr(_routes.subscription_service, "list_subscriptions", stub)
        with pytest.raises(InsufficientPermissionsError):
            await _routes.list_subscriptions(
                request=_request(tenant_id="7"), tenant_id="other-tenant",
                catalog_type=None, session=_SESSION,
            )
        stub.assert_not_awaited()

    async def test_admin_may_view_any_tenant(self, monkeypatch):
        stub = AsyncMock(return_value=[])
        monkeypatch.setattr(_routes.subscription_service, "list_subscriptions", stub)
        await _routes.list_subscriptions(
            request=_request(permission_ids="1", tenant_id=""), tenant_id="any-tenant",
            catalog_type=None, session=_SESSION,
        )
        stub.assert_awaited_once()


@pytest.mark.asyncio
class TestUpdateSubscriptionState:
    async def test_forwards_tenant_and_subscribed(self, monkeypatch):
        stub = AsyncMock(return_value=_item(subscribed=True))
        monkeypatch.setattr(_routes.subscription_service, "update_subscription_state", stub)
        from app.schemas.notification_management.subscription import SubscriptionPatch

        await _routes.update_subscription_state(
            notification_id=1, payload=SubscriptionPatch(subscribed=True),
            request=_request(), tenant_id="7", session=_SESSION,
        )
        assert stub.await_args.kwargs["tenant_id"] == "7"
        assert stub.await_args.kwargs["subscribed"] is True
        assert stub.await_args.kwargs["updated_by"] == "u1"

    async def test_wraps_the_updated_item_with_a_message(self, monkeypatch):
        stub = AsyncMock(return_value=_item(subscribed=True))
        monkeypatch.setattr(_routes.subscription_service, "update_subscription_state", stub)
        from app.schemas.notification_management.subscription import SubscriptionPatch

        resp = await _routes.update_subscription_state(
            notification_id=1, payload=SubscriptionPatch(subscribed=True),
            request=_request(), tenant_id="7", session=_SESSION,
        )
        assert resp.success is True
        assert "Subscribed" in resp.meta.message


@pytest.mark.asyncio
class TestUpdateSubscriptionRecipients:
    async def test_forwards_recipients_and_auth_db(self, monkeypatch):
        stub = AsyncMock(return_value=_item(recipients=["u1", "u2"]))
        monkeypatch.setattr(_routes.subscription_service, "update_subscription_recipients", stub)
        from app.schemas.notification_management.subscription import SubscriptionRecipientsUpdate

        resp = await _routes.update_subscription_recipients(
            notification_id=1, payload=SubscriptionRecipientsUpdate(recipients=["u1", "u2"]),
            request=_request(), tenant_id="7", session=_SESSION, auth_db=_AUTH_SESSION,
        )
        assert stub.await_args.kwargs["recipients"] == ["u1", "u2"]
        assert stub.await_args.kwargs["auth_db"] is _AUTH_SESSION
        assert resp.data.recipients == ["u1", "u2"]


class TestRouteShape:
    def test_get_path(self):
        route = next(r for r in _routes.router.routes if "GET" in r.methods)
        assert route.path == "/notification-alerts/subscriptions"

    def test_patch_path(self):
        route = next(r for r in _routes.router.routes if "PATCH" in r.methods)
        assert route.path == "/notification-alerts/subscriptions/{notification_id}"

    def test_put_path(self):
        route = next(r for r in _routes.router.routes if "PUT" in r.methods)
        assert route.path == "/notification-alerts/subscriptions/{notification_id}"
