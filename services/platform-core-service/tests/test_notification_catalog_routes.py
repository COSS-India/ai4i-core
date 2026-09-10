"""app/routes/notification.py and app/routes/alert_catalog.py — the catalog
read/write surface.

The service layer is covered in test_notification_catalog_service.py. What is
left to pin here is the wiring, which is exactly what a refactor drops
silently:

* the envelope shape — ``data.items`` for the list, ``data``/``meta`` for the
  PATCH;
* ``type`` being a required query parameter aliased from ``catalog_type``,
  and it reaching the service unchanged;
* ``response_model_exclude_none=True`` on the GET route, which is what
  actually drops ``thresholds`` from a NOTIFICATION row's JSON rather than
  sending it as ``null``;
* HTTPException-shaped errors from the service propagating untouched.

Route modules are loaded by file path because app/routes/__init__.py eagerly
imports every route plus ai4i_core.bootstrap.versioning, which this suite's
conftest does not stub — the same approach test_inference_types_routes.py
takes.
"""

from __future__ import annotations

import importlib.util
import sys
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.exceptions import EntityNotFoundError
from app.schemas.enums.notification_management import NotificationType
from app.schemas.notification_management.catalog import CatalogItem, CatalogUpdate

_notification_spec = importlib.util.spec_from_file_location(
    "app.routes.notification", "app/routes/notification.py"
)
_notification_routes = importlib.util.module_from_spec(_notification_spec)
sys.modules["app.routes.notification"] = _notification_routes
_notification_spec.loader.exec_module(_notification_routes)

_alert_catalog_spec = importlib.util.spec_from_file_location(
    "app.routes.alert_catalog", "app/routes/alert_catalog.py"
)
_alert_catalog_routes = importlib.util.module_from_spec(_alert_catalog_spec)
sys.modules["app.routes.alert_catalog"] = _alert_catalog_routes
_alert_catalog_spec.loader.exec_module(_alert_catalog_routes)


def _item(name="TIER_ASSIGNED", type=NotificationType.NOTIFICATION, thresholds=None) -> CatalogItem:
    return CatalogItem(
        name=name,
        display_name=name.replace("_", " ").title(),
        description="",
        type=type,
        module="TIER",
        channels=["EMAIL"],
        recipient_roles={},
        thresholds=thresholds,
    )


_SESSION = MagicMock()


@pytest.mark.asyncio
class TestListCatalogRoute:
    async def test_wraps_items_in_the_envelope(self, monkeypatch):
        stub = AsyncMock(return_value=[_item()])
        monkeypatch.setattr(_notification_routes.catalog_service, "list_catalog", stub)
        resp = await _notification_routes.list_catalog(
            catalog_type=NotificationType.NOTIFICATION, session=_SESSION
        )
        assert resp.success is True
        assert [i.name for i in resp.data.items] == ["TIER_ASSIGNED"]

    async def test_forwards_the_type_unchanged(self, monkeypatch):
        stub = AsyncMock(return_value=[])
        monkeypatch.setattr(_notification_routes.catalog_service, "list_catalog", stub)
        await _notification_routes.list_catalog(
            catalog_type=NotificationType.ALERT, session=_SESSION
        )
        assert stub.await_args.args[1] == NotificationType.ALERT

    async def test_empty_catalog_is_an_empty_list_not_an_error(self, monkeypatch):
        monkeypatch.setattr(
            _notification_routes.catalog_service, "list_catalog", AsyncMock(return_value=[])
        )
        resp = await _notification_routes.list_catalog(
            catalog_type=NotificationType.NOTIFICATION, session=_SESSION
        )
        assert resp.data.items == []

    async def test_thresholds_is_none_on_a_notification_item(self, monkeypatch):
        monkeypatch.setattr(
            _notification_routes.catalog_service, "list_catalog",
            AsyncMock(return_value=[_item(thresholds=None)]),
        )
        resp = await _notification_routes.list_catalog(
            catalog_type=NotificationType.NOTIFICATION, session=_SESSION
        )
        assert resp.data.items[0].thresholds is None

    async def test_thresholds_survives_for_an_alert_item(self, monkeypatch):
        monkeypatch.setattr(
            _notification_routes.catalog_service, "list_catalog",
            AsyncMock(return_value=[
                _item(name="QUOTA_THRESHOLD", type=NotificationType.ALERT,
                      thresholds={"50": False})
            ]),
        )
        resp = await _notification_routes.list_catalog(
            catalog_type=NotificationType.ALERT, session=_SESSION
        )
        assert resp.data.items[0].thresholds == {"50": False}


class TestListCatalogRouteShape:
    """The mounted path and its exclude_none behavior are part of the public
    contract — a refactor that drops response_model_exclude_none silently
    puts thresholds:null back on every notification response."""

    def test_path(self):
        route = next(r for r in _notification_routes.router.routes if "GET" in r.methods)
        assert route.path == "/catalog"

    def test_excludes_none_fields(self):
        route = next(r for r in _notification_routes.router.routes if "GET" in r.methods)
        assert route.response_model_exclude_none is True

    def test_type_query_param_is_required(self):
        # No default on the route signature => FastAPI raises for a missing
        # ?type= at the HTTP layer; asserting there IS no default pins that.
        import inspect

        sig = inspect.signature(_notification_routes.list_catalog)
        assert sig.parameters["catalog_type"].default is not inspect.Parameter.empty
        # It's a required fastapi Query(...), not a plain default value.
        from fastapi.params import Query as QueryParam

        default = sig.parameters["catalog_type"].default
        assert isinstance(default, QueryParam)
        assert default.is_required(), "?type= must be required, not optional"
        assert default.alias == "type"


@pytest.mark.asyncio
class TestUpdateCatalogRoute:
    async def test_wraps_the_updated_item_with_a_message(self, monkeypatch):
        stub = AsyncMock(return_value=_item(name="QUOTA_THRESHOLD", type=NotificationType.ALERT))
        monkeypatch.setattr(_alert_catalog_routes.catalog_service, "update_catalog", stub)
        resp = await _alert_catalog_routes.update_catalog(
            name="QUOTA_THRESHOLD", payload=CatalogUpdate(),
            catalog_type=NotificationType.ALERT, session=_SESSION,
        )
        assert resp.success is True
        assert resp.data.name == "QUOTA_THRESHOLD"
        assert "QUOTA_THRESHOLD" in resp.meta.message

    async def test_forwards_name_type_and_payload(self, monkeypatch):
        stub = AsyncMock(return_value=_item(type=NotificationType.ALERT))
        monkeypatch.setattr(_alert_catalog_routes.catalog_service, "update_catalog", stub)
        payload = CatalogUpdate(recipient_roles={"ADMIN": True})
        await _alert_catalog_routes.update_catalog(
            name="QUOTA_THRESHOLD", payload=payload,
            catalog_type=NotificationType.ALERT, session=_SESSION,
        )
        args = stub.await_args.args
        assert args[1] == "QUOTA_THRESHOLD"
        assert args[2] == NotificationType.ALERT
        assert args[3] is payload

    async def test_forwards_notification_type_too(self, monkeypatch):
        stub = AsyncMock(return_value=_item(type=NotificationType.NOTIFICATION))
        monkeypatch.setattr(_alert_catalog_routes.catalog_service, "update_catalog", stub)
        await _alert_catalog_routes.update_catalog(
            name="TIER_ASSIGNED", payload=CatalogUpdate(),
            catalog_type=NotificationType.NOTIFICATION, session=_SESSION,
        )
        assert stub.await_args.args[2] == NotificationType.NOTIFICATION

    async def test_404_propagates(self, monkeypatch):
        stub = AsyncMock(side_effect=EntityNotFoundError("Catalog entry 'NOPE'"))
        monkeypatch.setattr(_alert_catalog_routes.catalog_service, "update_catalog", stub)
        with pytest.raises(EntityNotFoundError):
            await _alert_catalog_routes.update_catalog(
                name="NOPE", payload=CatalogUpdate(),
                catalog_type=NotificationType.ALERT, session=_SESSION,
            )


class TestUpdateCatalogRouteShape:
    def test_path(self):
        route = next(r for r in _alert_catalog_routes.router.routes if "PATCH" in r.methods)
        assert route.path == "/catalog/{name}"

    def test_404_is_documented(self):
        route = next(r for r in _alert_catalog_routes.router.routes if "PATCH" in r.methods)
        assert 404 in route.responses

    def test_type_query_param_is_required(self):
        import inspect

        from fastapi.params import Query as QueryParam

        sig = inspect.signature(_alert_catalog_routes.update_catalog)
        default = sig.parameters["catalog_type"].default
        assert isinstance(default, QueryParam)
        assert default.is_required(), "?type= must be required, not optional"
        assert default.alias == "type"


class TestCatalogUpdateValidation:
    """Belongs to the schema, but is the route's first line of defense —
    an empty channels list must 422 before the service ever sees it."""

    def test_empty_channels_is_rejected(self):
        with pytest.raises(Exception):
            CatalogUpdate(channels=[])

    def test_omitted_channels_is_fine(self):
        assert CatalogUpdate().channels is None
