"""Unit tests: update_service completes successfully (AI4IDS-1766).

Regression: PATCH /api/v1/services was raising POLICY_CONSTRAINT_VIOLATION for
valid policy combinations, preventing all policy-bearing updates from going
through. These tests verify the happy path reaches apply_updates + commit.
"""

import sys
import types
from unittest.mock import AsyncMock, MagicMock

import pytest

import importlib

# ── Module-level stubs ───────────────────────────────────────────────────────
# test_pii_management.py (collected before this file, p < s) inserts an empty
# stub for the 'sqlalchemy' package into sys.modules.  service_service.py
# imports SQLAlchemy-backed ORM model/repo classes at module level; stubbing
# those classes here lets the service module load without hitting the stub.


def _stub_svc(name: str, **attrs) -> types.ModuleType:
    mod = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(mod, k, v)
    sys.modules.setdefault(name, mod)
    return mod


_stub_svc("app.models")
_stub_svc("app.models.model_management")
_stub_svc("app.models.model_management.service", Service=MagicMock)
_stub_svc("app.models.model_management.model", Model=MagicMock)
_stub_svc("app.repositories")
_stub_svc("app.repositories.model_management")
_stub_svc("app.repositories.model_management.model_repository", ModelRepository=MagicMock)
_stub_svc("app.repositories.model_management.service_repository", ServiceRepository=MagicMock)

# ─────────────────────────────────────────────────────────────────────────────

from app.schemas.enums.model_management import (
    PolicyAccuracyEnum,
    PolicyCostEnum,
    PolicyLatencyEnum,
)
from app.schemas.model_management.service import ServicePolicy, ServiceUpdateRequest

# model-management directory is hyphenated; plain imports cannot resolve it.
ServiceService = importlib.import_module(
    "app.services.model-management.service_service"
).ServiceService


def _make_service_orm(service_id: str = "svc-abc", task_type: str = None) -> MagicMock:
    instance = MagicMock()
    instance.service_id = service_id
    instance.model_id = "model-1"
    instance.model_version = "1.0"
    instance.api_key = None
    instance.task_type = task_type
    return instance


def _make_svc(service_id: str = "svc-abc") -> ServiceService:
    service_repo = MagicMock()
    service_repo.get_by_service_id = AsyncMock(return_value=_make_service_orm(service_id))
    service_repo.apply_updates = AsyncMock()
    service_repo.commit = AsyncMock()
    service_repo.rollback = AsyncMock()
    service_repo.get_tier_names_by_ids = AsyncMock(return_value={"tier-1": "Tier 1"})

    model_repo = MagicMock()
    model_repo.get_by_id_version = AsyncMock(return_value=None)

    cache = MagicMock()
    cache.invalidate_service = AsyncMock()
    cache.set_service = AsyncMock()

    return ServiceService(
        service_repo=service_repo,
        model_repo=model_repo,
        cache=cache,
    )


class TestUpdateServicePolicy:
    @pytest.mark.asyncio
    async def test_update_with_sensitive_tier1_policy_succeeds(self) -> None:
        """sensitive + tier_1 was previously blocked; must now reach the DB."""
        svc = _make_svc()
        payload = ServiceUpdateRequest(
            serviceId="svc-abc",
            policy=ServicePolicy(
                accuracy=PolicyAccuracyEnum.SENSITIVE,
                cost=PolicyCostEnum.TIER_1,
            ),
            taskType="asr",
            costPerUnit=1.0,
            unitSize=1,
            tierIds=["tier-1"],
        )

        await svc.update_service(payload, updated_by="user-1")

        svc._services.apply_updates.assert_awaited_once()
        svc._services.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_update_with_low_latency_tier1_policy_succeeds(self) -> None:
        """latency='low' + tier_1 was previously blocked; must now reach the DB."""
        svc = _make_svc()
        payload = ServiceUpdateRequest(
            serviceId="svc-abc",
            policy=ServicePolicy(
                latency=PolicyLatencyEnum.LOW,
                cost=PolicyCostEnum.TIER_1,
            ),
            taskType="asr",
            costPerUnit=1.0,
            unitSize=1,
            tierIds=["tier-1"],
        )

        await svc.update_service(payload, updated_by="user-1")

        svc._services.apply_updates.assert_awaited_once()
        svc._services.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_update_non_policy_fields_succeeds(self) -> None:
        """Update without a policy field reaches the DB unaffected."""
        svc = _make_svc()
        payload = ServiceUpdateRequest(
            serviceId="svc-abc",
            serviceDescription="Updated description",
            taskType="asr",
            costPerUnit=1.0,
            unitSize=1,
            tierIds=["tier-1"],
        )

        await svc.update_service(payload, updated_by="user-1")

        svc._services.apply_updates.assert_awaited_once()
        svc._services.commit.assert_awaited_once()


class TestUpdateServiceTryItDefault:
    """isTryItDefault invariant: at most one default per task_type
    (AI4IDS Try-It fix — see mm_services.is_try_it_default migration)."""

    @pytest.mark.asyncio
    async def test_setting_try_it_default_clears_other_services_of_same_task_type(
        self,
    ) -> None:
        """Flagging service B as default must clear the flag on every other
        service sharing its task_type (simulates A previously being default)."""
        svc = _make_svc()
        svc._services.get_by_service_id = AsyncMock(
            return_value=_make_service_orm("svc-b", task_type="llm")
        )
        svc._services.clear_try_it_default = AsyncMock()

        payload = ServiceUpdateRequest(serviceId="svc-b", isTryItDefault=True)
        await svc.update_service(payload, updated_by="user-1")

        svc._services.clear_try_it_default.assert_awaited_once_with(
            task_type="llm", exclude_service_id="svc-b"
        )
        _, update_data = svc._services.apply_updates.call_args.args
        assert update_data["is_try_it_default"] is True
        svc._services.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_unsetting_try_it_default_does_not_clear_other_services(self) -> None:
        """isTryItDefault=False is just a plain field write — no other
        service's flag should be touched."""
        svc = _make_svc()
        svc._services.get_by_service_id = AsyncMock(
            return_value=_make_service_orm("svc-b", task_type="llm")
        )
        svc._services.clear_try_it_default = AsyncMock()

        payload = ServiceUpdateRequest(serviceId="svc-b", isTryItDefault=False)
        await svc.update_service(payload, updated_by="user-1")

        svc._services.clear_try_it_default.assert_not_awaited()
        _, update_data = svc._services.apply_updates.call_args.args
        assert update_data["is_try_it_default"] is False

    @pytest.mark.asyncio
    async def test_none_task_type_skips_clear_invariant(self) -> None:
        """Documented edge case: a None task_type intentionally skips the
        clear step (see the comment in update_service) since Try-It only
        ever surfaces nmt/llm services regardless of this flag's value."""
        svc = _make_svc()
        svc._services.get_by_service_id = AsyncMock(
            return_value=_make_service_orm("svc-c", task_type=None)
        )
        svc._services.clear_try_it_default = AsyncMock()

        payload = ServiceUpdateRequest(serviceId="svc-c", isTryItDefault=True)
        await svc.update_service(payload, updated_by="user-1")

        svc._services.clear_try_it_default.assert_not_awaited()
