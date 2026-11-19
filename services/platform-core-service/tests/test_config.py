"""Config management — schema validation, service logic (session mocked),
and HTTP route handlers (service mocked via monkeypatch).

Route module is loaded by file path to avoid importing app/routes/__init__.py,
which eagerly imports ai4i_core.bootstrap.versioning — not stubbed in conftest.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import ValidationError as PydanticValidationError

from app.core.exceptions import AppError, DuplicateEntityError, EntityNotFoundError, InsufficientPermissionsError, ValidationError
from app.schemas.config_management.config_schema import ConfigCreate, ConfigItem, ConfigUpdate

# ── Load route module by file path ───────────────────────────────────────────

_spec = importlib.util.spec_from_file_location("app.routes.config", "app/routes/config.py")
_config_routes = importlib.util.module_from_spec(_spec)
sys.modules["app.routes.config"] = _config_routes
_spec.loader.exec_module(_config_routes)

# ── Shared test data ──────────────────────────────────────────────────────────

_NOW = datetime(2026, 11, 4, 10, 0, 0, tzinfo=timezone.utc)
_DOMAIN_DATA = ["healthcare", "global", "general"]


def _config_item(id: int = 1, type: str = "domain", data=None, is_default: bool = False) -> ConfigItem:
    return ConfigItem(
        id=id,
        type=type,
        data=data if data is not None else _DOMAIN_DATA,
        is_default=is_default,
        created_by="user-1",
        created_at=_NOW,
        updated_by="user-1",
        updated_at=_NOW,
    )


def _request(*, is_admin: bool = True) -> MagicMock:
    """Minimal request mock with X-Permission-IDS and X-User-Id headers."""
    req = MagicMock()
    req.headers = {
        "X-Permission-IDS": "1" if is_admin else "5",
        "X-User-Id": "user-1",
    }
    return req


def _orm_row(id: int = 1, type: str = "domain", data=None, is_default: bool = False) -> MagicMock:
    """Fake ORM Config row that ConfigItem.model_validate(from_attributes) can read."""
    row = MagicMock()
    row.id = id
    row.type = type
    row.data = data if data is not None else _DOMAIN_DATA
    row.is_default = is_default
    row.created_by = "user-1"
    row.created_at = _NOW
    row.updated_by = "user-1"
    row.updated_at = _NOW
    return row


def _session(*, rows=None, get_return=None) -> MagicMock:
    """Minimal async SQLAlchemy session mock."""
    session = MagicMock()
    result = MagicMock()
    result.scalars.return_value.all.return_value = rows or []
    session.execute = AsyncMock(return_value=result)
    session.get = AsyncMock(return_value=get_return)
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    session.rollback = AsyncMock()
    return session


# ── Schema validation ─────────────────────────────────────────────────────────


class TestConfigCreateSchema:
    def test_valid_with_list_data(self):
        obj = ConfigCreate(type="domain", data=_DOMAIN_DATA)
        assert obj.type == "domain"
        assert obj.data == _DOMAIN_DATA

    def test_valid_with_dict_data(self):
        obj = ConfigCreate(type="settings", data={"theme": "dark"})
        assert obj.data == {"theme": "dark"}

    def test_valid_with_string_data(self):
        obj = ConfigCreate(type="flag", data="enabled")
        assert obj.data == "enabled"

    def test_type_is_required(self):
        with pytest.raises(PydanticValidationError):
            ConfigCreate(data=_DOMAIN_DATA)

    def test_data_is_required(self):
        with pytest.raises(PydanticValidationError):
            ConfigCreate(type="domain")

    def test_type_max_255_chars(self):
        with pytest.raises(PydanticValidationError):
            ConfigCreate(type="x" * 256, data=_DOMAIN_DATA)

    def test_type_exactly_255_chars_is_accepted(self):
        obj = ConfigCreate(type="x" * 255, data=_DOMAIN_DATA)
        assert len(obj.type) == 255

    def test_type_is_stripped(self):
        obj = ConfigCreate(type="  domain  ", data=_DOMAIN_DATA)
        assert obj.type == "domain"

    def test_type_empty_string_rejected(self):
        with pytest.raises(PydanticValidationError, match="blank"):
            ConfigCreate(type="", data=_DOMAIN_DATA)

    def test_type_whitespace_only_rejected(self):
        with pytest.raises(PydanticValidationError, match="blank"):
            ConfigCreate(type="   ", data=_DOMAIN_DATA)

    def test_data_null_rejected(self):
        # POST {"type": "x", "data": null} must 422, not store JSON null.
        with pytest.raises(PydanticValidationError, match="null"):
            ConfigCreate(type="domain", data=None)


class TestConfigUpdateSchema:
    def test_all_fields_omitted_is_valid(self):
        # Both omitted → both stay None (no-op update is allowed at schema level).
        obj = ConfigUpdate()
        assert obj.type is None
        assert obj.data is None

    def test_type_only(self):
        obj = ConfigUpdate(type="settings")
        assert obj.type == "settings"
        assert obj.data is None

    def test_data_only(self):
        obj = ConfigUpdate(data={"key": "val"})
        assert obj.type is None
        assert obj.data == {"key": "val"}

    def test_both_fields(self):
        obj = ConfigUpdate(type="domain", data=_DOMAIN_DATA)
        assert obj.type == "domain"
        assert obj.data == _DOMAIN_DATA

    def test_type_max_255_chars(self):
        with pytest.raises(PydanticValidationError):
            ConfigUpdate(type="x" * 256)

    def test_type_is_stripped(self):
        obj = ConfigUpdate(type="  settings  ")
        assert obj.type == "settings"

    def test_type_null_rejected(self):
        # PUT {"type": null} must 422, not reach the DB as NOT NULL violation → 500.
        with pytest.raises(PydanticValidationError, match="null"):
            ConfigUpdate(type=None)

    def test_type_empty_string_rejected(self):
        with pytest.raises(PydanticValidationError, match="blank"):
            ConfigUpdate(type="")

    def test_type_whitespace_only_rejected(self):
        with pytest.raises(PydanticValidationError, match="blank"):
            ConfigUpdate(type="   ")

    def test_data_null_rejected(self):
        # PUT {"data": null} must 422, not store JSON null in JSONB column.
        with pytest.raises(PydanticValidationError, match="null"):
            ConfigUpdate(data=None)


# ── Service logic ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestConfigService:
    async def test_list_returns_empty(self):
        from app.services.config_management import config_service as svc

        result = await svc.list_configs(_session(rows=[]))
        assert result == []

    async def test_list_returns_all_rows_ordered(self):
        from app.services.config_management import config_service as svc

        rows = [_orm_row(id=1), _orm_row(id=2, type="settings")]
        result = await svc.list_configs(_session(rows=rows))
        assert len(result) == 2
        assert result[0].id == 1
        assert result[1].type == "settings"

    async def test_list_defaults_to_ascending_order(self):
        from app.services.config_management import config_service as svc

        session = _session(rows=[])
        await svc.list_configs(session)
        query = session.execute.call_args[0][0]
        assert "ORDER BY configs.id ASC" in str(query)

    async def test_list_sort_order_desc_sorts_descending(self):
        from app.services.config_management import config_service as svc

        session = _session(rows=[])
        await svc.list_configs(session, sort_order="desc")
        query = session.execute.call_args[0][0]
        assert "ORDER BY configs.id DESC" in str(query)

    async def test_type_filter_sorts_data_items_by_label_asc(self):
        from app.services.config_management import config_service as svc

        row = _orm_row(
            type="domain",
            data=[
                {"key": "news", "label": "News", "required": False},
                {"key": "general", "label": "General", "required": False},
                {"key": "education", "label": "Education", "required": False},
            ],
        )
        result = await svc.list_configs(_session(rows=[row]), type_filter="domain", sort_order="asc")
        assert [item["label"] for item in result[0].data] == ["Education", "General", "News"]

    async def test_type_filter_without_sort_order_leaves_data_untouched(self):
        from app.services.config_management import config_service as svc

        data = [
            {"key": "news", "label": "News", "required": False},
            {"key": "general", "label": "General", "required": False},
        ]
        row = _orm_row(type="domain", data=data)
        result = await svc.list_configs(_session(rows=[row]), type_filter="domain")
        assert [item["label"] for item in result[0].data] == ["News", "General"]

    async def test_type_filter_sorts_data_items_by_label_desc(self):
        from app.services.config_management import config_service as svc

        row = _orm_row(
            type="domain",
            data=[
                {"key": "news", "label": "News", "required": False},
                {"key": "general", "label": "General", "required": False},
                {"key": "education", "label": "Education", "required": False},
            ],
        )
        result = await svc.list_configs(_session(rows=[row]), type_filter="domain", sort_order="desc")
        assert [item["label"] for item in result[0].data] == ["News", "General", "Education"]

    async def test_type_filter_sort_is_case_insensitive(self):
        from app.services.config_management import config_service as svc

        row = _orm_row(
            type="domain",
            data=[
                {"key": "news", "label": "news", "required": False},
                {"key": "general", "label": "General", "required": False},
            ],
        )
        result = await svc.list_configs(_session(rows=[row]), type_filter="domain", sort_order="asc")
        assert [item["label"] for item in result[0].data] == ["General", "news"]

    async def test_no_type_filter_leaves_data_untouched(self):
        from app.services.config_management import config_service as svc

        data = [
            {"key": "news", "label": "News", "required": False},
            {"key": "general", "label": "General", "required": False},
        ]
        row = _orm_row(type="domain", data=data)
        result = await svc.list_configs(_session(rows=[row]), sort_order="desc")
        assert [item["label"] for item in result[0].data] == ["News", "General"]

    async def test_non_sortable_data_shape_is_left_unchanged(self):
        from app.services.config_management import config_service as svc

        row = _orm_row(type="settings", data={"theme": "dark"})
        result = await svc.list_configs(_session(rows=[row]), type_filter="settings")
        assert result[0].data == {"theme": "dark"}

    async def test_get_returns_matching_item(self):
        from app.services.config_management import config_service as svc

        result = await svc.get_config(_session(get_return=_orm_row()), 1)
        assert result.id == 1
        assert result.type == "domain"
        assert result.data == _DOMAIN_DATA

    async def test_get_missing_raises_not_found(self):
        from app.services.config_management import config_service as svc

        with pytest.raises(EntityNotFoundError):
            await svc.get_config(_session(get_return=None), 999)

    async def test_create_adds_row_and_commits(self):
        from app.services.config_management import config_service as svc

        session = _session()
        body = ConfigCreate(type="domain", data=_DOMAIN_DATA)

        async def _refresh(row):
            row.id = 1
            row.type = "domain"
            row.data = _DOMAIN_DATA
            row.is_default = False
            row.created_by = "user-1"
            row.created_at = _NOW
            row.updated_by = "user-1"
            row.updated_at = _NOW

        session.refresh = _refresh

        result = await svc.create_config(session, body, created_by="user-1")
        session.add.assert_called_once()
        session.commit.assert_awaited_once()
        assert result.type == "domain"
        assert result.data == _DOMAIN_DATA

    async def test_create_sets_created_by_and_updated_by(self):
        from app.services.config_management import config_service as svc

        session = _session()
        body = ConfigCreate(type="domain", data=_DOMAIN_DATA)

        async def _refresh(row):
            row.id = 1
            row.type = row.type
            row.data = row.data
            row.is_default = False
            row.created_by = row.created_by
            row.created_at = _NOW
            row.updated_by = row.updated_by
            row.updated_at = _NOW

        session.refresh = _refresh

        await svc.create_config(session, body, created_by="admin-user")
        added_row = session.add.call_args[0][0]
        assert added_row.created_by == "admin-user"
        assert added_row.updated_by == "admin-user"

    async def test_create_duplicate_type_raises_conflict(self):
        from app.services.config_management import config_service as svc
        from sqlalchemy.exc import IntegrityError

        session = _session()
        body = ConfigCreate(type="domain", data=_DOMAIN_DATA)

        orig = Exception('duplicate key value violates unique constraint "uq_configs_type"')
        session.commit = AsyncMock(side_effect=IntegrityError("", {}, orig))

        with pytest.raises(DuplicateEntityError):
            await svc.create_config(session, body, created_by="user-1")
        session.rollback.assert_awaited_once()

    async def test_update_missing_raises_not_found(self):
        from app.services.config_management import config_service as svc

        with pytest.raises(EntityNotFoundError):
            await svc.update_config(_session(get_return=None), 999, ConfigUpdate(type="x"))

    async def test_update_applies_sent_fields_only(self):
        from app.services.config_management import config_service as svc

        row = _orm_row(type="domain", data=_DOMAIN_DATA)
        session = _session(get_return=row)

        async def _refresh(r):
            pass

        session.refresh = _refresh

        await svc.update_config(session, 1, ConfigUpdate(type="settings"), updated_by="admin")
        assert row.type == "settings"
        assert row.data == _DOMAIN_DATA  # unchanged — not in payload
        assert row.updated_by == "admin"
        session.commit.assert_awaited_once()

    async def test_update_data_only_leaves_type_unchanged(self):
        from app.services.config_management import config_service as svc

        row = _orm_row(type="domain", data=_DOMAIN_DATA)
        session = _session(get_return=row)
        session.refresh = AsyncMock()

        new_data = ["finance"]
        await svc.update_config(session, 1, ConfigUpdate(data=new_data))
        assert row.type == "domain"  # unchanged
        assert row.data == new_data

    async def test_update_duplicate_type_raises_conflict(self):
        from app.services.config_management import config_service as svc
        from sqlalchemy.exc import IntegrityError

        row = _orm_row(type="domain")
        session = _session(get_return=row)
        session.refresh = AsyncMock()

        orig = Exception('duplicate key value violates unique constraint "uq_configs_type"')
        session.commit = AsyncMock(side_effect=IntegrityError("", {}, orig))

        with pytest.raises(DuplicateEntityError):
            await svc.update_config(session, 1, ConfigUpdate(type="settings"), updated_by="user-1")
        session.rollback.assert_awaited_once()

    async def test_delete_missing_raises_not_found(self):
        from app.services.config_management import config_service as svc

        with pytest.raises(EntityNotFoundError):
            await svc.delete_config(_session(get_return=None), 999)

    async def test_delete_executes_and_commits(self):
        from app.services.config_management import config_service as svc

        session = _session(get_return=_orm_row(id=5))
        session.delete = AsyncMock()
        deleted_id = await svc.delete_config(session, 5)
        assert deleted_id == 5
        session.delete.assert_awaited_once()
        session.commit.assert_awaited_once()

    async def test_delete_default_config_is_rejected(self):
        from app.services.config_management import config_service as svc

        session = _session(get_return=_orm_row(id=5, is_default=True))
        session.delete = AsyncMock()
        with pytest.raises(AppError) as exc_info:
            await svc.delete_config(session, 5)
        assert exc_info.value.status_code == 409
        session.delete.assert_not_awaited()
        session.commit.assert_not_awaited()


# ── Route handlers ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestListConfigsRoute:
    async def test_returns_success_envelope(self, monkeypatch):
        monkeypatch.setattr(
            _config_routes.config_service, "list_configs",
            AsyncMock(return_value=[_config_item(id=1), _config_item(id=2)]),
        )
        resp = await _config_routes.list_configs(type=None, session=MagicMock())
        assert resp.success is True
        assert len(resp.data.items) == 2

    async def test_returns_empty_list(self, monkeypatch):
        monkeypatch.setattr(
            _config_routes.config_service, "list_configs", AsyncMock(return_value=[])
        )
        resp = await _config_routes.list_configs(type=None, session=MagicMock())
        assert resp.data.items == []

    async def test_filter_by_type_passes_to_service(self, monkeypatch):
        stub = AsyncMock(return_value=[_config_item()])
        monkeypatch.setattr(_config_routes.config_service, "list_configs", stub)
        await _config_routes.list_configs(type="domain", session=MagicMock())
        _, kwargs = stub.call_args
        assert kwargs.get("type_filter") == "domain"

    async def test_no_filter_passes_none_to_service(self, monkeypatch):
        stub = AsyncMock(return_value=[])
        monkeypatch.setattr(_config_routes.config_service, "list_configs", stub)
        await _config_routes.list_configs(type=None, session=MagicMock())
        _, kwargs = stub.call_args
        assert kwargs.get("type_filter") is None

    async def test_sort_order_defaults_to_none(self, monkeypatch):
        stub = AsyncMock(return_value=[])
        monkeypatch.setattr(_config_routes.config_service, "list_configs", stub)
        await _config_routes.list_configs(type=None, session=MagicMock())
        _, kwargs = stub.call_args
        assert kwargs.get("sort_order") is None

    async def test_sort_order_desc_passes_to_service(self, monkeypatch):
        stub = AsyncMock(return_value=[])
        monkeypatch.setattr(_config_routes.config_service, "list_configs", stub)
        await _config_routes.list_configs(type=None, sort_order="desc", session=MagicMock())
        _, kwargs = stub.call_args
        assert kwargs.get("sort_order") == "desc"

    async def test_invalid_sort_order_is_rejected(self, monkeypatch):
        stub = AsyncMock(return_value=[])
        monkeypatch.setattr(_config_routes.config_service, "list_configs", stub)
        with pytest.raises(ValidationError):
            await _config_routes.list_configs(type=None, sort_order="sideways", session=MagicMock())
        stub.assert_not_awaited()

    async def test_all_roles_can_list(self, monkeypatch):
        # No permission check on list — any authenticated user passes through.
        stub = AsyncMock(return_value=[_config_item()])
        monkeypatch.setattr(_config_routes.config_service, "list_configs", stub)
        resp = await _config_routes.list_configs(type=None, session=MagicMock())
        assert resp.success is True
        stub.assert_awaited_once()


@pytest.mark.asyncio
class TestCreateConfigRoute:
    async def test_returns_item_and_message(self, monkeypatch):
        monkeypatch.setattr(
            _config_routes.config_service, "create_config",
            AsyncMock(return_value=_config_item()),
        )
        resp = await _config_routes.create_config(
            payload=ConfigCreate(type="domain", data=_DOMAIN_DATA),
            request=_request(),
            session=MagicMock(),
        )
        assert resp.success is True
        assert resp.data.id == 1
        assert resp.data.type == "domain"
        assert "domain" in resp.meta.message

    async def test_passes_user_id_to_service(self, monkeypatch):
        stub = AsyncMock(return_value=_config_item())
        monkeypatch.setattr(_config_routes.config_service, "create_config", stub)
        await _config_routes.create_config(
            payload=ConfigCreate(type="domain", data=_DOMAIN_DATA),
            request=_request(),
            session=MagicMock(),
        )
        _, kwargs = stub.call_args
        assert kwargs.get("created_by") == "user-1"

    async def test_duplicate_type_propagates_conflict(self, monkeypatch):
        monkeypatch.setattr(
            _config_routes.config_service, "create_config",
            AsyncMock(side_effect=DuplicateEntityError("Config with type 'domain' already exists")),
        )
        with pytest.raises(DuplicateEntityError):
            await _config_routes.create_config(
                payload=ConfigCreate(type="domain", data=_DOMAIN_DATA),
                request=_request(),
                session=MagicMock(),
            )

    async def test_non_admin_is_rejected(self, monkeypatch):
        stub = AsyncMock()
        monkeypatch.setattr(_config_routes.config_service, "create_config", stub)
        with pytest.raises(InsufficientPermissionsError):
            await _config_routes.create_config(
                payload=ConfigCreate(type="domain", data=_DOMAIN_DATA),
                request=_request(is_admin=False),
                session=MagicMock(),
            )
        stub.assert_not_awaited()


@pytest.mark.asyncio
class TestGetConfigRoute:
    async def test_returns_item(self, monkeypatch):
        monkeypatch.setattr(
            _config_routes.config_service, "get_config",
            AsyncMock(return_value=_config_item()),
        )
        resp = await _config_routes.get_config(
            request=_request(), config_id=1, session=MagicMock()
        )
        assert resp.success is True
        assert resp.data.id == 1
        assert resp.data.data == _DOMAIN_DATA

    async def test_missing_propagates_not_found(self, monkeypatch):
        monkeypatch.setattr(
            _config_routes.config_service, "get_config",
            AsyncMock(side_effect=EntityNotFoundError("Config 999")),
        )
        with pytest.raises(EntityNotFoundError):
            await _config_routes.get_config(
                request=_request(), config_id=999, session=MagicMock()
            )

    async def test_non_admin_is_rejected(self, monkeypatch):
        stub = AsyncMock()
        monkeypatch.setattr(_config_routes.config_service, "get_config", stub)
        with pytest.raises(InsufficientPermissionsError):
            await _config_routes.get_config(
                request=_request(is_admin=False), config_id=1, session=MagicMock()
            )
        stub.assert_not_awaited()


@pytest.mark.asyncio
class TestUpdateConfigRoute:
    async def test_returns_updated_item_and_message(self, monkeypatch):
        monkeypatch.setattr(
            _config_routes.config_service, "update_config",
            AsyncMock(return_value=_config_item(type="settings")),
        )
        resp = await _config_routes.update_config(
            payload=ConfigUpdate(type="settings"),
            request=_request(),
            config_id=1,
            session=MagicMock(),
        )
        assert resp.success is True
        assert resp.data.type == "settings"
        assert "settings" in resp.meta.message

    async def test_missing_propagates_not_found(self, monkeypatch):
        monkeypatch.setattr(
            _config_routes.config_service, "update_config",
            AsyncMock(side_effect=EntityNotFoundError("Config 999")),
        )
        with pytest.raises(EntityNotFoundError):
            await _config_routes.update_config(
                payload=ConfigUpdate(type="x"),
                request=_request(),
                config_id=999,
                session=MagicMock(),
            )

    async def test_duplicate_type_propagates_conflict(self, monkeypatch):
        monkeypatch.setattr(
            _config_routes.config_service, "update_config",
            AsyncMock(side_effect=DuplicateEntityError("Config with type 'settings' already exists")),
        )
        with pytest.raises(DuplicateEntityError):
            await _config_routes.update_config(
                payload=ConfigUpdate(type="settings"),
                request=_request(),
                config_id=1,
                session=MagicMock(),
            )

    async def test_passes_user_id_to_service(self, monkeypatch):
        stub = AsyncMock(return_value=_config_item())
        monkeypatch.setattr(_config_routes.config_service, "update_config", stub)
        await _config_routes.update_config(
            payload=ConfigUpdate(type="x"),
            request=_request(),
            config_id=1,
            session=MagicMock(),
        )
        _, kwargs = stub.call_args
        assert kwargs.get("updated_by") == "user-1"

    async def test_non_admin_is_rejected(self, monkeypatch):
        stub = AsyncMock()
        monkeypatch.setattr(_config_routes.config_service, "update_config", stub)
        with pytest.raises(InsufficientPermissionsError):
            await _config_routes.update_config(
                payload=ConfigUpdate(type="x"),
                request=_request(is_admin=False),
                config_id=1,
                session=MagicMock(),
            )
        stub.assert_not_awaited()


@pytest.mark.asyncio
class TestDeleteConfigRoute:
    async def test_returns_deleted_id_and_message(self, monkeypatch):
        monkeypatch.setattr(
            _config_routes.config_service, "delete_config", AsyncMock(return_value=1)
        )
        resp = await _config_routes.delete_config(
            request=_request(), config_id=1, session=MagicMock()
        )
        assert resp.success is True
        assert resp.data.id == 1
        assert "1" in resp.meta.message

    async def test_missing_propagates_not_found(self, monkeypatch):
        monkeypatch.setattr(
            _config_routes.config_service, "delete_config",
            AsyncMock(side_effect=EntityNotFoundError("Config 999")),
        )
        with pytest.raises(EntityNotFoundError):
            await _config_routes.delete_config(
                request=_request(), config_id=999, session=MagicMock()
            )

    async def test_non_admin_is_rejected(self, monkeypatch):
        stub = AsyncMock()
        monkeypatch.setattr(_config_routes.config_service, "delete_config", stub)
        with pytest.raises(InsufficientPermissionsError):
            await _config_routes.delete_config(
                request=_request(is_admin=False), config_id=1, session=MagicMock()
            )
        stub.assert_not_awaited()

    async def test_default_config_propagates_protected_error(self, monkeypatch):
        monkeypatch.setattr(
            _config_routes.config_service, "delete_config",
            AsyncMock(side_effect=AppError(
                message="Config marked as default cannot be deleted.",
                code="DEFAULT_CONFIG_PROTECTED",
                status_code=409,
            )),
        )
        with pytest.raises(AppError) as exc_info:
            await _config_routes.delete_config(
                request=_request(), config_id=1, session=MagicMock()
            )
        assert exc_info.value.status_code == 409


# ── Gateway permissions ───────────────────────────────────────────────────────


def test_config_endpoints_registered_in_api_permissions():
    """Config endpoints must be in api_permissions.json with correct permissions."""
    from pathlib import Path

    permissions_file = (
        Path(__file__).resolve().parents[2] / "auth-service" / "api_permissions.json"
    )
    data = json.loads(permissions_file.read_text())
    entries = data if isinstance(data, list) else next(
        v for v in data.values() if isinstance(v, list)
    )
    perm_map = {e["endpoint"]: e["permissionRequired"] for e in entries}

    # List is open to all authenticated roles (configs.read = 120).
    assert "GET:/api/v1/config" in perm_map
    assert perm_map["GET:/api/v1/config"] == 120, "List must use configs.read (120), not admin sentinel"

    # All mutating + get-by-id endpoints remain admin-only (sentinel = 1).
    for endpoint in [
        "POST:/api/v1/config",
        "GET:/api/v1/config/{config_id}",
        "PUT:/api/v1/config/{config_id}",
        "DELETE:/api/v1/config/{config_id}",
    ]:
        assert endpoint in perm_map, f"{endpoint} missing from api_permissions.json"
        assert perm_map[endpoint] == 1, f"{endpoint} must have permissionRequired=1 (admin sentinel)"
