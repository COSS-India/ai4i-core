"""GET /services/columns — RBAC-filtered column catalogue with filter options.

The route module is loaded by file path (see test_inference_types_routes.py)
because app/routes/__init__.py imports packages the conftest does not stub.
"""

from __future__ import annotations

import importlib.util
import sys
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from app.core.database import get_db
from app.schemas.model_management.service_columns import (
    SERVICE_LIST_COLUMNS,
    columns_for_caller,
)

_spec = importlib.util.spec_from_file_location(
    "app.routes.service_columns", "app/routes/service_columns.py"
)
_routes = importlib.util.module_from_spec(_spec)
sys.modules["app.routes.service_columns"] = _routes
_spec.loader.exec_module(_routes)

TIER_ID = uuid.uuid4()
INFERENCE_TYPES = [{"name": "asr"}, {"name": "NMT"}, {"name": "tts", "display_name": "Text to Speech"}]


def _db(tiers=None):
    db = MagicMock()
    result = MagicMock()
    result.all.return_value = tiers if tiers is not None else [SimpleNamespace(id=TIER_ID, name="Gold")]
    db.execute = AsyncMock(return_value=result)
    return db


@pytest.fixture
def make_client(monkeypatch):
    monkeypatch.setattr(
        _routes.inference_type_cache, "get_all", AsyncMock(return_value=INFERENCE_TYPES)
    )

    def _make(db, routers=None):
        app = FastAPI()
        for r in routers or [_routes.router]:
            app.include_router(r)
        app.dependency_overrides[get_db] = lambda: db
        return TestClient(app)

    return _make


def _get(client, perms):
    resp = client.get("/services/columns", headers={"X-Permission-IDS": perms})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["success"] is True
    return body["data"]["columns"]


def test_admin_gets_full_catalogue_in_order(make_client):
    cols = _get(make_client(_db()), "1")
    assert [c["id"] for c in cols] == [c.id for c in SERVICE_LIST_COLUMNS]
    assert len(cols) == 12


def test_moderator_is_treated_as_admin(make_client):
    assert len(_get(make_client(_db()), "2")) == 12


def test_non_admin_gets_only_non_admin_columns_and_no_tier_query(make_client):
    db = _db()
    cols = _get(make_client(db), "3")
    assert [c["id"] for c in cols] == [c.id for c in columns_for_caller(False)]
    assert "tier" not in {c["id"] for c in cols}
    db.execute.assert_not_awaited()


def test_mandatory_and_default_visible_flags(make_client):
    by_id = {c["id"]: c for c in _get(make_client(_db()), "1")}
    assert by_id["name"]["mandatory"] and by_id["name"]["defaultVisible"]
    assert by_id["actions"]["mandatory"] and by_id["actions"]["sortable"] is False
    assert by_id["tier"]["mandatory"] is False and by_id["tier"]["defaultVisible"] is True
    assert by_id["input_price"]["defaultVisible"] is False


def test_filter_metadata_per_type(make_client):
    by_id = {c["id"]: c for c in _get(make_client(_db()), "1")}
    assert by_id["name"]["filter"] == {"type": "text", "params": ["name"], "options": None}
    assert by_id["created_at"]["filter"] == {
        "type": "date_range", "params": ["created_from", "created_to"], "options": None,
    }
    assert by_id["status"]["filter"]["type"] == "single_select"
    assert by_id["status"]["filter"]["params"] == ["is_published"]
    assert by_id["task_type"]["filter"]["type"] == "multi_select"
    assert by_id["input_price"]["filter"] is None
    assert by_id["input_price"]["filterable"] is False
    assert by_id["tier"]["filterable"] is True


def test_options_populated(make_client):
    by_id = {c["id"]: c for c in _get(make_client(_db()), "1")}
    assert by_id["status"]["filter"]["options"] == [
        {"value": "true", "label": "Published"},
        {"value": "false", "label": "Unpublished"},
    ]
    assert by_id["task_type"]["filter"]["options"] == [
        {"value": "asr", "label": "asr"},
        {"value": "nmt", "label": "NMT"},
        {"value": "tts", "label": "Text to Speech"},
    ]
    assert by_id["tier"]["filter"]["options"] == [{"value": str(TIER_ID), "label": "Gold"}]


def test_non_admin_still_gets_task_type_options(make_client):
    by_id = {c["id"]: c for c in _get(make_client(_db()), "3")}
    assert len(by_id["task_type"]["filter"]["options"]) == 3


def test_columns_not_captured_by_service_id_route(make_client):
    """Same include order as app/routes/__init__.py."""
    catch_all = APIRouter(prefix="/services")
    hits = []

    @catch_all.get("/{service_id:path}")
    async def get_one(service_id: str):
        hits.append(service_id)
        return {"captured": service_id}

    client = make_client(_db(), routers=[_routes.router, catch_all])
    cols = _get(client, "1")
    assert hits == [] and len(cols) == 12
    # sanity: other paths still reach the catch-all
    assert client.get("/services/abc").json() == {"captured": "abc"}


def test_router_registered_before_service_router():
    src = open("app/routes/__init__.py").read()
    assert src.index("include_router(service_columns_router)") < src.index(
        "include_router(service_router)"
    )
