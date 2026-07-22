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


def _make_service_orm(service_id: str = "svc-abc") -> MagicMock:
    instance = MagicMock()
    instance.service_id = service_id
    instance.model_id = "model-1"
    instance.model_version = "1.0"
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
            task={"type": "asr"},
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
            task={"type": "asr"},
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
            description="Updated description with enough length to pass validation.",
            task={"type": "asr"},
            costPerUnit=1.0,
            unitSize=1,
            tierIds=["tier-1"],
        )

        await svc.update_service(payload, updated_by="user-1")

        svc._services.apply_updates.assert_awaited_once()
        svc._services.commit.assert_awaited_once()
