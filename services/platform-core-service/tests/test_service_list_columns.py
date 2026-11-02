"""GET /services?columns=...: the catalogue's column -> field map, column
parsing, row projection, and skipping the tier-name lookup."""
from __future__ import annotations

import importlib
import importlib.util
import sys
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.model_management.service import Service
from app.schemas.model_management.service import ServiceListItem
from app.schemas.model_management.service_columns import (
    ADMIN_ONLY_KEYS,
    MANDATORY_KEYS,
    SERVICE_LIST_COLUMNS,
    VALID_COLUMN_KEYS,
    response_fields_for,
)

_spec = importlib.util.spec_from_file_location("app.routes.service", "app/routes/service.py")
_route = importlib.util.module_from_spec(_spec)
sys.modules["app.routes.service"] = _route
_spec.loader.exec_module(_route)
list_services = _route.list_services
ServiceListFilterParams = _route.ServiceListFilterParams
ServiceListSortParams = _route.ServiceListSortParams

_serializers = importlib.import_module("app.services.model-management.serializers")
_svc_svc_mod = importlib.import_module("app.services.model-management.service_service")

ADMIN, NON_ADMIN = "1", "50"

# What service_to_dict + the list's model join produce for one row.
_FULL_ITEM = {
    "serviceId": "svc-1",
    "name": "ASR Prod",
    "description": "desc",
    "serviceDescription": "desc",
    "hardwareDescription": "8x A100",
    "modelId": "model-1",
    "modelVersion": "1.0",
    "task": {"type": "asr"},
    "taskType": "asr",
    "endpoint": "http://internal-host/asr",
    "inferenceServerType": "triton",
    "sslVerify": True,
    "api_key": "super-secret-key",
    "isPublished": False,
    "isTryItDefault": False,
    "publishedAt": None,
    "unpublishedAt": None,
    "costPerUnit": 0.5,
    "cachedInputCostPerUnit": None,
    "outputCostPerUnit": 1.5,
    "unitSize": 1,
    "unitRate": 0.5,
    "tierIds": ["tier-1"],
    "tierNames": ["Gold"],
    "deletedAt": None,
    "createdAt": "2026-01-01T00:00:00Z",
    "updatedAt": "2026-01-02T00:00:00Z",
    "createdBy": "user-1",
    "updatedBy": "user-1",
    "modelName": "asr-model",
    "languages": [{"sourceLanguage": "en"}],
    "versionStatus": "ACTIVE",
}


def _req(ids):
    r = MagicMock()
    r.headers = {"X-Permission-IDS": ids}
    return r


async def _call(ids, columns=None, item=None):
    svc = MagicMock()
    svc.list_services = AsyncMock(return_value=([dict(item or _FULL_ITEM)], 1))
    result = await list_services(
        request=_req(ids), response=MagicMock(headers={}), svc=svc, db=MagicMock(),
        filters=ServiceListFilterParams(), paging=ServiceListSortParams(), columns=columns,
    )
    # What response_model_exclude_unset=True puts on the wire.
    return result.data.services[0].model_dump(exclude_unset=True), svc


class TestCatalogue:
    @pytest.mark.parametrize("col", SERVICE_LIST_COLUMNS, ids=lambda c: c.id)
    def test_every_column_maps_to_list_item_fields(self, col):
        assert col.fields
        assert set(col.fields) <= set(ServiceListItem.model_fields)

    def test_valid_keys_are_every_column(self):
        assert VALID_COLUMN_KEYS == {c.id for c in SERVICE_LIST_COLUMNS}

    def test_response_fields_for(self):
        base = {"serviceId", "name", "isPublished", "versionStatus", "tierIds"}
        assert response_fields_for(frozenset({"model_name"}), False) == base | {"modelName"}
        assert response_fields_for(frozenset(), True) == base | {"createdAt", "updatedAt", "publishedAt"}


class TestParseColumns:
    @pytest.mark.parametrize("value", [None, "", " , ,"])
    def test_omitted_or_blank_is_full_item(self, value):
        assert _route._parse_columns(value, False) is None

    def test_unknown_id_names_it_and_the_valid_ones(self):
        with pytest.raises(_route.ValidationError) as e:
            _route._parse_columns("task_type,bogus", True)
        assert e.value.code == "INVALID_COLUMNS"
        assert "bogus" in e.value.message and "task_type" in e.value.message

    def test_admin_only_id_for_non_admin(self):
        with pytest.raises(_route.ValidationError) as e:
            _route._parse_columns("task_type,input_price", False)
        assert e.value.code == "COLUMN_NOT_PERMITTED"
        assert "input_price" in e.value.message

    def test_admin_may_use_admin_only_ids(self):
        assert ADMIN_ONLY_KEYS <= _route._parse_columns(",".join(ADMIN_ONLY_KEYS), True)

    def test_mandatory_ids_are_added(self):
        assert _route._parse_columns(" Task_Type ", False) == MANDATORY_KEYS | {"task_type"}


class TestRoute:
    @pytest.mark.asyncio
    async def test_admin_gets_exactly_the_selected_fields(self):
        row, _ = await _call(ADMIN, "task_type,input_price")
        assert row == {
            "serviceId": "svc-1", "name": "ASR Prod", "isPublished": False,
            "versionStatus": "ACTIVE", "tierIds": ["tier-1"],
            "createdAt": "2026-01-01T00:00:00Z", "updatedAt": "2026-01-02T00:00:00Z",
            "publishedAt": None,
            "taskType": "asr", "task": {"type": "asr"}, "costPerUnit": 0.5,
        }

    @pytest.mark.asyncio
    async def test_non_admin_gets_no_timestamps_or_prices(self):
        row, _ = await _call(NON_ADMIN, "task_type,model_name,service_id,status")
        assert set(row) == {
            "serviceId", "name", "isPublished", "versionStatus", "tierIds",
            "taskType", "task", "modelName",
        }

    @pytest.mark.asyncio
    async def test_non_admin_admin_only_column_is_422_before_db_work(self):
        svc = MagicMock()
        svc.list_services = AsyncMock()
        with pytest.raises(_route.ValidationError) as e:
            await list_services(
                request=_req(NON_ADMIN), response=MagicMock(headers={}), svc=svc, db=MagicMock(),
                filters=ServiceListFilterParams(), paging=ServiceListSortParams(), columns="input_price",
            )
        assert e.value.code == "COLUMN_NOT_PERMITTED"
        svc.list_services.assert_not_called()

    @pytest.mark.asyncio
    async def test_tier_names_only_when_tier_selected(self):
        row, svc = await _call(ADMIN, "status")
        assert "tierNames" not in row and row["tierIds"] == ["tier-1"]
        assert svc.list_services.call_args.kwargs["include_tier_names"] is False

        row, svc = await _call(ADMIN, "tier")
        assert row["tierNames"] == ["Gold"]
        assert svc.list_services.call_args.kwargs["include_tier_names"] is True

    @pytest.mark.asyncio
    @pytest.mark.parametrize("ids", [ADMIN, NON_ADMIN])
    async def test_omitting_columns_keeps_the_full_payload(self, ids):
        row, svc = await _call(ids)
        expected = _route.mask_service_secrets(dict(_FULL_ITEM)) if ids == ADMIN \
            else _route._filter_service_fields(_FULL_ITEM)
        assert row == ServiceListItem(**expected).model_dump(exclude_unset=True)
        assert svc.list_services.call_args.kwargs["include_tier_names"] is True


def _service(**over) -> Service:
    fields = dict(
        service_id="svc-1", name="ASR Prod", model_id="model-1", model_version="1.0",
        task_type="asr", is_published=False, tier_ids=["tier-1"],
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        updated_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
    )
    fields.update(over)
    return Service(**fields)


class TestServiceLayer:
    def _svc(self):
        repo = MagicMock()
        repo.list_services = AsyncMock(return_value=[(_service(), None)])
        repo.get_tier_names_by_ids = AsyncMock(return_value={"tier-1": "Gold"})
        return _svc_svc_mod.ServiceService(service_repo=repo, model_repo=MagicMock(), cache=MagicMock()), repo

    @pytest.mark.asyncio
    async def test_skips_tier_lookup_when_not_needed(self):
        svc, repo = self._svc()
        items, _ = await svc.list_services(include_tier_names=False)
        repo.get_tier_names_by_ids.assert_not_called()
        assert items[0]["tierNames"] is None
        assert items[0]["tierIds"] == ["tier-1"]

    @pytest.mark.asyncio
    async def test_looks_up_tier_names_by_default(self):
        svc, repo = self._svc()
        items, _ = await svc.list_services()
        repo.get_tier_names_by_ids.assert_awaited_once()
        assert items[0]["tierNames"] == ["Gold"]


def test_serializer_emits_updated_at():
    out = _serializers.service_to_dict(_service())
    assert out["updatedAt"].startswith("2026-01-02")
