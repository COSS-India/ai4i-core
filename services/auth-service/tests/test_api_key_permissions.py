"""API key permission name resolution — create, read, and inference catalog."""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.core.exceptions import ValidationError
from app.models.api_key import APIKey
from app.models.role import Permission
from app.services.api_key_service import APIKeyService


def _api_key(*, permissions: list[int] | None = None) -> APIKey:
    return APIKey(
        id=1,
        user_id=uuid4(),
        key_name="test-key",
        api_key="a" * 32,
        permissions=permissions if permissions is not None else [12, 15],
        expires_at=datetime.now(timezone.utc) + timedelta(days=30),
        is_active=True,
    )


def _service(*, name_to_id: dict[str, int] | None = None, id_to_name: dict[int, str] | None = None) -> APIKeyService:
    repo = AsyncMock()
    repo.get_permission_ids_by_names = AsyncMock(return_value=name_to_id or {})
    repo.get_permission_names_by_ids = AsyncMock(return_value=id_to_name or {})
    return APIKeyService(repo, AsyncMock())


class TestResolvePermissionNames:
    @pytest.mark.asyncio
    async def test_resolves_known_names_to_ids_in_request_order(self) -> None:
        svc = _service(name_to_id={"nmt.inference": 12, "asr.inference": 15})
        ids = await svc._resolve_permission_names(["nmt.inference", "asr.inference"])
        assert ids == [12, 15]

    @pytest.mark.asyncio
    async def test_deduplicates_names_while_preserving_first_occurrence_order(self) -> None:
        svc = _service(name_to_id={"nmt.inference": 12, "asr.inference": 15})
        ids = await svc._resolve_permission_names(["nmt.inference", "asr.inference", "nmt.inference"])
        assert ids == [12, 15]

    @pytest.mark.asyncio
    async def test_empty_list_returns_empty(self) -> None:
        svc = _service()
        assert await svc._resolve_permission_names([]) == []

    @pytest.mark.asyncio
    async def test_unknown_name_raises_invalid_permission_names(self) -> None:
        svc = _service(name_to_id={"nmt.inference": 12})
        with pytest.raises(ValidationError) as exc_info:
            await svc._resolve_permission_names(["nmt.inference", "unknown.permission"])
        exc = exc_info.value
        assert exc.code == "INVALID_PERMISSION_NAMES"
        assert exc.status_code == 422
        assert "Unknown permission: unknown.permission" in exc.errors

    @pytest.mark.asyncio
    async def test_all_unknown_names_are_reported(self) -> None:
        svc = _service(name_to_id={})
        with pytest.raises(ValidationError) as exc_info:
            await svc._resolve_permission_names(["foo.inference", "bar.inference"])
        assert exc_info.value.code == "INVALID_PERMISSION_NAMES"
        assert exc_info.value.errors == [
            "Unknown permission: foo.inference",
            "Unknown permission: bar.inference",
        ]


class TestPermissionIdsToNames:
    @pytest.mark.asyncio
    async def test_maps_stored_ids_to_names_in_order(self) -> None:
        svc = _service(id_to_name={12: "nmt.inference", 15: "asr.inference"})
        names = await svc.permission_ids_to_names([12, 15])
        assert names == ["nmt.inference", "asr.inference"]

    @pytest.mark.asyncio
    async def test_empty_ids_returns_empty(self) -> None:
        svc = _service()
        assert await svc.permission_ids_to_names([]) == []

    @pytest.mark.asyncio
    async def test_orphaned_id_is_omitted_from_response(self) -> None:
        """Deleted permissions leave stored IDs that no longer resolve — names are dropped."""
        svc = _service(id_to_name={12: "nmt.inference"})
        names = await svc.permission_ids_to_names([12, 99])
        assert names == ["nmt.inference"]


class TestAPIKeyReadRoutes:
    @pytest.mark.asyncio
    async def test_list_api_keys_returns_permission_names_not_ids(self) -> None:
        from app.routes.api_key import list_api_keys

        key = _api_key(permissions=[12, 15])
        mock_svc = AsyncMock()
        mock_svc.list_by_user = AsyncMock(return_value=[key])
        mock_svc.permission_name_map_for_keys = AsyncMock(
            return_value={12: "nmt.inference", 15: "asr.inference"},
        )

        response = await list_api_keys(user_id=key.user_id, _admin=MagicMock(), svc=mock_svc)

        assert response["success"] is True
        assert response["data"]["api_keys"][0]["permissions"] == [
            "nmt.inference",
            "asr.inference",
        ]
        assert all(not isinstance(p, int) for p in response["data"]["api_keys"][0]["permissions"])

    @pytest.mark.asyncio
    async def test_list_api_keys_omits_unresolved_permission_ids(self) -> None:
        from app.routes.api_key import list_api_keys

        key = _api_key(permissions=[12, 99])
        mock_svc = AsyncMock()
        mock_svc.list_by_user = AsyncMock(return_value=[key])
        mock_svc.permission_name_map_for_keys = AsyncMock(return_value={12: "nmt.inference"})

        response = await list_api_keys(user_id=key.user_id, _admin=MagicMock(), svc=mock_svc)

        assert response["data"]["api_keys"][0]["permissions"] == ["nmt.inference"]


class TestInferencePermissionCatalog:
    @pytest.mark.asyncio
    async def test_list_inference_permissions_returns_slim_name_and_label_only(self) -> None:
        from app.routes.permission import list_inference_permissions

        permission = Permission(
            id=12,
            name="nmt.inference",
            resource="nmt",
            action="inference",
        )
        mock_svc = AsyncMock()
        mock_svc.list_inference_permissions = AsyncMock(return_value=[permission])

        response = await list_inference_permissions(_admin=MagicMock(), svc=mock_svc)

        assert response["success"] is True
        items = response["data"]
        assert len(items) == 1
        assert items[0] == {"name": "nmt.inference", "label": "NMT.INFERENCE"}
        assert "id" not in items[0]
        assert "permission_id" not in items[0]
        assert "created_at" not in items[0]
        assert "updated_at" not in items[0]
        assert "resource" not in items[0]
        assert "action" not in items[0]
