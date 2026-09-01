"""create_api_key: the allocation-cap lock ordering, and the inference-only
permission restriction — both closing gaps a reviewer found with nothing
pinning them (a later refactor could silently reintroduce either with a
green build otherwise).
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, patch
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
    async def test_neither_allocation_given_is_rejected_before_any_lock(self) -> None:
        """A key must have SOME allocation (allocated_percentage or budget) —
        the ALLOCATION_REQUIRED check runs before the lock is ever
        considered, so an unallocated request never takes it. (There's no
        longer a valid "allocated_percentage ends up None" case that reaches
        the lock decision at all — one or the other is always required by
        the time we get there.)"""
        application = _application()
        tenant = _tenant()
        applications = AsyncMock()
        applications.get_by_id_for_tenant = AsyncMock(return_value=application)
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
                caller_tenant_id=1,
            )

        assert exc_info.value.code == "ALLOCATION_REQUIRED"
        applications.get_by_id_for_update.assert_not_called()
        repo.create.assert_not_called()

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


class TestBudgetParam:
    """budget (a raw ₹ ceiling, alternative to allocated_percentage) used to
    bypass ALLOCATION_TOTAL_EXCEEDED entirely and never populate
    allocated_percentage/allocated_budget — invisible to the sum both that
    check and the Budget Allocation endpoints' resolve_level depend on. Now
    converted to allocated_percentage up front, so it goes through the exact same
    path as any other request."""

    @pytest.mark.asyncio
    async def test_budget_and_percentage_together_rejected(self) -> None:
        application = _application(allocated_budget=Decimal("50000.00"))
        tenant = _tenant()
        applications = AsyncMock()
        applications.get_by_id_for_tenant = AsyncMock(return_value=application)
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
                budget=Decimal("1000"),
                caller_tenant_id=1,
            )

        assert exc_info.value.code == "PERCENTAGE_AMOUNT_MISMATCH"
        repo.create.assert_not_called()

    @pytest.mark.asyncio
    async def test_budget_without_application_budget_rejected(self) -> None:
        application = _application(allocated_budget=None)
        tenant = _tenant()
        applications = AsyncMock()
        applications.get_by_id_for_tenant = AsyncMock(return_value=application)
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
                budget=Decimal("1000"),
                caller_tenant_id=1,
            )

        assert exc_info.value.code == "APPLICATION_BUDGET_NOT_SET"
        repo.create.assert_not_called()

    @pytest.mark.asyncio
    async def test_budget_is_converted_and_enforces_the_cap(self) -> None:
        """The bug this fixes: budget=15000 against a 50000 Application
        budget is 30% — an existing 80% already allocated must reject it,
        exactly as it would for an equivalent allocated_percentage=30 request."""
        application = _application(allocated_budget=Decimal("50000.00"))
        tenant = _tenant()
        applications = AsyncMock()
        applications.get_by_id_for_tenant = AsyncMock(return_value=application)
        applications.get_by_id_for_update = AsyncMock(return_value=application)
        applications.sum_api_key_allocated_percentage = AsyncMock(return_value=Decimal("80"))
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
                budget=Decimal("15000"),
                caller_tenant_id=1,
            )

        assert exc_info.value.code == "ALLOCATION_TOTAL_EXCEEDED"
        repo.create.assert_not_called()

    @pytest.mark.asyncio
    async def test_budget_populates_percentage_and_budget_columns(self) -> None:
        application = _application(allocated_budget=Decimal("50000.00"))
        tenant = _tenant()
        applications = AsyncMock()
        applications.get_by_id_for_tenant = AsyncMock(return_value=application)
        applications.get_by_id_for_update = AsyncMock(return_value=application)
        applications.sum_api_key_allocated_percentage = AsyncMock(return_value=Decimal("0"))
        tenants = AsyncMock()
        tenants.get_by_id = AsyncMock(return_value=tenant)
        svc, repo, applications, tenants = _service(applications=applications, tenants=tenants)
        repo.get_permission_ids_by_names = AsyncMock(return_value={"nmt.inference": 1})

        with patch(
            "app.services.budget_usage.write_budget_snapshot", AsyncMock()
        ) as write_snap:
            _, api_key = await svc.create_api_key(
                actor_user_id=uuid4(),
                key_name="test",
                permissions=["nmt.inference"],
                application_id=1,
                budget=Decimal("15000"),
                caller_tenant_id=1,
            )

        # 15000 / 50000 * 100 = 30.00% — no longer NULL/invisible to the cap check.
        assert api_key.allocated_percentage == Decimal("30.00")
        assert api_key.allocated_budget == Decimal("15000.00")
        write_snap.assert_awaited_once_with({api_key.id: Decimal("15000.00")}, None)

    @pytest.mark.asyncio
    async def test_budget_is_kept_exact_even_when_percentage_rounds(self) -> None:
        """The bug this fixes: budget=1000 against a 30000 Application
        budget is 3.333...%, which quantizes to 3.33% for the cap check —
        but allocated_budget must stay the exact 1000 requested, NOT
        re-derived as 30000 * 3.33 / 100 = 999.90. Re-deriving it would
        silently shrink the ceiling below what was actually asked for."""
        application = _application(allocated_budget=Decimal("30000.00"))
        tenant = _tenant()
        applications = AsyncMock()
        applications.get_by_id_for_tenant = AsyncMock(return_value=application)
        applications.get_by_id_for_update = AsyncMock(return_value=application)
        applications.sum_api_key_allocated_percentage = AsyncMock(return_value=Decimal("0"))
        tenants = AsyncMock()
        tenants.get_by_id = AsyncMock(return_value=tenant)
        svc, repo, applications, tenants = _service(applications=applications, tenants=tenants)
        repo.get_permission_ids_by_names = AsyncMock(return_value={"nmt.inference": 1})

        with patch(
            "app.services.budget_usage.write_budget_snapshot", AsyncMock()
        ) as write_snap:
            _, api_key = await svc.create_api_key(
                actor_user_id=uuid4(),
                key_name="test",
                permissions=["nmt.inference"],
                application_id=1,
                budget=Decimal("1000"),
                caller_tenant_id=1,
            )

        assert api_key.allocated_percentage == Decimal("3.33")
        assert api_key.allocated_budget == Decimal("1000.00")
        write_snap.assert_awaited_once_with({api_key.id: Decimal("1000.00")}, None)

    @pytest.mark.asyncio
    async def test_budget_rounding_to_zero_percent_is_rejected(self) -> None:
        """A budget under 0.005% of the Application's own budget would
        quantize to 0.00% — the cap check (and the Budget Allocation
        endpoints' resolve_level, which sums percentages) would treat that as no
        allocation at all, exactly the invisibility bug this whole change
        exists to close. Must reject outright instead of silently creating
        a key with a real ₹ ceiling but a 0.00% footprint."""
        application = _application(allocated_budget=Decimal("10000000.00"))
        tenant = _tenant()
        applications = AsyncMock()
        applications.get_by_id_for_tenant = AsyncMock(return_value=application)
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
                budget=Decimal("1"),
                caller_tenant_id=1,
            )

        assert exc_info.value.code == "BUDGET_TOO_SMALL"
        repo.create.assert_not_called()
        applications.get_by_id_for_update.assert_not_called()

    @pytest.mark.asyncio
    async def test_neither_percentage_nor_budget_given_is_rejected(self) -> None:
        application = _application(allocated_budget=Decimal("50000.00"))
        tenant = _tenant()
        applications = AsyncMock()
        applications.get_by_id_for_tenant = AsyncMock(return_value=application)
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
                caller_tenant_id=1,
            )

        assert exc_info.value.code == "ALLOCATION_REQUIRED"
        repo.create.assert_not_called()


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
        applications.get_by_id_for_update = AsyncMock(return_value=application)
        applications.sum_api_key_allocated_percentage = AsyncMock(return_value=Decimal("0"))
        tenants = AsyncMock()
        tenants.get_by_id = AsyncMock(return_value=tenant)
        svc, repo, applications, tenants = _service(applications=applications, tenants=tenants)
        repo.get_permission_ids_by_names = AsyncMock(return_value={"nmt.inference": 12})

        _raw_key, api_key = await svc.create_api_key(
            actor_user_id=uuid4(),
            key_name="test",
            permissions=["nmt.inference"],
            application_id=1,
            allocated_percentage=Decimal("10"),
            caller_tenant_id=1,
        )

        assert api_key.permissions == [12]
        repo.create.assert_awaited_once()
