"""create_api_key: the allocation-cap lock ordering, and the inference-only
permission restriction — both closing gaps a reviewer found with nothing
pinning them (a later refactor could silently reintroduce either with a
green build otherwise).
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
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


def _tenant(*, tier_id=uuid4(), allocated_budget=None) -> Tenant:
    return Tenant(
        id=1, name="Acme", organisation="Acme",
        email="test-contact@example.invalid", status=TenantStatus.ACTIVE, tier_id=tier_id,
        allocated_budget=allocated_budget,
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
        tenants.get_operational_fields = AsyncMock(return_value=tenant)
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
    async def test_neither_allocation_given_creates_uncapped_key_when_tenant_has_budget(
        self,
    ) -> None:
        """Omitting both allocated_percentage and budget is allowed (product
        decision, 2026: the prior ALLOCATION_REQUIRED block is removed) — a
        caller may deliberately create an uncapped Key. No allocation means
        no lock is ever needed (this Key never contends for a share of the
        Application's 100%), and — since the owning Tenant DOES have a real
        Budget here — the Key is NOT seeded budget-exhausted: it's genuinely
        unlimited, tracked by nothing, exactly the state pre-existing
        NULL-allocation keys already had."""
        application = _application()
        tenant = _tenant(allocated_budget=Decimal("100000.00"))
        applications = AsyncMock()
        applications.get_by_id_for_tenant = AsyncMock(return_value=application)
        tenants = AsyncMock()
        tenants.get_operational_fields = AsyncMock(return_value=tenant)
        svc, repo, applications, tenants = _service(applications=applications, tenants=tenants)
        repo.get_permission_ids_by_names = AsyncMock(return_value={"nmt.inference": 1})

        _raw_key, api_key, _exhausted = await svc.create_api_key(
            actor_user_id=uuid4(),
            key_name="test",
            permissions=["nmt.inference"],
            application_id=1,
            caller_tenant_id=1,
        )

        assert api_key.allocated_percentage is None
        assert api_key.allocated_budget is None
        applications.get_by_id_for_update.assert_not_called()
        repo.create.assert_awaited_once()
        payload = svc._cache.set_api_key_cache.call_args.args[2]
        assert "budget-exhausted" not in payload

    @pytest.mark.asyncio
    async def test_neither_allocation_given_is_exhausted_when_tenant_has_no_budget(
        self,
    ) -> None:
        """The one case still blocked outright: a Tenant with NO Budget at
        all. An uncapped Key under it must mean "nothing to spend," not
        "unlimited" — same reasoning as
        test_key_under_a_tenant_with_no_budget_configured_is_flagged_exhausted
        above, but reached via omission instead of a percentage that
        resolves to None."""
        application = _application()
        tenant = _tenant(allocated_budget=None)
        applications = AsyncMock()
        applications.get_by_id_for_tenant = AsyncMock(return_value=application)
        tenants = AsyncMock()
        tenants.get_operational_fields = AsyncMock(return_value=tenant)
        svc, repo, applications, tenants = _service(applications=applications, tenants=tenants)
        repo.get_permission_ids_by_names = AsyncMock(return_value={"nmt.inference": 1})

        _raw_key, api_key, _exhausted = await svc.create_api_key(
            actor_user_id=uuid4(),
            key_name="test",
            permissions=["nmt.inference"],
            application_id=1,
            caller_tenant_id=1,
        )

        assert api_key.allocated_percentage is None
        assert api_key.allocated_budget is None
        payload = svc._cache.set_api_key_cache.call_args.args[2]
        assert payload["budget-exhausted"] == "1"

    @pytest.mark.asyncio
    async def test_over_allocation_still_rejected(self) -> None:
        application = _application()
        tenant = _tenant()
        applications = AsyncMock()
        applications.get_by_id_for_tenant = AsyncMock(return_value=application)
        applications.get_by_id_for_update = AsyncMock(return_value=application)
        applications.sum_api_key_allocated_percentage = AsyncMock(return_value=Decimal("90"))
        tenants = AsyncMock()
        tenants.get_operational_fields = AsyncMock(return_value=tenant)
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


class TestBudgetExpiredBlocksKeyCreation:
    """create_api_key must not hand out a new key against a tenant whose
    budget effective window has already ended — before this, nothing here
    ever looked at budget_effective_to at all: a key could be freely
    created (and would even work for its very first request, since
    /auth/validate's budget-expired Redis flag only gets set reactively by
    the next Kafka-billed message) for a tenant that was already expired.
    This checks tenants.budget_effective_to directly, not the Redis flag, so
    it can't have that same lag — see app.utils.budget_window."""

    @pytest.mark.asyncio
    async def test_expired_window_rejected_before_tier_check(self) -> None:
        """Checked ahead of NO_ACTIVE_TIER — a lapsed window is the more
        fundamental block, and cheaper (no further lookups needed either
        way, but this comes first in the method)."""
        application = _application()
        tenant = _tenant(tier_id=None)  # would ALSO fail NO_ACTIVE_TIER — proves ordering
        tenant.budget_effective_to = datetime.now(timezone.utc) - timedelta(days=1)
        applications = AsyncMock()
        applications.get_by_id_for_tenant = AsyncMock(return_value=application)
        tenants = AsyncMock()
        tenants.get_operational_fields = AsyncMock(return_value=tenant)
        svc, repo, applications, tenants = _service(applications=applications, tenants=tenants)

        with pytest.raises(ValidationError) as exc_info:
            await svc.create_api_key(
                actor_user_id=uuid4(),
                key_name="test",
                permissions=["nmt.inference"],
                application_id=1,
                allocated_percentage=Decimal("20"),
                caller_tenant_id=1,
            )

        assert exc_info.value.code == "BUDGET_EXPIRED"
        repo.create.assert_not_called()
        applications.get_by_id_for_update.assert_not_called()

    @pytest.mark.asyncio
    async def test_future_effective_to_is_allowed(self) -> None:
        application = _application()
        tenant = _tenant()
        tenant.budget_effective_to = datetime.now(timezone.utc) + timedelta(days=30)
        applications = AsyncMock()
        applications.get_by_id_for_tenant = AsyncMock(return_value=application)
        applications.get_by_id_for_update = AsyncMock(return_value=application)
        applications.sum_api_key_allocated_percentage = AsyncMock(return_value=Decimal("0"))
        tenants = AsyncMock()
        tenants.get_operational_fields = AsyncMock(return_value=tenant)
        svc, repo, applications, tenants = _service(applications=applications, tenants=tenants)
        repo.get_permission_ids_by_names = AsyncMock(return_value={"nmt.inference": 1})

        await svc.create_api_key(
            actor_user_id=uuid4(),
            key_name="test",
            permissions=["nmt.inference"],
            application_id=1,
            allocated_percentage=Decimal("20"),
            caller_tenant_id=1,
        )

        repo.create.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_no_effective_to_is_allowed(self) -> None:
        """None means no window was ever set (or a pre-fix row) — must not
        block key creation for every tenant that predates this feature."""
        application = _application()
        tenant = _tenant()
        tenant.budget_effective_to = None
        applications = AsyncMock()
        applications.get_by_id_for_tenant = AsyncMock(return_value=application)
        applications.get_by_id_for_update = AsyncMock(return_value=application)
        applications.sum_api_key_allocated_percentage = AsyncMock(return_value=Decimal("0"))
        tenants = AsyncMock()
        tenants.get_operational_fields = AsyncMock(return_value=tenant)
        svc, repo, applications, tenants = _service(applications=applications, tenants=tenants)
        repo.get_permission_ids_by_names = AsyncMock(return_value={"nmt.inference": 1})

        await svc.create_api_key(
            actor_user_id=uuid4(),
            key_name="test",
            permissions=["nmt.inference"],
            application_id=1,
            allocated_percentage=Decimal("20"),
            caller_tenant_id=1,
        )

        repo.create.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_naive_effective_to_treated_as_utc(self) -> None:
        application = _application()
        tenant = _tenant(tier_id=None)
        tenant.budget_effective_to = (datetime.now(timezone.utc) - timedelta(days=1)).replace(tzinfo=None)
        applications = AsyncMock()
        applications.get_by_id_for_tenant = AsyncMock(return_value=application)
        tenants = AsyncMock()
        tenants.get_operational_fields = AsyncMock(return_value=tenant)
        svc, repo, applications, tenants = _service(applications=applications, tenants=tenants)

        with pytest.raises(ValidationError) as exc_info:
            await svc.create_api_key(
                actor_user_id=uuid4(),
                key_name="test",
                permissions=["nmt.inference"],
                application_id=1,
                allocated_percentage=Decimal("20"),
                caller_tenant_id=1,
            )

        assert exc_info.value.code == "BUDGET_EXPIRED"


class TestExplicitZeroAllocationRejected:
    """Explicit 0 is a different state from omitting the field entirely
    (None now means "intentionally uncapped," allowed) — 0 means "a ₹0
    ceiling," an "Active"-looking Key that can never spend anything and is
    indistinguishable from key sprawl in the UI. Rejected the same way
    BUDGET_TOO_SMALL already rejects a `budget` that rounds to 0.00% derived
    from a tiny amount."""

    @pytest.mark.asyncio
    async def test_explicit_zero_percentage_is_rejected(self) -> None:
        application = _application()
        tenant = _tenant()
        applications = AsyncMock()
        applications.get_by_id_for_tenant = AsyncMock(return_value=application)
        tenants = AsyncMock()
        tenants.get_operational_fields = AsyncMock(return_value=tenant)
        svc, repo, applications, tenants = _service(applications=applications, tenants=tenants)
        repo.get_permission_ids_by_names = AsyncMock(return_value={"nmt.inference": 1})

        with pytest.raises(ValidationError) as exc_info:
            await svc.create_api_key(
                actor_user_id=uuid4(),
                key_name="test",
                permissions=["nmt.inference"],
                application_id=1,
                allocated_percentage=Decimal("0"),
                caller_tenant_id=1,
            )

        assert exc_info.value.code == "BUDGET_TOO_SMALL"
        applications.get_by_id_for_update.assert_not_called()
        repo.create.assert_not_called()


class TestCommittedTotalCountsActiveCeilingsAndRevokedSpend:
    """ALLOCATION_TOTAL_EXCEEDED above only weighs ACTIVE keys'
    allocated_percentage — it verifies ceilings sum to <=100%, but that's
    silent on ₹ once a revoked key's spend is added back into the picture.
    The BUDGET_OVERCOMMITTED check mirrors AllocationService's full
    two-half contract: each ACTIVE key is charged the greater of its own
    PERCENTAGE-derived ceiling (still reserved, whether spent or not) or
    what it's actually spent (an over-exhausted key, from the
    one-call-past-budget design, can overshoot its own allocated_budget);
    each REVOKED key is charged only its consumed spend (its ceiling is no
    longer reserved, but the spend is real and permanent). Missing the
    revoked half lets revoking an overspent key and creating a fresh one
    erase the overspend from every check this function runs; missing the
    active half leaves an active sibling's still-unspent — but already
    promised — ceiling invisible. Percentage-derived, not
    key.allocated_budget, on purpose: allocated_budget is kept as the exact
    ₹ a currency-path create/resize was given, which can disagree with its
    OWN stored allocated_percentage by up to allocated_budget / 20000 —
    measuring this check in raw ₹ would put it on a different basis than
    ALLOCATION_TOTAL_EXCEEDED and the frontend's available-percentage
    figure, both of which are percent-based, and could reject a Key
    allocated exactly the remaining share those checks just approved."""

    @pytest.mark.asyncio
    async def test_active_key_created_via_the_currency_path_is_charged_its_percentage_not_its_exact_rupees(
        self,
    ) -> None:
        """The reviewer's rounding-drift scenario: a 30,000 Application
        budget holds one active key created with budget=1000 — stored as
        allocated_percentage=3.33 (rounded) and allocated_budget=1000
        (kept exact, NOT re-derived from the rounded percentage — see the
        currency-path comment in create_api_key). A new key requesting the
        entire remaining 96.67% must succeed: charging the active key its
        raw ₹1000 would leave only 30000 - 1000 - 29001 = -1 of headroom
        and wrongly reject it; charging it its percentage-derived ceiling
        (3.33% of 30000 = 999.00) puts this check on the same percent basis
        as ALLOCATION_TOTAL_EXCEEDED (3.33 + 96.67 = 100.00, which already
        passed) and the request fits exactly."""
        application = _application(allocated_budget=Decimal("30000"))
        tenant = _tenant()
        active_key = MagicMock(
            id=902, is_active=True, allocated_budget=Decimal("1000"),
            allocated_percentage=Decimal("3.33"),
        )
        applications = AsyncMock()
        applications.get_by_id_for_tenant = AsyncMock(return_value=application)
        applications.get_by_id_for_update = AsyncMock(return_value=application)
        applications.sum_api_key_allocated_percentage = AsyncMock(return_value=Decimal("3.33"))
        tenants = AsyncMock()
        tenants.get_operational_fields = AsyncMock(return_value=tenant)
        svc, repo, applications, tenants = _service(applications=applications, tenants=tenants)
        repo.get_permission_ids_by_names = AsyncMock(return_value={"nmt.inference": 1})
        repo.list_by_application = AsyncMock(return_value=[active_key])

        with patch(
            "app.services.api_key_service.budget_usage.fetch_budget_usage",
            new=AsyncMock(return_value={902: (Decimal("0"), Decimal("1000"))}),
        ):
            _raw_key, api_key, _exhausted = await svc.create_api_key(
                actor_user_id=uuid4(),
                key_name="test",
                permissions=["nmt.inference"],
                application_id=1,
                allocated_percentage=Decimal("96.67"),
                caller_tenant_id=1,
            )

        assert api_key.allocated_budget == Decimal("29001.00")
        repo.create.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_active_keys_unspent_ceiling_blocks_a_new_key_even_with_small_revoked_spend(
        self,
    ) -> None:
        """The reviewer's exact scenario: a 10,000 Application budget, a
        revoked key that only spent 1,000, and an active key already
        holding a 5,000 ceiling it hasn't spent. A new 5,000 key must still
        be rejected (1,000 + 5,000 + 5,000 = 11,000 > 10,000) even though
        the revoked spend alone (1,000) would have left room — a
        consumed-only check would wrongly allow this."""
        application = _application(allocated_budget=Decimal("10000"))
        tenant = _tenant()
        revoked_key = MagicMock(id=901, is_active=False, allocated_budget=Decimal("9000"))
        active_key = MagicMock(
            id=902, is_active=True, allocated_budget=Decimal("5000"),
            allocated_percentage=Decimal("50"),
        )
        applications = AsyncMock()
        applications.get_by_id_for_tenant = AsyncMock(return_value=application)
        applications.get_by_id_for_update = AsyncMock(return_value=application)
        applications.sum_api_key_allocated_percentage = AsyncMock(return_value=Decimal("50"))
        tenants = AsyncMock()
        tenants.get_operational_fields = AsyncMock(return_value=tenant)
        svc, repo, applications, tenants = _service(applications=applications, tenants=tenants)
        repo.get_permission_ids_by_names = AsyncMock(return_value={"nmt.inference": 1})
        repo.list_by_application = AsyncMock(return_value=[revoked_key, active_key])

        with patch(
            "app.services.api_key_service.budget_usage.fetch_budget_usage",
            new=AsyncMock(
                return_value={
                    901: (Decimal("1000"), Decimal("1000")),
                    902: (Decimal("0"), Decimal("5000")),
                }
            ),
        ):
            with pytest.raises(ValidationError) as exc_info:
                await svc.create_api_key(
                    actor_user_id=uuid4(),
                    key_name="test",
                    permissions=["nmt.inference"],
                    application_id=1,
                    allocated_percentage=Decimal("50"),
                    caller_tenant_id=1,
                )

        assert exc_info.value.code == "BUDGET_OVERCOMMITTED"
        repo.create.assert_not_called()

    @pytest.mark.asyncio
    async def test_an_over_exhausted_active_key_is_charged_its_actual_spend_not_its_ceiling(
        self,
    ) -> None:
        """An active key that overspent past its own ceiling (the one call
        the design allows through after exhaustion) must be charged its
        real spend, not the smaller ceiling — max(ceiling, consumed)."""
        application = _application(allocated_budget=Decimal("10000"))
        tenant = _tenant()
        over_exhausted_key = MagicMock(
            id=902, is_active=True, allocated_budget=Decimal("3000"),
            allocated_percentage=Decimal("30"),
        )
        applications = AsyncMock()
        applications.get_by_id_for_tenant = AsyncMock(return_value=application)
        applications.get_by_id_for_update = AsyncMock(return_value=application)
        applications.sum_api_key_allocated_percentage = AsyncMock(return_value=Decimal("30"))
        tenants = AsyncMock()
        tenants.get_operational_fields = AsyncMock(return_value=tenant)
        svc, repo, applications, tenants = _service(applications=applications, tenants=tenants)
        repo.get_permission_ids_by_names = AsyncMock(return_value={"nmt.inference": 1})
        repo.list_by_application = AsyncMock(return_value=[over_exhausted_key])

        with patch(
            "app.services.api_key_service.budget_usage.fetch_budget_usage",
            new=AsyncMock(return_value={902: (Decimal("4000"), Decimal("3000"))}),
        ):
            with pytest.raises(ValidationError) as exc_info:
                await svc.create_api_key(
                    actor_user_id=uuid4(),
                    key_name="test",
                    permissions=["nmt.inference"],
                    application_id=1,
                    allocated_percentage=Decimal("65"),
                    caller_tenant_id=1,
                )

        # committed_total = max(3000, 4000) = 4000; new key = 6500; 10500 > 10000.
        assert exc_info.value.code == "BUDGET_OVERCOMMITTED"
        repo.create.assert_not_called()

    @pytest.mark.asyncio
    async def test_revoked_keys_spend_blocks_a_new_key_that_would_overcommit(self) -> None:
        application = _application(allocated_budget=Decimal("10000"))
        tenant = _tenant()
        revoked_key = MagicMock(id=901, is_active=False)
        applications = AsyncMock()
        applications.get_by_id_for_tenant = AsyncMock(return_value=application)
        applications.get_by_id_for_update = AsyncMock(return_value=application)
        applications.sum_api_key_allocated_percentage = AsyncMock(return_value=Decimal("0"))
        tenants = AsyncMock()
        tenants.get_operational_fields = AsyncMock(return_value=tenant)
        svc, repo, applications, tenants = _service(applications=applications, tenants=tenants)
        repo.get_permission_ids_by_names = AsyncMock(return_value={"nmt.inference": 1})
        repo.list_by_application = AsyncMock(return_value=[revoked_key])

        with patch(
            "app.services.api_key_service.budget_usage.fetch_budget_usage",
            new=AsyncMock(return_value={901: (Decimal("9500"), Decimal("9500"))}),
        ):
            with pytest.raises(ValidationError) as exc_info:
                await svc.create_api_key(
                    actor_user_id=uuid4(),
                    key_name="test",
                    permissions=["nmt.inference"],
                    application_id=1,
                    allocated_percentage=Decimal("90"),
                    caller_tenant_id=1,
                )

        assert exc_info.value.code == "BUDGET_OVERCOMMITTED"
        repo.create.assert_not_called()

    @pytest.mark.asyncio
    async def test_new_key_allowed_when_prior_spend_leaves_room(self) -> None:
        application = _application(allocated_budget=Decimal("10000"))
        tenant = _tenant()
        revoked_key = MagicMock(id=901, is_active=False)
        applications = AsyncMock()
        applications.get_by_id_for_tenant = AsyncMock(return_value=application)
        applications.get_by_id_for_update = AsyncMock(return_value=application)
        applications.sum_api_key_allocated_percentage = AsyncMock(return_value=Decimal("0"))
        tenants = AsyncMock()
        tenants.get_operational_fields = AsyncMock(return_value=tenant)
        svc, repo, applications, tenants = _service(applications=applications, tenants=tenants)
        repo.get_permission_ids_by_names = AsyncMock(return_value={"nmt.inference": 1})
        repo.list_by_application = AsyncMock(return_value=[revoked_key])

        with patch(
            "app.services.api_key_service.budget_usage.fetch_budget_usage",
            new=AsyncMock(return_value={901: (Decimal("2000"), Decimal("2000"))}),
        ):
            _raw_key, api_key, _exhausted = await svc.create_api_key(
                actor_user_id=uuid4(),
                key_name="test",
                permissions=["nmt.inference"],
                application_id=1,
                allocated_percentage=Decimal("50"),
                caller_tenant_id=1,
            )

        assert api_key.allocated_budget == Decimal("5000")
        repo.create.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_skipped_entirely_when_application_has_no_budget_set(self) -> None:
        """A percentage-only key against an Application with no ₹ budget yet
        has no ceiling to overcommit — nothing to fetch usage for."""
        application = _application(allocated_budget=None)
        tenant = _tenant()
        applications = AsyncMock()
        applications.get_by_id_for_tenant = AsyncMock(return_value=application)
        applications.get_by_id_for_update = AsyncMock(return_value=application)
        applications.sum_api_key_allocated_percentage = AsyncMock(return_value=Decimal("0"))
        tenants = AsyncMock()
        tenants.get_operational_fields = AsyncMock(return_value=tenant)
        svc, repo, applications, tenants = _service(applications=applications, tenants=tenants)
        repo.get_permission_ids_by_names = AsyncMock(return_value={"nmt.inference": 1})
        repo.list_by_application = AsyncMock()

        await svc.create_api_key(
            actor_user_id=uuid4(),
            key_name="test",
            permissions=["nmt.inference"],
            application_id=1,
            allocated_percentage=Decimal("50"),
            caller_tenant_id=1,
        )

        repo.list_by_application.assert_not_awaited()


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
        tenants.get_operational_fields = AsyncMock(return_value=tenant)
        svc, repo, applications, tenants = _service(applications=applications, tenants=tenants)
        repo.get_permission_ids_by_names = AsyncMock(return_value={"nmt.inference": 1})

        _, api_key, _exhausted = await svc.create_api_key(
            actor_user_id=uuid4(),
            key_name="test",
            permissions=["nmt.inference"],
            application_id=1,
            allocated_percentage=Decimal("30"),
            caller_tenant_id=1,
        )

        # 1000.00 * 30% = 300.00, not 0.00 (the stale pre-revision figure).
        assert api_key.allocated_budget == Decimal("300.00")


class TestNewKeyExhaustionFlagSeeding:
    """A brand-new Key can still resolve to a ₹0 ceiling — not via its own
    percentage (TestExplicitZeroAllocationRejected covers that: an explicit
    0% is rejected outright), but via a positive percentage of an
    Application whose OWN allocated_budget is already 0. Without seeding
    "budget-exhausted" into the Key's very first cache write, the flag
    stays absent (falsy, i.e. NOT exhausted) until some future billed
    request happens to set it via the Kafka consumer — letting every
    request in between through against a ceiling that was already zero
    from the moment the Key was created."""

    @pytest.mark.asyncio
    async def test_key_resolved_to_a_zero_ceiling_is_flagged_exhausted_on_creation(self) -> None:
        application = _application(allocated_budget=Decimal("0"))
        tenant = _tenant()
        applications = AsyncMock()
        applications.get_by_id_for_tenant = AsyncMock(return_value=application)
        applications.get_by_id_for_update = AsyncMock(return_value=application)
        applications.sum_api_key_allocated_percentage = AsyncMock(return_value=Decimal("0"))
        tenants = AsyncMock()
        tenants.get_operational_fields = AsyncMock(return_value=tenant)
        svc, repo, applications, tenants = _service(applications=applications, tenants=tenants)
        repo.get_permission_ids_by_names = AsyncMock(return_value={"nmt.inference": 1})

        _raw_key, api_key, _exhausted = await svc.create_api_key(
            actor_user_id=uuid4(),
            key_name="test",
            permissions=["nmt.inference"],
            application_id=1,
            allocated_percentage=Decimal("50"),
            caller_tenant_id=1,
        )

        assert api_key.allocated_budget == Decimal("0")
        svc._cache.set_api_key_cache.assert_awaited_once()
        payload = svc._cache.set_api_key_cache.call_args.args[2]
        assert payload["budget-exhausted"] == "1"

    @pytest.mark.asyncio
    async def test_key_resolved_to_a_real_ceiling_is_not_flagged(self) -> None:
        application = _application(allocated_budget=Decimal("10000"))
        tenant = _tenant()
        applications = AsyncMock()
        applications.get_by_id_for_tenant = AsyncMock(return_value=application)
        applications.get_by_id_for_update = AsyncMock(return_value=application)
        applications.sum_api_key_allocated_percentage = AsyncMock(return_value=Decimal("0"))
        tenants = AsyncMock()
        tenants.get_operational_fields = AsyncMock(return_value=tenant)
        svc, repo, applications, tenants = _service(applications=applications, tenants=tenants)
        repo.get_permission_ids_by_names = AsyncMock(return_value={"nmt.inference": 1})

        await svc.create_api_key(
            actor_user_id=uuid4(),
            key_name="test",
            permissions=["nmt.inference"],
            application_id=1,
            allocated_percentage=Decimal("50"),
            caller_tenant_id=1,
        )

        payload = svc._cache.set_api_key_cache.call_args.args[2]
        assert "budget-exhausted" not in payload

    @pytest.mark.asyncio
    async def test_key_under_a_tenant_with_no_budget_configured_is_flagged_exhausted(
        self,
    ) -> None:
        """A Tenant that's never been given a Budget at all cascades None
        down through an Application (given only a percentage, no ₹ to
        resolve it against) to this new Key too — None here must mean
        "nothing to spend," not "unlimited," the same way 0 does. No
        budget_usage row is written for it (same as any None ceiling) —
        the flag alone blocks every request until the Tenant's own future
        top-up sync naturally clears it."""
        application = _application(allocated_budget=None)
        tenant = _tenant(allocated_budget=None)
        applications = AsyncMock()
        applications.get_by_id_for_tenant = AsyncMock(return_value=application)
        applications.get_by_id_for_update = AsyncMock(return_value=application)
        applications.sum_api_key_allocated_percentage = AsyncMock(return_value=Decimal("0"))
        tenants = AsyncMock()
        tenants.get_operational_fields = AsyncMock(return_value=tenant)
        svc, repo, applications, tenants = _service(applications=applications, tenants=tenants)
        repo.get_permission_ids_by_names = AsyncMock(return_value={"nmt.inference": 1})

        _raw_key, api_key, _exhausted = await svc.create_api_key(
            actor_user_id=uuid4(),
            key_name="test",
            permissions=["nmt.inference"],
            application_id=1,
            allocated_percentage=Decimal("50"),
            caller_tenant_id=1,
        )

        assert api_key.allocated_budget is None
        payload = svc._cache.set_api_key_cache.call_args.args[2]
        assert payload["budget-exhausted"] == "1"

    @pytest.mark.asyncio
    async def test_key_under_a_deliberately_uncapped_application_with_a_funded_tenant_is_not_flagged(
        self,
    ) -> None:
        """A DIFFERENT reason for a None ceiling: the Application itself was
        created with no percentage at all, under a Tenant that DOES have a
        real Budget. That's the established, intentional "uncapped
        Application" state — unrelated to this fix, and must keep behaving
        exactly as it already did (not flagged)."""
        application = _application(allocated_budget=None)
        tenant = _tenant(allocated_budget=Decimal("50000"))
        applications = AsyncMock()
        applications.get_by_id_for_tenant = AsyncMock(return_value=application)
        applications.get_by_id_for_update = AsyncMock(return_value=application)
        applications.sum_api_key_allocated_percentage = AsyncMock(return_value=Decimal("0"))
        tenants = AsyncMock()
        tenants.get_operational_fields = AsyncMock(return_value=tenant)
        svc, repo, applications, tenants = _service(applications=applications, tenants=tenants)
        repo.get_permission_ids_by_names = AsyncMock(return_value={"nmt.inference": 1})

        _raw_key, api_key, _exhausted = await svc.create_api_key(
            actor_user_id=uuid4(),
            key_name="test",
            permissions=["nmt.inference"],
            application_id=1,
            allocated_percentage=Decimal("50"),
            caller_tenant_id=1,
        )

        assert api_key.allocated_budget is None
        payload = svc._cache.set_api_key_cache.call_args.args[2]
        assert "budget-exhausted" not in payload


class TestUncappedKeySeededFromApplicationsRemainingBudget:
    """Code-review finding (mohapatras): an uncapped Key under an Application
    that DOES have its own ₹ Budget used to contribute 0 to committed_total
    as both a ceiling AND a usage figure (no budget_usage row for it — see
    create_api_key's own comment on this), so a LATER Key could be allocated
    the Application's entire remaining share while the uncapped one kept
    spending on top of the Budget, with only the Tenant's tier monthly quota
    to ever stop it. Fixed by seeding the uncapped Key with the Application's
    remaining (unallocated) ₹ instead of leaving it None."""

    @pytest.mark.asyncio
    async def test_uncapped_key_seeded_with_remaining_budget_when_room_exists(self) -> None:
        """50000 Application budget, one existing active Key already at 30%
        (15000). The new uncapped Key must be seeded with exactly what's
        left: 35000 (70%) — not the Application's full 50000, which would
        itself overcommit against the existing Key's own 30%."""
        application = _application(allocated_budget=Decimal("50000"))
        tenant = _tenant(allocated_budget=Decimal("100000"))
        existing_key = MagicMock(
            id=501, is_active=True, allocated_budget=Decimal("15000"),
            allocated_percentage=Decimal("30"),
        )
        applications = AsyncMock()
        applications.get_by_id_for_tenant = AsyncMock(return_value=application)
        applications.get_by_id_for_update = AsyncMock(return_value=application)
        applications.sum_api_key_allocated_percentage = AsyncMock(return_value=Decimal("30"))
        tenants = AsyncMock()
        tenants.get_operational_fields = AsyncMock(return_value=tenant)
        svc, repo, applications, tenants = _service(applications=applications, tenants=tenants)
        repo.get_permission_ids_by_names = AsyncMock(return_value={"nmt.inference": 1})
        repo.list_by_application = AsyncMock(return_value=[existing_key])

        with patch(
            "app.services.api_key_service.budget_usage.fetch_budget_usage",
            new=AsyncMock(return_value={501: (Decimal("15000"), Decimal("15000"))}),
        ), patch(
            "app.services.budget_usage.write_budget_snapshot", AsyncMock()
        ) as write_snap:
            _raw_key, api_key, exhausted = await svc.create_api_key(
                actor_user_id=uuid4(),
                key_name="test",
                permissions=["nmt.inference"],
                application_id=1,
                caller_tenant_id=1,
            )

        assert api_key.allocated_budget == Decimal("35000.00")
        assert api_key.allocated_percentage == Decimal("70.00")
        write_snap.assert_awaited_once_with({api_key.id: Decimal("35000.00")}, None)
        payload = svc._cache.set_api_key_cache.call_args.args[2]
        assert "budget-exhausted" not in payload
        assert exhausted is False

    @pytest.mark.asyncio
    async def test_uncapped_key_seeded_zero_when_application_already_fully_committed(self) -> None:
        """50000 Application budget, one existing active Key already at
        100% (50000) — nothing left. The uncapped-Key request must still
        SUCCEED (never rejected — it asks for "whatever's available," not a
        specific amount) but come out with a real, trackable ₹0 ceiling,
        flagged budget-exhausted immediately — not a silent, untracked
        None that would recreate the exact bug this fix closes."""
        application = _application(allocated_budget=Decimal("50000"))
        tenant = _tenant(allocated_budget=Decimal("100000"))
        existing_key = MagicMock(
            id=502, is_active=True, allocated_budget=Decimal("50000"),
            allocated_percentage=Decimal("100"),
        )
        applications = AsyncMock()
        applications.get_by_id_for_tenant = AsyncMock(return_value=application)
        applications.get_by_id_for_update = AsyncMock(return_value=application)
        applications.sum_api_key_allocated_percentage = AsyncMock(return_value=Decimal("100"))
        tenants = AsyncMock()
        tenants.get_operational_fields = AsyncMock(return_value=tenant)
        svc, repo, applications, tenants = _service(applications=applications, tenants=tenants)
        repo.get_permission_ids_by_names = AsyncMock(return_value={"nmt.inference": 1})
        repo.list_by_application = AsyncMock(return_value=[existing_key])

        with patch(
            "app.services.api_key_service.budget_usage.fetch_budget_usage",
            new=AsyncMock(return_value={502: (Decimal("50000"), Decimal("50000"))}),
        ), patch(
            "app.services.budget_usage.write_budget_snapshot", AsyncMock()
        ) as write_snap:
            _raw_key, api_key, exhausted = await svc.create_api_key(
                actor_user_id=uuid4(),
                key_name="test",
                permissions=["nmt.inference"],
                application_id=1,
                caller_tenant_id=1,
            )

        assert api_key.allocated_budget == Decimal("0")
        assert api_key.allocated_percentage == Decimal("0")
        write_snap.assert_awaited_once_with({api_key.id: Decimal("0")}, None)
        payload = svc._cache.set_api_key_cache.call_args.args[2]
        assert payload["budget-exhausted"] == "1"
        # Code-review finding (mohapatras): the internal cache flag alone
        # isn't visible to the caller of POST /auth/api-keys — the same
        # 0/0 state an explicit allocated_percentage=0 is rejected for must
        # not come back from create_api_key looking like a healthy key.
        assert exhausted is True

    @pytest.mark.asyncio
    async def test_exact_bug_scenario_uncapped_key_blocks_a_later_key_from_overcommitting(
        self,
    ) -> None:
        """The exact scenario mohapatras described: create an uncapped Key
        first (it takes the Application's entire remaining 50000/100%,
        since nothing else exists yet), THEN try to create a second Key
        requesting even a small extra share — it must be rejected, proving
        the first (originally 'uncapped') Key's footprint is no longer
        invisible to the second Key's own ALLOCATION_TOTAL_EXCEEDED check."""
        application = _application(allocated_budget=Decimal("50000"))
        tenant = _tenant(allocated_budget=Decimal("100000"))
        applications = AsyncMock()
        applications.get_by_id_for_tenant = AsyncMock(return_value=application)
        applications.get_by_id_for_update = AsyncMock(return_value=application)
        applications.sum_api_key_allocated_percentage = AsyncMock(return_value=Decimal("0"))
        tenants = AsyncMock()
        tenants.get_operational_fields = AsyncMock(return_value=tenant)
        svc, repo, applications, tenants = _service(applications=applications, tenants=tenants)
        repo.get_permission_ids_by_names = AsyncMock(return_value={"nmt.inference": 1})
        repo.list_by_application = AsyncMock(return_value=[])

        with patch(
            "app.services.api_key_service.budget_usage.fetch_budget_usage",
            new=AsyncMock(return_value={}),
        ), patch(
            "app.services.budget_usage.write_budget_snapshot", AsyncMock()
        ):
            _raw_key, uncapped_key, _exhausted = await svc.create_api_key(
                actor_user_id=uuid4(),
                key_name="uncapped-first",
                permissions=["nmt.inference"],
                application_id=1,
                caller_tenant_id=1,
            )

        assert uncapped_key.allocated_percentage == Decimal("100.00")

        # Second Key request: the first Key's own 100% is now visible to
        # sum_api_key_allocated_percentage, exactly as any other Key's
        # would be — this must reject, not silently succeed on top of it.
        applications.sum_api_key_allocated_percentage = AsyncMock(return_value=Decimal("100.00"))

        with pytest.raises(ValidationError) as exc:
            await svc.create_api_key(
                actor_user_id=uuid4(),
                key_name="second-key",
                permissions=["nmt.inference"],
                application_id=1,
                allocated_percentage=Decimal("10"),
                caller_tenant_id=1,
            )

        assert exc.value.code == "ALLOCATION_TOTAL_EXCEEDED"
        repo.create.assert_awaited_once()  # only the first Key was ever persisted


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
        tenants.get_operational_fields = AsyncMock(return_value=tenant)
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
        tenants.get_operational_fields = AsyncMock(return_value=tenant)
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
        tenants.get_operational_fields = AsyncMock(return_value=tenant)
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
        tenants.get_operational_fields = AsyncMock(return_value=tenant)
        svc, repo, applications, tenants = _service(applications=applications, tenants=tenants)
        repo.get_permission_ids_by_names = AsyncMock(return_value={"nmt.inference": 1})

        with patch(
            "app.services.budget_usage.write_budget_snapshot", AsyncMock()
        ) as write_snap:
            _, api_key, _exhausted = await svc.create_api_key(
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
        tenants.get_operational_fields = AsyncMock(return_value=tenant)
        svc, repo, applications, tenants = _service(applications=applications, tenants=tenants)
        repo.get_permission_ids_by_names = AsyncMock(return_value={"nmt.inference": 1})

        with patch(
            "app.services.budget_usage.write_budget_snapshot", AsyncMock()
        ) as write_snap:
            _, api_key, _exhausted = await svc.create_api_key(
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
        tenants.get_operational_fields = AsyncMock(return_value=tenant)
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

    # test_neither_percentage_nor_budget_given_is_rejected removed: omitting
    # both is now allowed (ALLOCATION_REQUIRED removed) — see
    # TestAllocationCapLockOrdering.
    # test_neither_allocation_given_creates_uncapped_key_when_tenant_has_budget
    # and .test_neither_allocation_given_is_exhausted_when_tenant_has_no_budget
    # for the current behavior.


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
        tenants.get_operational_fields = AsyncMock(return_value=tenant)
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
        tenants.get_operational_fields = AsyncMock(return_value=tenant)
        svc, repo, applications, tenants = _service(applications=applications, tenants=tenants)
        repo.get_permission_ids_by_names = AsyncMock(return_value={"nmt.inference": 12})

        _raw_key, api_key, _exhausted = await svc.create_api_key(
            actor_user_id=uuid4(),
            key_name="test",
            permissions=["nmt.inference"],
            application_id=1,
            allocated_percentage=Decimal("10"),
            caller_tenant_id=1,
        )

        assert api_key.permissions == [12]
        repo.create.assert_awaited_once()
