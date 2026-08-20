"""Unit tests for model-management ModelService and ServiceService.

All external dependencies (DB, Redis, SQLAlchemy ORM) are mocked so the tests
run with plain pytest — no running services required.

Import strategy
---------------
The service modules live under ``app/services/model-management/`` (hyphenated
directory), so they are loaded via ``importlib.import_module``.  SQLAlchemy-
backed ORM classes are stubbed at module level before any app imports so the
service files can load even when the ``sqlalchemy`` package is unavailable
(or stubbed by an earlier test module).
"""

from __future__ import annotations

import sys
import types
from enum import Enum
from unittest.mock import AsyncMock, MagicMock

import importlib

import pytest

# ── Module-level stubs ────────────────────────────────────────────────────────
# Must run before any ``from app.*`` import so the stubs are in sys.modules
# when the service files resolve their own imports.


def _stub(name: str, **attrs) -> types.ModuleType:
    mod = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(mod, k, v)
    sys.modules.setdefault(name, mod)
    return mod


# VersionStatus is used as a real enum inside model_service.py comparisons.
class VersionStatus(str, Enum):
    ACTIVE = "ACTIVE"
    DEPRECATED = "DEPRECATED"


_stub("app.models").model_management = MagicMock()
_stub("app.models.model_management")
_stub(
    "app.models.model_management.model",
    Model=MagicMock,
    VersionStatus=VersionStatus,
)
_stub("app.models.model_management.service", Service=MagicMock)
_stub("app.repositories").model_management = MagicMock()
_stub("app.repositories.model_management")
_stub(
    "app.repositories.model_management.model_repository",
    ModelRepository=MagicMock,
)
_stub(
    "app.repositories.model_management.service_repository",
    ServiceRepository=MagicMock,
)

# ── Import service classes ────────────────────────────────────────────────────

_model_svc_mod = importlib.import_module("app.services.model-management.model_service")
_svc_svc_mod = importlib.import_module("app.services.model-management.service_service")

ModelService = _model_svc_mod.ModelService
ServiceService = _svc_svc_mod.ServiceService

ImmutableModelVersionError = _model_svc_mod.ImmutableModelVersionError
DuplicateModelVersionError = _model_svc_mod.DuplicateModelVersionError

from app.core.exceptions import EntityNotFoundError, ValidationError  # noqa: E402
from app.schemas.enums.model_management import VersionStatusEnum  # noqa: E402
from app.schemas.model_management.model import ModelCreateRequest, ModelUpdateRequest  # noqa: E402


# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_model_svc() -> ModelService:
    model_repo = MagicMock()
    model_repo.get_by_name_version = AsyncMock(return_value=None)
    model_repo.count_active_versions = AsyncMock(return_value=0)
    model_repo.add = AsyncMock()
    model_repo.commit = AsyncMock()
    model_repo.refresh = AsyncMock()
    model_repo.rollback = AsyncMock()
    model_repo.get_by_id_version = AsyncMock(return_value=None)
    model_repo.get_by_model_id = AsyncMock(return_value=None)
    model_repo.get_default_version = AsyncMock(return_value=None)
    model_repo.get_by_uuid = AsyncMock(return_value=None)
    model_repo.list_models = AsyncMock(return_value=[])
    model_repo.count_models = AsyncMock(return_value=0)
    model_repo.apply_updates = AsyncMock()
    model_repo.delete_by_model_id = AsyncMock()
    model_repo.count_active_versions = AsyncMock(return_value=0)

    service_repo = MagicMock()
    service_repo.list_published_for_model_version = AsyncMock(return_value=[])
    service_repo.list_unpublished_for_model_version = AsyncMock(return_value=[])
    service_repo.delete_unpublished_for_model_version = AsyncMock()

    cache = MagicMock()
    cache.get_model = AsyncMock(return_value=None)
    cache.set_model = AsyncMock()
    cache.invalidate_all_versions = AsyncMock()
    cache.invalidate_service = AsyncMock()

    return ModelService(model_repo=model_repo, service_repo=service_repo, cache=cache)


def _make_svc_svc() -> ServiceService:
    service_repo = MagicMock()
    service_repo.get_by_service_id = AsyncMock(return_value=None)
    service_repo.get_by_name = AsyncMock(return_value=None)
    service_repo.add = AsyncMock()
    service_repo.commit = AsyncMock()
    service_repo.rollback = AsyncMock()
    service_repo.delete_by_service_id = AsyncMock()
    service_repo.list_services = AsyncMock(return_value=[])
    service_repo.count_services = AsyncMock(return_value=0)
    service_repo.get_tier_names_by_ids = AsyncMock(return_value={"tier-1": "Tier 1"})

    model_repo = MagicMock()
    model_repo.get_by_id_version = AsyncMock(return_value=None)

    cache = MagicMock()
    cache.get_service = AsyncMock(return_value=None)
    cache.set_service = AsyncMock()
    cache.invalidate_service = AsyncMock()

    return ServiceService(service_repo=service_repo, model_repo=model_repo, cache=cache)


def _make_model_orm(
    *,
    model_id: str = "abc123",
    name: str = "test-model",
    version: str = "1.0",
    version_status: VersionStatus = VersionStatus.ACTIVE,
) -> MagicMock:
    m = MagicMock()
    m.model_id = model_id
    m.name = name
    m.version = version
    m.version_status = version_status
    m.inference_endpoint = {}
    m.task = {"type": "nmt"}
    m.created_at = None
    m.updated_at = None
    m.version_status_updated_at = None
    m.description = "desc"
    m.languages = []
    m.is_lang_detection_enabled = False
    m.is_multilingual = False
    m.domain = []
    m.submitter = {}
    m.license = "mit"
    m.license_url = None
    m.training_dataset = {"description": "test training dataset"}
    m.ref_url = "http://example.com"
    m.class_instance = None
    m.created_by = "user-1"
    m.updated_by = None
    return m


def _make_create_payload(**overrides) -> ModelCreateRequest:
    defaults = dict(
        name="test-model",
        version="1.0",
        description="A test model used for automated unit testing.",
        refUrl="http://example.com/model",
        task={"type": "nmt"},
        languages=[{"sourceLanguage": "en"}],
        license="mit",
        domain=["general"],
        submitter={"name": "Test User"},
        trainingDataset={"description": "test training dataset"},
    )
    defaults.update(overrides)
    return ModelCreateRequest(**defaults)


# ===========================================================================
# Section 1 — ModelService.create_model
# ===========================================================================


class TestModelServiceCreate:
    @pytest.mark.asyncio
    async def test_create_model_success_returns_model_id(self):
        svc = _make_model_svc()
        payload = _make_create_payload()
        model_id = await svc.create_model(payload, created_by="user-1")
        assert isinstance(model_id, str) and len(model_id) == 32

    @pytest.mark.asyncio
    async def test_create_model_calls_add_and_commit(self):
        svc = _make_model_svc()
        payload = _make_create_payload()
        await svc.create_model(payload, created_by="user-1")
        svc._models.add.assert_awaited_once()
        svc._models.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_create_model_duplicate_raises_error(self):
        svc = _make_model_svc()
        svc._models.get_by_name_version = AsyncMock(return_value=_make_model_orm())
        payload = _make_create_payload()
        with pytest.raises(DuplicateModelVersionError):
            await svc.create_model(payload, created_by="user-1")

    @pytest.mark.asyncio
    async def test_create_model_max_active_versions_exceeded_raises(self):
        svc = _make_model_svc()
        svc._models.count_active_versions = AsyncMock(return_value=999)
        payload = _make_create_payload()
        with pytest.raises(ValidationError):
            await svc.create_model(payload, created_by="user-1")

    @pytest.mark.asyncio
    async def test_create_model_warms_cache(self):
        svc = _make_model_svc()
        payload = _make_create_payload()
        await svc.create_model(payload, created_by="user-1")
        svc._cache.set_model.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_create_model_rollback_on_db_error(self):
        svc = _make_model_svc()
        svc._models.commit = AsyncMock(side_effect=RuntimeError("DB down"))
        payload = _make_create_payload()
        with pytest.raises(RuntimeError):
            await svc.create_model(payload, created_by="user-1")
        svc._models.rollback.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_create_model_adapter_config_stored_in_inference_endpoint(self):
        """adapterConfig from the create request is written into inference_endpoint['adapterConfig']."""
        from unittest.mock import patch as _patch
        svc = _make_model_svc()
        payload = _make_create_payload(adapterConfig={"version": "1", "inputs": []})

        model_ctor = MagicMock(return_value=_make_model_orm())
        with _patch.object(_model_svc_mod, "Model", model_ctor):
            await svc.create_model(payload, created_by="user-1")

        assert model_ctor.call_args.kwargs["inference_endpoint"] == {
            "adapterConfig": {"version": "1", "inputs": []},
        }


# ===========================================================================
# Section 2 — ModelService.update_model
# ===========================================================================


class TestModelServiceUpdate:
    @pytest.mark.asyncio
    async def test_update_model_version_required(self):
        svc = _make_model_svc()
        payload = ModelUpdateRequest(modelId="abc123", version=None, description="an updated model description here")
        with pytest.raises(ValidationError):
            await svc.update_model(payload, updated_by="user-1")

    @pytest.mark.asyncio
    async def test_update_model_not_found_raises(self):
        svc = _make_model_svc()
        svc._models.get_by_id_version = AsyncMock(return_value=None)
        svc._models.get_by_model_id = AsyncMock(return_value=None)
        payload = ModelUpdateRequest(modelId="missing", version="1.0", description="an updated model description here")
        with pytest.raises(EntityNotFoundError):
            await svc.update_model(payload, updated_by="user-1")

    @pytest.mark.asyncio
    async def test_update_model_immutable_when_published(self):
        svc = _make_model_svc()
        svc._models.get_by_id_version = AsyncMock(return_value=_make_model_orm())
        svc._services.list_published_for_model_version = AsyncMock(
            return_value=["svc-pub-1"]
        )
        payload = ModelUpdateRequest(modelId="abc123", version="1.0", description="an updated model description here")
        with pytest.raises(ImmutableModelVersionError):
            await svc.update_model(payload, updated_by="user-1")

    @pytest.mark.asyncio
    async def test_update_model_deprecated_blocked_by_settings(self):
        svc = _make_model_svc()
        instance = _make_model_orm(version_status=VersionStatus.DEPRECATED)
        svc._models.get_by_id_version = AsyncMock(return_value=instance)
        svc._services.list_published_for_model_version = AsyncMock(return_value=[])

        from app.core.config import settings
        original = settings.allow_deprecated_model_changes
        settings.allow_deprecated_model_changes = False

        try:
            payload = ModelUpdateRequest(modelId="abc123", version="1.0", description="an updated model description here")
            with pytest.raises(ValidationError):
                await svc.update_model(payload, updated_by="user-1")
        finally:
            settings.allow_deprecated_model_changes = original

    @pytest.mark.asyncio
    async def test_update_model_description_calls_apply_updates_and_commit(self):
        svc = _make_model_svc()
        instance = _make_model_orm()
        svc._models.get_by_id_version = AsyncMock(return_value=instance)
        svc._models.refresh = AsyncMock(return_value=instance)
        svc._services.list_published_for_model_version = AsyncMock(return_value=[])
        payload = ModelUpdateRequest(modelId="abc123", version="1.0", description="an updated model description here")
        await svc.update_model(payload, updated_by="user-1")
        svc._models.apply_updates.assert_awaited_once()
        svc._models.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_update_model_status_to_deprecated_calls_commit(self):
        svc = _make_model_svc()
        instance = _make_model_orm(version_status=VersionStatus.ACTIVE)
        svc._models.get_by_id_version = AsyncMock(return_value=instance)
        svc._models.refresh = AsyncMock(return_value=instance)
        svc._services.list_published_for_model_version = AsyncMock(return_value=[])
        payload = ModelUpdateRequest(
            modelId="abc123", version="1.0", versionStatus=VersionStatusEnum.DEPRECATED
        )
        await svc.update_model(payload, updated_by="user-1")
        svc._models.apply_updates.assert_awaited_once()
        svc._models.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_update_model_adapter_config_deep_merges_existing(self):
        """PATCH with adapterConfig deep-merges sent keys into the stored adapterConfig,
        leaving unmentioned keys (e.g. inputs) intact."""
        svc = _make_model_svc()
        instance = _make_model_orm()
        instance.inference_endpoint = {
            "adapterConfig": {"version": "1", "inputs": [{"tensor": "A"}]},
        }
        svc._models.get_by_id_version = AsyncMock(return_value=instance)
        svc._models.refresh = AsyncMock(return_value=instance)
        svc._services.list_published_for_model_version = AsyncMock(return_value=[])

        payload = ModelUpdateRequest(modelId="abc123", version="1.0", adapterConfig={"version": "2"})
        await svc.update_model(payload, updated_by="user-1")

        merged = svc._models.apply_updates.call_args.args[1]["inference_endpoint"]["adapterConfig"]
        assert merged["version"] == "2"
        assert merged["inputs"] == [{"tensor": "A"}]

    @pytest.mark.asyncio
    async def test_update_model_adapter_config_merges_from_legacy_snake_case_key(self):
        """For seeded rows with adapter_config (snake_case), PATCH must read that
        as the merge base and normalise the stored key to adapterConfig."""
        svc = _make_model_svc()
        instance = _make_model_orm()
        instance.inference_endpoint = {
            "adapter_config": {"version": "1", "inputs": [{"tensor": "A"}]},
        }
        svc._models.get_by_id_version = AsyncMock(return_value=instance)
        svc._models.refresh = AsyncMock(return_value=instance)
        svc._services.list_published_for_model_version = AsyncMock(return_value=[])

        payload = ModelUpdateRequest(modelId="abc123", version="1.0", adapterConfig={"version": "2"})
        await svc.update_model(payload, updated_by="user-1")

        ep = svc._models.apply_updates.call_args.args[1]["inference_endpoint"]
        assert "adapter_config" not in ep
        assert ep["adapterConfig"]["version"] == "2"
        assert ep["adapterConfig"]["inputs"] == [{"tensor": "A"}]


# ===========================================================================
# Section 3 — ModelService.delete_model
# ===========================================================================


class TestModelServiceDelete:
    @pytest.mark.asyncio
    async def test_delete_not_found_raises(self):
        svc = _make_model_svc()
        svc._models.get_by_model_id = AsyncMock(return_value=None)
        with pytest.raises(EntityNotFoundError):
            await svc.delete_model("missing-id")

    @pytest.mark.asyncio
    async def test_delete_blocked_by_published_service(self):
        svc = _make_model_svc()
        svc._models.get_by_model_id = AsyncMock(return_value=_make_model_orm())
        svc._services.list_published_for_model_version = AsyncMock(
            return_value=["svc-pub-1"]
        )
        with pytest.raises(ImmutableModelVersionError):
            await svc.delete_model("abc123")

    @pytest.mark.asyncio
    async def test_delete_success_calls_commit(self):
        svc = _make_model_svc()
        svc._models.get_by_model_id = AsyncMock(return_value=_make_model_orm())
        svc._services.list_published_for_model_version = AsyncMock(return_value=[])
        svc._services.list_unpublished_for_model_version = AsyncMock(return_value=[])
        await svc.delete_model("abc123")
        svc._models.delete_by_model_id.assert_awaited_once()
        svc._models.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_delete_cascades_unpublished_services(self):
        svc = _make_model_svc()
        svc._models.get_by_model_id = AsyncMock(return_value=_make_model_orm())
        svc._services.list_published_for_model_version = AsyncMock(return_value=[])
        unpub = MagicMock()
        unpub.service_id = "svc-unpub-1"
        svc._services.list_unpublished_for_model_version = AsyncMock(
            return_value=[unpub]
        )
        await svc.delete_model("abc123")
        svc._cache.invalidate_service.assert_awaited_once_with("svc-unpub-1")
        svc._services.delete_unpublished_for_model_version.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_delete_invalidates_cache(self):
        svc = _make_model_svc()
        svc._models.get_by_model_id = AsyncMock(return_value=_make_model_orm())
        svc._services.list_published_for_model_version = AsyncMock(return_value=[])
        svc._services.list_unpublished_for_model_version = AsyncMock(return_value=[])
        await svc.delete_model("abc123")
        svc._cache.invalidate_all_versions.assert_awaited_once_with("abc123")


# ===========================================================================
# Section 4 — ModelService.get_model
# ===========================================================================


class TestModelServiceGet:
    @pytest.mark.asyncio
    async def test_get_model_returns_cached_value(self):
        svc = _make_model_svc()
        cached_data = {"modelId": "abc123", "name": "test-model"}
        svc._cache.get_model = AsyncMock(return_value=cached_data)
        result = await svc.get_model("abc123")
        assert result == cached_data
        svc._models.get_default_version.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_get_model_not_found_raises(self):
        svc = _make_model_svc()
        svc._cache.get_model = AsyncMock(return_value=None)
        svc._models.get_by_id_version = AsyncMock(return_value=None)
        svc._models.get_default_version = AsyncMock(return_value=None)
        svc._models.get_by_uuid = AsyncMock(return_value=None)
        with pytest.raises(EntityNotFoundError):
            await svc.get_model("missing-id")

    @pytest.mark.asyncio
    async def test_get_model_warms_cache_on_miss(self):
        svc = _make_model_svc()
        svc._cache.get_model = AsyncMock(return_value=None)
        instance = _make_model_orm()
        svc._models.get_default_version = AsyncMock(return_value=instance)
        await svc.get_model("abc123")
        svc._cache.set_model.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_get_model_with_version_uses_id_version_lookup(self):
        svc = _make_model_svc()
        svc._cache.get_model = AsyncMock(return_value=None)
        instance = _make_model_orm()
        svc._models.get_by_id_version = AsyncMock(return_value=instance)
        await svc.get_model("abc123", version="1.0")
        svc._models.get_by_id_version.assert_awaited_once_with("abc123", "1.0")


# ===========================================================================
# Section 5 — ModelService.list_models
# ===========================================================================


class TestModelServiceList:
    @pytest.mark.asyncio
    async def test_list_models_returns_empty(self):
        svc = _make_model_svc()
        items, total = await svc.list_models()
        assert items == []
        assert total == 0

    @pytest.mark.asyncio
    async def test_list_models_with_pagination_calls_count(self):
        svc = _make_model_svc()
        svc._models.list_models = AsyncMock(return_value=[_make_model_orm()])
        svc._models.count_models = AsyncMock(return_value=10)
        items, total = await svc.list_models(offset=5, limit=2)
        svc._models.count_models.assert_awaited_once()
        assert total == 10

    @pytest.mark.asyncio
    async def test_count_does_not_forward_include_deprecated(self):
        """Known, pre-existing bug (flagged in AI4IDS-2854 review, NOT fixed
        here — out of that ticket's scope): `include_deprecated` filters the
        `items` list (via ModelRepository.list_models) but is never
        forwarded to `count_models`, which builds `meta.total`. So
        `?task_types=llm&include_deprecated=false` returns an `items` list
        narrower than its own `meta.total` — MeteringService.
        registry_model_count's docstring calls this out explicitly rather
        than silently assuming full parity with every possible call to this
        endpoint. This test pins the current (buggy) contract so a future
        change can't silently alter it without this test forcing the
        question of whether that docstring caveat still applies."""
        svc = _make_model_svc()
        svc._models.list_models = AsyncMock(return_value=[])
        svc._models.count_models = AsyncMock(return_value=10)

        await svc.list_models(task_types=["llm"], include_deprecated=False, offset=1, limit=5)

        svc._models.count_models.assert_awaited_once_with(
            task_types=["llm"], version_status=None, model_name=None, created_by=None,
        )


# ===========================================================================
# Section 6 — ServiceService.create_service
# ===========================================================================


class TestServiceServiceCreate:
    @pytest.mark.asyncio
    async def test_create_service_model_not_found_raises(self):
        svc = _make_svc_svc()
        svc._models.get_by_id_version = AsyncMock(return_value=None)
        from app.core.exceptions import ValidationError as VE
        from app.schemas.model_management.service import ServiceCreateRequest

        payload = ServiceCreateRequest(
            serviceId="svc-1",
            name="my-service",
            # description/infraDescription now enforce ULCA's
            # minimum lengths, and `inferenceEndPoint.schema` is required.
            serviceDescription="A test service used for automated unit tests.",
            hardwareDescription="test-hw-cluster",
            modelId="no-model",
            modelVersion="1.0",
            endpoint="http://localhost:8000",
            taskType="asr",
            inferenceEndPoint={"schema": [{"taskType": "asr", "request": {}, "response": {}}]},
            costPerUnit=0.01,
            unitSize=1,
            tierIds=["tier-1"],
            expectedResponseSchema={"output": [{"source": "test"}]},
        )
        with pytest.raises(VE):
            await svc.create_service(payload, created_by="user-1")

    @pytest.mark.asyncio
    async def test_create_service_duplicate_name_raises(self):
        svc = _make_svc_svc()
        model = _make_model_orm()
        svc._models.get_by_id_version = AsyncMock(return_value=model)
        svc._services.get_by_name = AsyncMock(return_value=MagicMock())

        from app.schemas.model_management.service import ServiceCreateRequest
        from unittest.mock import patch as _patch

        DupErr = _svc_svc_mod.DuplicateServiceNameError

        payload = ServiceCreateRequest(
            serviceId="svc-1",
            name="dup-service",
            serviceDescription="A test service used for automated unit tests.",
            hardwareDescription="test-hw-cluster",
            modelId="abc123",
            modelVersion="1.0",
            endpoint="http://localhost:8000",
            taskType="asr",
            inferenceEndPoint={"schema": [{"taskType": "asr", "request": {}, "response": {}}]},
            costPerUnit=0.01,
            unitSize=1,
            tierIds=["tier-1"],
            expectedResponseSchema={"output": [{"source": "test"}]},
        )
        # Endpoint validation is also triggered; mock it out.
        with pytest.raises(DupErr):
            with _patch.object(svc, "_validate_endpoint_for_model", new=AsyncMock()):
                await svc.create_service(payload, created_by="user-1")


# ===========================================================================
# Section 7 — ServiceService.delete_service
# ===========================================================================


class TestServiceServiceDelete:
    @pytest.mark.asyncio
    async def test_delete_service_not_found_raises(self):
        svc = _make_svc_svc()
        svc._services.get_by_service_id = AsyncMock(return_value=None)
        with pytest.raises(EntityNotFoundError):
            await svc.delete_service("missing-svc")

    @pytest.mark.asyncio
    async def test_delete_published_service_raises(self):
        svc = _make_svc_svc()
        instance = MagicMock()
        instance.service_id = "svc-1"
        instance.is_published = True
        svc._services.get_by_service_id = AsyncMock(return_value=instance)

        PublishedErr = _svc_svc_mod.PublishedServiceImmutableError
        with pytest.raises(PublishedErr):
            await svc.delete_service("svc-1")

    @pytest.mark.asyncio
    async def test_delete_unpublished_service_commits(self):
        svc = _make_svc_svc()
        instance = MagicMock()
        instance.service_id = "svc-1"
        instance.is_published = False
        svc._services.get_by_service_id = AsyncMock(return_value=instance)
        await svc.delete_service("svc-1")
        svc._services.delete_by_service_id.assert_awaited_once_with("svc-1")
        svc._services.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_delete_invalidates_cache(self):
        svc = _make_svc_svc()
        instance = MagicMock()
        instance.service_id = "svc-del"
        instance.is_published = False
        svc._services.get_by_service_id = AsyncMock(return_value=instance)
        await svc.delete_service("svc-del")
        svc._cache.invalidate_service.assert_awaited_once_with("svc-del")
