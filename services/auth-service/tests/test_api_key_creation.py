"""create_api_key: the allocation-cap lock ordering, and the inference-only
permission restriction — both closing gaps a reviewer found with nothing
pinning them (a later refactor could silently reintroduce either with a
green build otherwise).
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.core.exceptions import ValidationError
from app.models.application import Application, ApplicationStatus
from app.models.tenant import Tenant, TenantStatus
from app.services.api_key_service import APIKeyService


def _application(*, tenant_id: int = 1, allocated_budget=None) -> Application:
    return Application(
        id=1, tenant_id=tenant_id, name="Test App",
        status=ApplicationStatus.ACTIVE, allocated_budget=allocated_budget,
    )


def _tenant(*, tier_id=uuid4()) -> Tenant:
    return Tenant(
        id=1, name="Acme", organisation="Acme",
        email="test-contact@example.invalid", status=TenantStatus.ACTIVE, tier_id=tier_id,
    )


def _service(*, applications=None, tenants=None) -> tuple:
    repo = AsyncMock()
    repo.get_permission_ids_by_names = AsyncMock(return_value={})
    cache = AsyncMock()
    applications = applications if applications is not None else AsyncMock()
    tenants = tenants if tenants is not None else AsyncMock()
    svc = APIKeyService(repo, cache, application_repo=applications, tenant_repo=tenants)
    return svc, repo, applications, tenants


class TestAllocationCapLockOrdering:
    """Pins the fix for the over-allocation race: the application row must
    be locked (get_by_id_for_update) before the existing total is summed,
    and both must happen before the key is persisted — see
    ApplicationRepository.get_by_id_for_update's docstring. Mirrors the
    existing get_by_id_for_update.assert_not_called()/call-order pattern in
    test_tenant_status_transitions.py."""

    @pytest.mark.asyncio
    async def test_lock_acquired_before_sum_when_allocating(self) -> None:
        application = _application()
        tenant = _tenant()
        applications = AsyncMock()
        applications.get_by_id_for_tenant = AsyncMock(return_value=application)
        applications.get_by_id_for_update = AsyncMock(return_value=application)
        applications.sum_api_key_allocated_percentage = AsyncMock(return_value=Decimal("10"))
        tenants = AsyncMock()
        tenants.get_by_id = AsyncMock(return_value=tenant)
        svc, repo, applications, tenants = _service(applications=applications, tenants=tenants)
        repo.get_permission_ids_by_names = AsyncMock(return_value={"nmt.inference": 1})

        call_order: list[str] = []
        applications.get_by_id_for_update.side_effect = lambda *_: call_order.append("lock") or application
        applications.sum_api_key_allocated_percentage.side_effect = (
            lambda *_: call_order.append("sum") or Decimal("10")
        )

        await svc.create_api_key(
            actor_user_id=uuid4(),
            key_name="test",
            permissions=["nmt.inference"],
            application_id=1,
            allocated_percentage=Decimal("20"),
            caller_tenant_id=1,
        )

        applications.get_by_id_for_update.assert_awaited_once_with(1)
        applications.sum_api_key_allocated_percentage.assert_awaited_once_with(1)
        assert call_order == ["lock", "sum"]

    @pytest.mark.asyncio
    async def test_lock_not_acquired_when_no_percentage_requested(self) -> None:
        """No allocated_percentage means nothing to protect — the lock is
        skipped entirely rather than taken unconditionally."""
        application = _application()
        tenant = _tenant()
        applications = AsyncMock()
        applications.get_by_id_for_tenant = AsyncMock(return_value=application)
        tenants = AsyncMock()
        tenants.get_by_id = AsyncMock(return_value=tenant)
        svc, repo, applications, tenants = _service(applications=applications, tenants=tenants)
        repo.get_permission_ids_by_names = AsyncMock(return_value={"nmt.inference": 1})

        await svc.create_api_key(
            actor_user_id=uuid4(),
            key_name="test",
            permissions=["nmt.inference"],
            application_id=1,
            allocated_percentage=None,
            caller_tenant_id=1,
        )

        applications.get_by_id_for_update.assert_not_called()

    @pytest.mark.asyncio
    async def test_over_allocation_still_rejected(self) -> None:
        application = _application()
        tenant = _tenant()
        applications = AsyncMock()
        applications.get_by_id_for_tenant = AsyncMock(return_value=application)
        applications.get_by_id_for_update = AsyncMock(return_value=application)
        applications.sum_api_key_allocated_percentage = AsyncMock(return_value=Decimal("90"))
        tenants = AsyncMock()
        tenants.get_by_id = AsyncMock(return_value=tenant)
        svc, repo, applications, tenants = _service(applications=applications, tenants=tenants)
        repo.get_permission_ids_by_names = AsyncMock(return_value={"nmt.inference": 1})

        with pytest.raises(ValidationError) as exc_info:
            await svc.create_api_key(
                actor_user_id=uuid4(),
                key_name="test",
                permissions=["nmt.inference"],
                application_id=1,
                allocated_percentage=Decimal("20"),
                caller_tenant_id=1,
            )

        assert exc_info.value.code == "ALLOCATION_TOTAL_EXCEEDED"
        repo.create.assert_not_called()


class TestBudgetDerivedFromLockedApplicationNotStaleRead:
    """Same bug class as ApplicationService.create_application (vipuldeveloper
    review, PR #1491): application is loaded unlocked first
    (get_by_id_for_tenant), then again — locked — via get_by_id_for_update,
    whose result is reassigned to `application` and later read for
    allocated_budget. Without ApplicationRepository.get_by_id_for_update
    forcing populate_existing(), a real AsyncSession would hand back the same
    identity-mapped object for both reads regardless of a concurrent budget
    revision landing in between. This pins the service-layer contract the
    same way: allocated_budget must derive from whatever get_by_id_for_update
    returns, not from the earlier get_by_id_for_tenant call."""

    @pytest.mark.asyncio
    async def test_uses_the_locked_read_not_the_earlier_unlocked_one(self) -> None:
        stale_application = _application(allocated_budget=Decimal("0.00"))
        # A concurrent tenant-budget revision recomputed this Application's
        # ceiling between the two reads — the locked read must see it.
        fresh_application = _application(allocated_budget=Decimal("1000.00"))
        tenant = _tenant()
        applications = AsyncMock()
        applications.get_by_id_for_tenant = AsyncMock(return_value=stale_application)
        applications.get_by_id_for_update = AsyncMock(return_value=fresh_application)
        applications.sum_api_key_allocated_percentage = AsyncMock(return_value=Decimal("0"))
        tenants = AsyncMock()
        tenants.get_by_id = AsyncMock(return_value=tenant)
        svc, repo, applications, tenants = _service(applications=applications, tenants=tenants)
        repo.get_permission_ids_by_names = AsyncMock(return_value={"nmt.inference": 1})

        _, api_key = await svc.create_api_key(
            actor_user_id=uuid4(),
            key_name="test",
            permissions=["nmt.inference"],
            application_id=1,
            allocated_percentage=Decimal("30"),
            caller_tenant_id=1,
        )

        # 1000.00 * 30% = 300.00, not 0.00 (the stale pre-revision figure).
        assert api_key.allocated_budget == Decimal("300.00")


class TestInferenceOnlyPermissionRestriction:
    """API keys may only ever hold inference permissions — see
    APIKeyRepository.get_permission_ids_by_names' docstring on why (no
    owning user to attribute a write to for API-key traffic any more, so an
    admin permission reaching a write via a key would silently NULL
    created_by/updated_by instead of failing). The repository itself
    enforces this with a SQL filter (action == 'inference'); at the service
    layer, a non-inference name is therefore indistinguishable from an
    unknown one — both come back missing from get_permission_ids_by_names,
    and _resolve_permission_names doesn't need to know which case it is."""

    @pytest.mark.asyncio
    async def test_non_inference_permission_name_is_rejected(self) -> None:
        application = _application()
        tenant = _tenant()
        applications = AsyncMock()
        applications.get_by_id_for_tenant = AsyncMock(return_value=application)
        tenants = AsyncMock()
        tenants.get_by_id = AsyncMock(return_value=tenant)
        svc, repo, applications, tenants = _service(applications=applications, tenants=tenants)
        # The real repository query filters action == 'inference' in SQL —
        # an admin permission like service.create simply never comes back,
        # the same as a genuinely unknown name. Mocking that absence here
        # is the correct unit-test boundary (repository is mocked
        # everywhere else in this suite too).
        repo.get_permission_ids_by_names = AsyncMock(return_value={})

        with pytest.raises(ValidationError) as exc_info:
            await svc.create_api_key(
                actor_user_id=uuid4(),
                key_name="test",
                permissions=["service.create"],
                application_id=1,
                caller_tenant_id=1,
            )

        assert exc_info.value.code == "INVALID_PERMISSION_NAMES"
        assert "service.create" in " ".join(exc_info.value.errors)
        repo.create.assert_not_called()

    @pytest.mark.asyncio
    async def test_inference_permission_name_is_accepted(self) -> None:
        application = _application()
        tenant = _tenant()
        applications = AsyncMock()
        applications.get_by_id_for_tenant = AsyncMock(return_value=application)
        tenants = AsyncMock()
        tenants.get_by_id = AsyncMock(return_value=tenant)
        svc, repo, applications, tenants = _service(applications=applications, tenants=tenants)
        repo.get_permission_ids_by_names = AsyncMock(return_value={"nmt.inference": 12})

        _raw_key, api_key = await svc.create_api_key(
            actor_user_id=uuid4(),
            key_name="test",
            permissions=["nmt.inference"],
            application_id=1,
            caller_tenant_id=1,
        )

        assert api_key.permissions == [12]
        repo.create.assert_awaited_once()
