"""Per-user table column preferences: service logic (repo mocked) and the
HTTP route (service-level exceptions mapped to status codes)."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from app.core.exceptions import AppError, EntityNotFoundError, ValidationError
from app.schemas.model_management import service_columns as cols
from app.services.user_preferences import column_preference_service as svc

_REPO = "app.services.user_preferences.column_preference_service.repo"
VIEW = "service-list"
NON_ADMIN_DEFAULTS = ["name", "actions", "task_type", "status"]


def _order(ids, is_admin):
    return [c.id for c in cols.columns_for_caller(is_admin) if c.id in set(ids)]


def _repo(stored=None):
    repo = MagicMock()
    repo.get = AsyncMock(return_value=stored)
    repo.upsert = AsyncMock()
    repo.delete_preference = AsyncMock()
    return repo


@pytest.mark.asyncio
class TestService:
    async def test_get_defaults_when_nothing_stored(self):
        with patch(_REPO, _repo(None)):
            out = await svc.get_preference(MagicMock(), "u1", VIEW, False)
        assert out == {"viewKey": VIEW, "visibleColumns": NON_ADMIN_DEFAULTS, "isDefault": True}

    async def test_admin_defaults_include_admin_defaults(self):
        with patch(_REPO, _repo(None)):
            out = await svc.get_preference(MagicMock(), "u1", VIEW, True)
        assert out["visibleColumns"] == _order(cols.DEFAULT_VISIBLE_KEYS | cols.MANDATORY_KEYS, True)
        assert out["isDefault"] is True

    async def test_put_then_get_returns_saved(self):
        repo = _repo()
        with patch(_REPO, repo):
            saved = await svc.save_preference(
                MagicMock(), "u1", VIEW, ["service_id", "task_type", "service_id"], False
            )
        assert saved == {
            "viewKey": VIEW,
            "visibleColumns": ["name", "actions", "task_type", "service_id"],
            "isDefault": False,
        }
        repo.upsert.assert_awaited_once()
        assert repo.upsert.await_args.args[1:] == ("u1", VIEW, saved["visibleColumns"])
        with patch(_REPO, _repo(saved["visibleColumns"])):
            out = await svc.get_preference(MagicMock(), "u1", VIEW, False)
        assert out == saved

    async def test_put_only_mandatory_rejected(self):
        with patch(_REPO, _repo()):
            with pytest.raises(ValidationError):
                await svc.save_preference(MagicMock(), "u1", VIEW, ["name", "actions"], False)
            with pytest.raises(ValidationError):
                await svc.save_preference(MagicMock(), "u1", VIEW, [], False)

    async def test_put_unknown_id_names_it(self):
        with patch(_REPO, _repo()):
            with pytest.raises(ValidationError) as exc:
                await svc.save_preference(MagicMock(), "u1", VIEW, ["task_type", "bogus"], False)
        assert "bogus" in str(exc.value)

    async def test_put_admin_only_id_rejected_for_non_admin(self):
        repo = _repo()
        with patch(_REPO, repo):
            with pytest.raises(ValidationError) as exc:
                await svc.save_preference(MagicMock(), "u1", VIEW, ["task_type", "input_price"], False)
            assert "input_price" in str(exc.value)
            out = await svc.save_preference(MagicMock(), "u1", VIEW, ["task_type", "input_price"], True)
        assert "input_price" in out["visibleColumns"]
        repo.upsert.assert_awaited_once()

    async def test_stored_admin_only_ids_dropped_for_non_admin(self):
        stored = ["name", "actions", "task_type", "input_price", "tier"]
        with patch(_REPO, _repo(stored)):
            out = await svc.get_preference(MagicMock(), "u1", VIEW, False)
        assert out["visibleColumns"] == ["name", "actions", "task_type"]
        assert out["isDefault"] is False

    async def test_stored_only_admin_ids_falls_back_to_defaults(self):
        with patch(_REPO, _repo(["name", "input_price"])):
            out = await svc.get_preference(MagicMock(), "u1", VIEW, False)
        assert out == {"viewKey": VIEW, "visibleColumns": NON_ADMIN_DEFAULTS, "isDefault": True}

    async def test_stored_without_mandatory_gets_them_added_in_order(self):
        with patch(_REPO, _repo(["service_id"])):
            out = await svc.get_preference(MagicMock(), "u1", VIEW, False)
        assert out["visibleColumns"] == ["name", "actions", "service_id"]

    async def test_delete_returns_defaults_and_is_idempotent(self):
        repo = _repo()
        with patch(_REPO, repo):
            out = await svc.reset_preference(MagicMock(), "u1", VIEW, False)
        assert out == {"viewKey": VIEW, "visibleColumns": NON_ADMIN_DEFAULTS, "isDefault": True}
        repo.delete_preference.assert_awaited_once()

    async def test_users_are_isolated(self):
        repo = _repo()
        with patch(_REPO, repo):
            await svc.save_preference(MagicMock(), "alice", VIEW, ["task_type"], False)
            await svc.save_preference(MagicMock(), "bob", VIEW, ["status"], False)
            await svc.get_preference(MagicMock(), "alice", VIEW, False)
        assert [c.args[1] for c in repo.upsert.await_args_list] == ["alice", "bob"]
        assert repo.get.await_args.args[1] == "alice"

    async def test_unknown_view_is_404(self):
        with patch(_REPO, _repo()):
            with pytest.raises(EntityNotFoundError):
                await svc.get_preference(MagicMock(), "u", "nope", False)
            with pytest.raises(EntityNotFoundError):
                await svc.save_preference(MagicMock(), "u", "nope", ["x"], False)
            with pytest.raises(EntityNotFoundError):
                await svc.reset_preference(MagicMock(), "u", "nope", False)


# -- HTTP level ---------------------------------------------------------------

_spec = importlib.util.spec_from_file_location(
    "app.routes.user_preferences", "app/routes/user_preferences.py"
)
_route_mod = importlib.util.module_from_spec(_spec)
sys.modules["app.routes.user_preferences"] = _route_mod
_spec.loader.exec_module(_route_mod)


@pytest.fixture()
def client():
    app = FastAPI()
    app.include_router(_route_mod.router)
    app.dependency_overrides[_route_mod.get_db] = lambda: MagicMock()

    @app.exception_handler(AppError)
    async def _handle(_, exc):
        # conftest's stub exceptions all carry 400; the real ones carry their
        # own status, so map by class here to match production behaviour.
        status = 404 if isinstance(exc, EntityNotFoundError) else 422 if isinstance(exc, ValidationError) else exc.status_code
        return JSONResponse(status_code=status, content={"detail": exc.message})

    return TestClient(app)


def _h(user="u1", perms=""):
    h = {"X-Permission-IDS": perms}
    if user:
        h["X-User-Id"] = user
    return h


class TestRoute:
    def test_missing_user_header_is_401(self, client):
        assert client.get(f"/preferences/columns/{VIEW}", headers=_h(user=None)).status_code == 401
        assert client.delete(f"/preferences/columns/{VIEW}", headers=_h(user=None)).status_code == 401

    def test_get_default_envelope(self, client):
        with patch(_REPO, _repo(None)):
            r = client.get(f"/preferences/columns/{VIEW}", headers=_h())
        assert r.status_code == 200
        assert r.json() == {
            "success": True,
            "data": {"viewKey": VIEW, "visibleColumns": NON_ADMIN_DEFAULTS, "isDefault": True},
        }

    def test_put_valid(self, client):
        with patch(_REPO, _repo()):
            r = client.put(
                f"/preferences/columns/{VIEW}", headers=_h(), json={"visibleColumns": ["task_type"]}
            )
        assert r.status_code == 200
        assert r.json()["data"]["visibleColumns"] == ["name", "actions", "task_type"]
        assert r.json()["data"]["isDefault"] is False

    def test_put_admin_only_column_depends_on_permission_header(self, client):
        body = {"visibleColumns": ["input_price"]}
        with patch(_REPO, _repo()):
            ok = client.put(f"/preferences/columns/{VIEW}", headers=_h(perms="1"), json=body)
            bad = client.put(f"/preferences/columns/{VIEW}", headers=_h(perms="4"), json=body)
        assert ok.status_code == 200
        assert bad.status_code == 422

    def test_put_bad_body_is_422(self, client):
        assert client.put(f"/preferences/columns/{VIEW}", headers=_h(), json={}).status_code == 422

    def test_unknown_view_404(self, client):
        with patch(_REPO, _repo()):
            assert client.get("/preferences/columns/nope", headers=_h()).status_code == 404

    def test_delete_returns_defaults(self, client):
        with patch(_REPO, _repo()):
            r = client.delete(f"/preferences/columns/{VIEW}", headers=_h())
        assert r.status_code == 200
        assert r.json()["data"]["isDefault"] is True


_API_PERMISSIONS = Path(__file__).resolve().parents[2] / "auth-service" / "api_permissions.json"
_ADMIN_SENTINEL = 1


def _gateway_permissions() -> dict:
    data = json.loads(_API_PERMISSIONS.read_text())
    entries = data if isinstance(data, list) else next(v for v in data.values() if isinstance(v, list))
    return {e["endpoint"]: e["permissionRequired"] for e in entries}


@pytest.mark.parametrize("view_key", sorted(svc.VIEW_CATALOGUES))
def test_every_view_has_its_own_gateway_permission(view_key):
    # The gateway matches an exact path before the {view_key} template, so each
    # view must list its own entries; otherwise it falls back to admin-only.
    perms = _gateway_permissions()
    for method in ("GET", "PUT", "DELETE"):
        key = f"{method}:/api/v1/preferences/columns/{view_key}"
        assert key in perms, f"{key} missing from api_permissions.json"
        assert perms[key] != _ADMIN_SENTINEL


def test_unlisted_view_falls_back_to_admin_only():
    perms = _gateway_permissions()
    for method in ("GET", "PUT", "DELETE"):
        assert perms[f"{method}:/api/v1/preferences/columns/{{view_key}}"] == _ADMIN_SENTINEL
