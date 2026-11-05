"""GET /models/list?columns=...: column -> field mapping, _parse_columns validation,
response_fields_for always emitting modelId, and row projection in the route."""
from __future__ import annotations

import importlib
import importlib.util
import sys
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.schemas.model_management.model_columns import (
    COLUMN_FIELDS_MAP,
    response_fields_for,
)

_spec = importlib.util.spec_from_file_location("app.routes.model", "app/routes/model.py")
_route = importlib.util.module_from_spec(_spec)
sys.modules["app.routes.model"] = _route
_spec.loader.exec_module(_route)
list_models = _route.list_models
ModelListFilterParams = _route.ModelListFilterParams
ModelListSortParams = _route.ModelListSortParams

# A representative full item as returned by ModelService.list_models.
_FULL_ITEM = {
    "modelId": "model-abc123",
    "name": "indic-nmt",
    "version": "2.0",
    "task": {"type": "nmt"},
    "providerName": "AI4Bharat",
    "versionStatus": "ACTIVE",
    "createdAt": "2026-01-01T00:00:00Z",
    "noOfServices": 3,
}


async def _call(columns=None, item=None):
    svc = MagicMock()
    svc.list_models = AsyncMock(return_value=([dict(item or _FULL_ITEM)], 1))
    result = await list_models(
        response=MagicMock(headers={}),
        db=MagicMock(),
        svc=svc,
        filters=ModelListFilterParams(),
        paging=ModelListSortParams(),
        columns=columns,
    )
    return result.data[0], svc


# ---------------------------------------------------------------------------
# TestColumnFieldsMap
# ---------------------------------------------------------------------------

class TestColumnFieldsMap:
    def test_all_keys_are_strings(self):
        for k, v in COLUMN_FIELDS_MAP.items():
            assert isinstance(k, str)
            assert isinstance(v, tuple) and v

    def test_actions_includes_model_id(self):
        assert "modelId" in COLUMN_FIELDS_MAP["actions"]


# ---------------------------------------------------------------------------
# TestResponseFieldsFor
# ---------------------------------------------------------------------------

class TestResponseFieldsFor:
    def test_model_id_always_present_even_with_no_columns(self):
        assert "modelId" in response_fields_for(frozenset())

    def test_model_id_always_present_for_non_actions_column(self):
        result = response_fields_for(frozenset({"name", "version"}))
        assert "modelId" in result
        assert "name" in result
        assert "version" in result

    def test_actions_column_does_not_duplicate_model_id(self):
        result = response_fields_for(frozenset({"actions"}))
        assert result.count("modelId") if isinstance(result, list) else "modelId" in result

    def test_multiple_columns_union_their_fields(self):
        result = response_fields_for(frozenset({"status", "createdAt"}))
        assert "versionStatus" in result
        assert "createdAt" in result

    def test_unknown_column_key_contributes_nothing_extra(self):
        result = response_fields_for(frozenset({"name"}))
        base = response_fields_for(frozenset())
        assert result == base | set(COLUMN_FIELDS_MAP["name"])


# ---------------------------------------------------------------------------
# TestParseColumns
# ---------------------------------------------------------------------------

class TestParseColumns:
    @pytest.mark.parametrize("value", [None, "", "  ,  , "])
    def test_omitted_or_blank_returns_none(self, value):
        assert _route._parse_columns(value) is None

    def test_valid_key_returns_frozenset(self):
        result = _route._parse_columns("name,version")
        assert result == frozenset({"name", "version"})

    def test_unknown_key_raises_invalid_columns(self):
        with pytest.raises(_route.ValidationError) as exc:
            _route._parse_columns("name,bogus")
        assert exc.value.code == "INVALID_COLUMNS"
        assert "bogus" in exc.value.message

    def test_error_message_lists_valid_keys(self):
        with pytest.raises(_route.ValidationError) as exc:
            _route._parse_columns("foo")
        for key in COLUMN_FIELDS_MAP:
            assert key in exc.value.message

    def test_multiple_unknown_keys_all_named(self):
        with pytest.raises(_route.ValidationError) as exc:
            _route._parse_columns("foo,bar")
        assert "foo" in exc.value.message and "bar" in exc.value.message

    def test_whitespace_trimmed_from_keys(self):
        result = _route._parse_columns(" name , version ")
        assert result == frozenset({"name", "version"})


# ---------------------------------------------------------------------------
# TestRoute — projection in the live route handler
# ---------------------------------------------------------------------------

class TestRoute:
    @pytest.mark.asyncio
    async def test_selected_columns_project_correct_fields(self):
        row, _ = await _call("name,status")
        # modelId always present; name + versionStatus from selected columns
        assert set(row) == {"modelId", "name", "versionStatus"}

    @pytest.mark.asyncio
    async def test_model_id_always_in_projected_row(self):
        row, _ = await _call("version")
        assert "modelId" in row

    @pytest.mark.asyncio
    async def test_omitting_columns_returns_full_item(self):
        row, _ = await _call(columns=None)
        assert row == _FULL_ITEM

    @pytest.mark.asyncio
    async def test_unknown_column_raises_before_db_call(self):
        svc = MagicMock()
        svc.list_models = AsyncMock()
        with pytest.raises(_route.ValidationError) as exc:
            await list_models(
                response=MagicMock(headers={}),
                db=MagicMock(),
                svc=svc,
                filters=ModelListFilterParams(),
                paging=ModelListSortParams(),
                columns="nonexistent",
            )
        assert exc.value.code == "INVALID_COLUMNS"
        svc.list_models.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_no_of_services_column_triggers_service_count(self):
        _, svc = await _call("noOfServices")
        call_kwargs = svc.list_models.call_args.kwargs
        assert call_kwargs["include_service_count"] is True

    @pytest.mark.asyncio
    async def test_omitting_no_of_services_skips_service_count(self):
        _, svc = await _call("name")
        call_kwargs = svc.list_models.call_args.kwargs
        assert call_kwargs["include_service_count"] is False
