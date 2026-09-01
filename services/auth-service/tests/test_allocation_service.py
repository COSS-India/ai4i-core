"""AllocationService — the orchestrator behind the three Budget Allocation
endpoints (PUT /auth/tenants/{id}/budget-allocation,
PUT /auth/applications/{id}/budget-allocation,
PUT /auth/api-keys/{id}/budget-allocation).

allocation_validator's own math is covered exhaustively in
test_allocation_validator.py; these tests focus on orchestration: scope
authorization, request-shape rejections (KEY_APPLICATION_MISMATCH,
KEY_ID_MISMATCH, APPLICATION_ID_MISMATCH, APPLICATION_ALLOCATION_MISMATCH),
which repository gets locked, persistence of resolved rows, the two
different "what happens to an unlisted child" rules at the two edges, the
Application -> its own Keys cascade, the {type, value} wire mapping
(including which rows report back FIXED vs PERCENTAGE), and the
budget_usage write-through.
"""

from decimal import Decimal
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.core.exceptions import EntityNotFoundError, ValidationError
from app.models.api_key import APIKey
from app.models.application import Application
from app.models.tenant import Tenant
from app.models.user import User
from app.schemas.allocation import (
    AllocationValue,
    APIKeyAllocationRow,
    APIKeyBudgetAllocationRequest,
    ApplicationAllocationRow,
    ApplicationBudgetAllocationRequest,
    TenantBudgetAllocationRequest,
)
from app.services.allocation_service import AllocationService


def _user(*, tenant_id=None) -> User:
    return User(id=uuid4(), email="test-admin@example.invalid", username=uuid4().hex[:12], tenant_id=tenant_id)


def _tenant(allocated_budget=Decimal("100000")) -> Tenant:
    return Tenant(id=101, name="Acme", organisation="Acme", email="test@example.invalid", allocated_budget=allocated_budget)


def _application(id_, *, allocated_budget, allocated_percentage, tenant_id=101) -> Application:
    return Application(
        id=id_, tenant_id=tenant_id, name=f"App{id_}",
        allocated_budget=allocated_budget, allocated_percentage=allocated_percentage,
    )


def _key(id_, application_id, *, allocated_budget, allocated_percentage, is_active=True) -> APIKey:
    # is_active defaults to True to match the column's own real default
    # (Column(default=True) only applies at INSERT time, not on a plain
    # Python-constructed object like this one) — pass is_active=False to
    # build a revoked Key for a test.
    return APIKey(
        id=id_, application_id=application_id, key_name=f"Key{id_}", api_key=uuid4().hex,
        allocated_budget=allocated_budget, allocated_percentage=allocated_percentage,
        is_active=is_active,
    )


def _svc(*, roles=("ADMIN",)) -> AllocationService:
    svc = AllocationService(
        application_repo=AsyncMock(),
        api_key_repo=AsyncMock(),
        tenant_repo=AsyncMock(),
        role_repo=AsyncMock(),
        db=AsyncMock(),
    )
    svc._roles.get_user_roles = AsyncMock(return_value=list(roles))
    return svc


def _pct(value) -> AllocationValue:
    return AllocationValue(type="PERCENTAGE", value=Decimal(value))


def _fixed(value) -> AllocationValue:
    return AllocationValue(type="FIXED", value=Decimal(value))


# The acceptance-criteria worked example, reused across several tests:
# App A=50%/50000 (40000 used), App B=30%/30000 (30000 used, exhausted),
# App C=20%/20000 (5000 used).
def _three_apps():
    return [
        _application(1, allocated_budget=Decimal("50000"), allocated_percentage=Decimal("50")),
        _application(2, allocated_budget=Decimal("30000"), allocated_percentage=Decimal("30")),
        _application(3, allocated_budget=Decimal("20000"), allocated_percentage=Decimal("20")),
    ]


class TestTenantScopeAuthAndShape:
    @pytest.mark.asyncio
    async def test_no_qualifying_role_rejected(self) -> None:
        svc = _svc(roles=["MODERATOR"])
        body = TenantBudgetAllocationRequest(
            applications=[ApplicationAllocationRow(application_id=1, allocation=_pct("45"))]
        )
        with pytest.raises(HTTPException) as exc:
            await svc.update_tenant_application_allocations(101, body, _user(), None)
        assert exc.value.status_code == 403

    @pytest.mark.asyncio
    async def test_tenant_admin_of_different_tenant_masked_404(self) -> None:
        svc = _svc(roles=["TENANT ADMIN"])
        body = TenantBudgetAllocationRequest(
            applications=[ApplicationAllocationRow(application_id=1, allocation=_pct("45"))]
        )
        with pytest.raises(HTTPException) as exc:
            await svc.update_tenant_application_allocations(101, body, _user(tenant_id=999), None)
        assert exc.value.status_code == 404

    def test_empty_applications_list_rejected_by_schema(self) -> None:
        with pytest.raises(ValueError):
            TenantBudgetAllocationRequest(applications=[])

    @pytest.mark.asyncio
    async def test_tenant_not_found(self) -> None:
        svc = _svc()
        svc._tenants.get_by_id_for_update = AsyncMock(return_value=None)
        body = TenantBudgetAllocationRequest(
            applications=[ApplicationAllocationRow(application_id=1, allocation=_pct("45"))]
        )
        with pytest.raises(EntityNotFoundError):
            await svc.update_tenant_application_allocations(101, body, _user(), None)

    @pytest.mark.asyncio
    async def test_tenant_with_no_budget_set_rejected(self) -> None:
        svc = _svc()
        svc._tenants.get_by_id_for_update = AsyncMock(return_value=_tenant(allocated_budget=None))
        body = TenantBudgetAllocationRequest(
            applications=[ApplicationAllocationRow(application_id=1, allocation=_pct("45"))]
        )
        with pytest.raises(ValidationError) as exc:
            await svc.update_tenant_application_allocations(101, body, _user(), None)
        assert exc.value.code == "TENANT_BUDGET_NOT_SET"


class TestTenantScopeResolution:
    @pytest.mark.asyncio
    async def test_reduce_app_a_unmentioned_siblings_proportionally_refit(self) -> None:
        """Unlike the Application->Keys edge, an unmentioned Application IS
        touched: App B and C's ₹ move to keep tracking the (unchanged)
        Tenant total, and both are returned in the response. 45000 (A) +
        33000 (B, refit) + 22000 (C, refit) = 100000."""
        svc = _svc()
        svc._tenants.get_by_id_for_update = AsyncMock(return_value=_tenant())
        apps = _three_apps()
        svc._applications.list_by_tenant = AsyncMock(return_value=apps)
        svc._applications.update = AsyncMock()
        svc._api_keys.list_by_applications = AsyncMock(return_value=[])

        body = TenantBudgetAllocationRequest(
            applications=[ApplicationAllocationRow(application_id=1, allocation=_pct("45"))]
        )
        with patch("app.services.budget_usage.fetch_budget_usage", AsyncMock(return_value={})), \
             patch("app.services.budget_usage.write_budget_snapshot", AsyncMock()) as write_snap:
            data = await svc.update_tenant_application_allocations(101, body, _user(), None)

        by_id = {row.application_id: row for row in data}
        assert set(by_id) == {1, 2, 3}
        assert by_id[1].allocated_budget == Decimal("45000.00")
        assert by_id[2].allocated_budget == Decimal("33000.00")
        assert by_id[3].allocated_budget == Decimal("22000.00")
        assert svc._applications.update.await_count == 3
        write_snap.assert_awaited_once()
        svc._db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_every_application_is_locked_not_just_listed(self) -> None:
        """refit_unlisted=True means any Application may end up written, so
        every one under the Tenant is locked up front, not just the row(s)
        explicitly listed."""
        svc = _svc()
        svc._tenants.get_by_id_for_update = AsyncMock(return_value=_tenant())
        apps = _three_apps()
        svc._applications.list_by_tenant = AsyncMock(return_value=apps)
        svc._applications.update = AsyncMock()
        svc._api_keys.list_by_applications = AsyncMock(return_value=[])

        body = TenantBudgetAllocationRequest(
            applications=[ApplicationAllocationRow(application_id=1, allocation=_pct("45"))]
        )
        with patch("app.services.budget_usage.fetch_budget_usage", AsyncMock(return_value={})), \
             patch("app.services.budget_usage.write_budget_snapshot", AsyncMock()):
            await svc.update_tenant_application_allocations(101, body, _user(), None)

        locked_ids = {call.args[0] for call in svc._applications.get_by_id_for_update.await_args_list}
        assert locked_ids == {1, 2, 3}

    @pytest.mark.asyncio
    async def test_reduce_fully_exhausted_app_b_blocked(self) -> None:
        svc = _svc()
        svc._tenants.get_by_id_for_update = AsyncMock(return_value=_tenant())
        apps = _three_apps()
        keys = [_key(21, 2, allocated_budget=Decimal("30000"), allocated_percentage=Decimal("100"))]
        svc._applications.list_by_tenant = AsyncMock(return_value=apps)
        svc._api_keys.list_by_applications = AsyncMock(return_value=keys)

        body = TenantBudgetAllocationRequest(
            applications=[ApplicationAllocationRow(application_id=2, allocation=_pct("25"))]
        )
        with patch(
            "app.services.budget_usage.fetch_budget_usage",
            AsyncMock(return_value={21: (Decimal("30000"), None)}),
        ):
            with pytest.raises(ValidationError) as exc:
                await svc.update_tenant_application_allocations(101, body, _user(), None)
        assert exc.value.code == "ALLOCATION_BELOW_CONSUMED"

    @pytest.mark.asyncio
    async def test_revoked_keys_spend_still_counts_toward_the_applications_own_floor(
        self,
    ) -> None:
        """Same scenario as test_reduce_fully_exhausted_app_b_blocked, but
        Key 21 is now revoked. Revocation doesn't undo the ₹ it already
        spent — App B's own consumed total must still include it, so
        shrinking App B below that is still rejected. (The Key itself would
        separately be excluded from any Keys-level cascade of App B's own
        Keys — a different concern from this Application-level floor.)"""
        svc = _svc()
        svc._tenants.get_by_id_for_update = AsyncMock(return_value=_tenant())
        apps = _three_apps()
        keys = [
            _key(
                21, 2, allocated_budget=Decimal("30000"), allocated_percentage=Decimal("100"),
                is_active=False,
            )
        ]
        svc._applications.list_by_tenant = AsyncMock(return_value=apps)
        svc._api_keys.list_by_applications = AsyncMock(return_value=keys)

        body = TenantBudgetAllocationRequest(
            applications=[ApplicationAllocationRow(application_id=2, allocation=_pct("25"))]
        )
        with patch(
            "app.services.budget_usage.fetch_budget_usage",
            AsyncMock(return_value={21: (Decimal("30000"), None)}),
        ):
            with pytest.raises(ValidationError) as exc:
                await svc.update_tenant_application_allocations(101, body, _user(), None)
        assert exc.value.code == "ALLOCATION_BELOW_CONSUMED"

    @pytest.mark.asyncio
    async def test_unmentioned_sibling_can_fail_floor_check_on_refit(self) -> None:
        """New failure mode versus the old contract: an Application nobody
        mentioned can still be rejected if re-fitting it down would drop it
        below its own spend. App C has 20000 used against its current
        20000 ceiling (fully exhausted); growing App A's share squeezes C's
        re-fit share below that."""
        svc = _svc()
        svc._tenants.get_by_id_for_update = AsyncMock(return_value=_tenant())
        apps = _three_apps()
        keys = [_key(31, 3, allocated_budget=Decimal("20000"), allocated_percentage=Decimal("100"))]
        svc._applications.list_by_tenant = AsyncMock(return_value=apps)
        svc._api_keys.list_by_applications = AsyncMock(return_value=keys)

        # App A grows to 79%, leaving only 21000 for B+C combined (old room
        # for B+C was 50000) — C's proportional share of that shrinks below
        # its 20000 already spent.
        body = TenantBudgetAllocationRequest(
            applications=[ApplicationAllocationRow(application_id=1, allocation=_pct("79"))]
        )
        with patch(
            "app.services.budget_usage.fetch_budget_usage",
            AsyncMock(return_value={31: (Decimal("20000"), None)}),
        ):
            with pytest.raises(ValidationError) as exc:
                await svc.update_tenant_application_allocations(101, body, _user(), None)
        assert exc.value.code == "ALLOCATION_BELOW_CONSUMED"

    @pytest.mark.asyncio
    async def test_resized_application_cascades_into_its_own_unlisted_keys(self) -> None:
        """App A resized 50000 -> 40000; two Keys (30000/20000, unlisted) must
        proportionally re-fit to sum <= 40000, and get persisted + snapshotted."""
        svc = _svc()
        svc._tenants.get_by_id_for_update = AsyncMock(return_value=_tenant())
        apps = _three_apps()
        key1 = _key(11, 1, allocated_budget=Decimal("30000"), allocated_percentage=Decimal("60"))
        key2 = _key(12, 1, allocated_budget=Decimal("20000"), allocated_percentage=Decimal("40"))
        svc._applications.list_by_tenant = AsyncMock(return_value=apps)
        svc._applications.update = AsyncMock()
        svc._api_keys.list_by_applications = AsyncMock(return_value=[key1, key2])
        svc._api_keys.update = AsyncMock()

        body = TenantBudgetAllocationRequest(
            applications=[ApplicationAllocationRow(application_id=1, allocation=_fixed("40000"))]
        )
        with patch("app.services.budget_usage.fetch_budget_usage", AsyncMock(return_value={})), \
             patch("app.services.budget_usage.write_budget_snapshot", AsyncMock()) as write_snap:
            data = await svc.update_tenant_application_allocations(101, body, _user(), None)

        app_row = next(row for row in data if row.application_id == 1)
        assert app_row.allocated_budget == Decimal("40000.00")
        assert app_row.allocation == AllocationValue(type="FIXED", value=Decimal("40000.00"))
        key_rows = {r.api_key_id: r for r in app_row.api_keys}
        assert key_rows[11].allocated_budget == Decimal("24000.00")
        assert key_rows[12].allocated_budget == Decimal("16000.00")
        # Auto-refitted Keys always report back PERCENTAGE — type is never
        # persisted/inferred for a row the caller didn't submit this call.
        assert key_rows[11].allocation.type == "PERCENTAGE"
        assert svc._api_keys.update.await_count == 2
        write_snap.assert_awaited_once()
        snapshot_arg = write_snap.await_args.args[0]
        assert snapshot_arg == {11: Decimal("24000.00"), 12: Decimal("16000.00")}

    @pytest.mark.asyncio
    async def test_key_application_mismatch(self) -> None:
        svc = _svc()
        svc._tenants.get_by_id_for_update = AsyncMock(return_value=_tenant())
        apps = _three_apps()
        key_under_app2 = _key(99, 2, allocated_budget=Decimal("30000"), allocated_percentage=Decimal("100"))
        svc._applications.list_by_tenant = AsyncMock(return_value=apps)
        svc._api_keys.list_by_applications = AsyncMock(return_value=[key_under_app2])
        svc._api_keys.get_by_id = AsyncMock(return_value=key_under_app2)

        body = TenantBudgetAllocationRequest(
            applications=[
                ApplicationAllocationRow(
                    application_id=1,
                    allocation=_fixed("40000"),
                    api_keys=[APIKeyAllocationRow(api_key_id=99, allocation=_fixed("1000"))],
                )
            ]
        )
        with patch("app.services.budget_usage.fetch_budget_usage", AsyncMock(return_value={})):
            with pytest.raises(ValidationError) as exc:
                await svc.update_tenant_application_allocations(101, body, _user(), None)
        assert exc.value.code == "KEY_APPLICATION_MISMATCH"


class TestApplicationScope:
    @pytest.mark.asyncio
    async def test_application_id_mismatch(self) -> None:
        svc = _svc()
        body = ApplicationBudgetAllocationRequest(application_id=2, allocation=_pct("50"))
        with pytest.raises(ValidationError) as exc:
            await svc.update_application_key_allocations(1, body, _user(), None)
        assert exc.value.code == "APPLICATION_ID_MISMATCH"

    @pytest.mark.asyncio
    async def test_application_not_found(self) -> None:
        svc = _svc()
        svc._applications.get_by_id = AsyncMock(return_value=None)
        body = ApplicationBudgetAllocationRequest(application_id=1, allocation=_pct("50"))
        with pytest.raises(EntityNotFoundError):
            await svc.update_application_key_allocations(1, body, _user(), None)

    @pytest.mark.asyncio
    async def test_application_deleted_between_unlocked_lookup_and_lock_is_not_found(self) -> None:
        """get_by_id (unlocked) finds it; get_by_id_for_update (the actual
        lock attempt) returns None because the row is gone by then — must
        not silently fall back to the earlier, now-stale unlocked object."""
        svc = _svc()
        app = _application(1, allocated_budget=Decimal("50000"), allocated_percentage=Decimal("50"))
        svc._applications.get_by_id = AsyncMock(return_value=app)
        svc._applications.get_by_id_for_update = AsyncMock(return_value=None)
        body = ApplicationBudgetAllocationRequest(application_id=1, allocation=_pct("50"))
        with pytest.raises(EntityNotFoundError):
            await svc.update_application_key_allocations(1, body, _user(), None)

    @pytest.mark.asyncio
    async def test_application_with_no_budget_set_rejected(self) -> None:
        svc = _svc()
        app = _application(1, allocated_budget=None, allocated_percentage=None)
        svc._applications.get_by_id = AsyncMock(return_value=app)
        svc._applications.get_by_id_for_update = AsyncMock(return_value=app)
        body = ApplicationBudgetAllocationRequest(application_id=1, allocation=_pct("50"))
        with pytest.raises(ValidationError) as exc:
            await svc.update_application_key_allocations(1, body, _user(), None)
        assert exc.value.code == "APPLICATION_BUDGET_NOT_SET"

    @pytest.mark.asyncio
    async def test_application_allocation_must_match_current_value(self) -> None:
        """This endpoint is echo-only for the Application's own allocation —
        it never changes an Application's share of the Tenant. Submitting a
        different percentage than what's stored is rejected outright."""
        svc = _svc()
        app = _application(1, allocated_budget=Decimal("50000"), allocated_percentage=Decimal("50"))
        svc._applications.get_by_id = AsyncMock(return_value=app)
        svc._applications.get_by_id_for_update = AsyncMock(return_value=app)
        body = ApplicationBudgetAllocationRequest(application_id=1, allocation=_pct("40"))
        with pytest.raises(ValidationError) as exc:
            await svc.update_application_key_allocations(1, body, _user(), None)
        assert exc.value.code == "APPLICATION_ALLOCATION_MISMATCH"

    @pytest.mark.asyncio
    async def test_application_allocation_matching_current_fixed_value_is_accepted(self) -> None:
        svc = _svc()
        app = _application(1, allocated_budget=Decimal("50000"), allocated_percentage=Decimal("50"))
        svc._applications.get_by_id = AsyncMock(return_value=app)
        svc._applications.get_by_id_for_update = AsyncMock(return_value=app)
        svc._api_keys.list_by_application = AsyncMock(return_value=[])
        body = ApplicationBudgetAllocationRequest(application_id=1, allocation=_fixed("50000"))
        with patch("app.services.budget_usage.fetch_budget_usage", AsyncMock(return_value={})), \
             patch("app.services.budget_usage.write_budget_snapshot", AsyncMock()):
            data = await svc.update_application_key_allocations(1, body, _user(), None)
        assert data.allocation == AllocationValue(type="FIXED", value=Decimal("50000"))

    @pytest.mark.asyncio
    async def test_direct_key_reduction_proportionally_refits_unlisted_sibling(self) -> None:
        """Key 12 isn't listed, but the Application's own total isn't
        changing either — refit_unlisted=True at this edge means the room
        Key 11 gives up is proportionally absorbed by Key 12, not left
        sitting there untouched. 50000 total, fully allocated (30000 +
        20000); Key 11 drops to 25000 (freeing 5000), so Key 12 — the only
        unlisted sibling — grows to fill exactly that freed room: 20000 *
        (25000 / 20000) = 25000."""
        svc = _svc()
        app = _application(1, allocated_budget=Decimal("50000"), allocated_percentage=Decimal("50"))
        key1 = _key(11, 1, allocated_budget=Decimal("30000"), allocated_percentage=Decimal("60"))
        key2 = _key(12, 1, allocated_budget=Decimal("20000"), allocated_percentage=Decimal("40"))
        svc._applications.get_by_id = AsyncMock(return_value=app)
        svc._applications.get_by_id_for_update = AsyncMock(return_value=app)
        svc._api_keys.list_by_application = AsyncMock(return_value=[key1, key2])
        svc._api_keys.update = AsyncMock()

        body = ApplicationBudgetAllocationRequest(
            application_id=1,
            allocation=_pct("50"),
            api_keys=[APIKeyAllocationRow(api_key_id=11, allocation=_fixed("25000"))],
        )
        with patch("app.services.budget_usage.fetch_budget_usage", AsyncMock(return_value={})), \
             patch("app.services.budget_usage.write_budget_snapshot", AsyncMock()):
            data = await svc.update_application_key_allocations(1, body, _user(), None)

        assert data.application_id == 1
        by_id = {row.api_key_id: row for row in data.api_keys}
        assert set(by_id) == {11, 12}
        assert by_id[11].allocated_budget == Decimal("25000.00")
        assert by_id[11].allocation == AllocationValue(type="FIXED", value=Decimal("25000.00"))
        # Unlisted sibling — proportionally re-fit to absorb the freed room,
        # always reported as PERCENTAGE (never FIXED — that's only for a
        # row just submitted as FIXED in this exact request).
        assert by_id[12].allocated_budget == Decimal("25000.00")
        assert by_id[12].allocation == AllocationValue(type="PERCENTAGE", value=Decimal("50"))
        assert svc._api_keys.update.await_count == 2

    @pytest.mark.asyncio
    async def test_revoked_sibling_is_excluded_not_refit_and_freed_room_stays_unallocated(
        self,
    ) -> None:
        """A revoked Key is terminal — it's excluded from the response and
        from the re-fit pool entirely, not merely left unlisted. Reducing
        Key 11 here frees room that would normally flow to an unlisted
        active sibling, but Key 12 is revoked, so there's no eligible
        sibling to absorb it — the freed room stays genuinely unallocated,
        and Key 12's own stale allocated_budget never changes."""
        svc = _svc()
        app = _application(1, allocated_budget=Decimal("50000"), allocated_percentage=Decimal("50"))
        key1 = _key(11, 1, allocated_budget=Decimal("30000"), allocated_percentage=Decimal("60"))
        key2 = _key(
            12, 1, allocated_budget=Decimal("20000"), allocated_percentage=Decimal("40"),
            is_active=False,
        )
        svc._applications.get_by_id = AsyncMock(return_value=app)
        svc._applications.get_by_id_for_update = AsyncMock(return_value=app)
        svc._api_keys.list_by_application = AsyncMock(return_value=[key1, key2])
        svc._api_keys.update = AsyncMock()

        body = ApplicationBudgetAllocationRequest(
            application_id=1,
            allocation=_pct("50"),
            api_keys=[APIKeyAllocationRow(api_key_id=11, allocation=_fixed("25000"))],
        )
        with patch("app.services.budget_usage.fetch_budget_usage", AsyncMock(return_value={})), \
             patch("app.services.budget_usage.write_budget_snapshot", AsyncMock()):
            data = await svc.update_application_key_allocations(1, body, _user(), None)

        by_id = {row.api_key_id: row for row in data.api_keys}
        assert set(by_id) == {11}  # revoked Key 12 excluded entirely, not merged back in
        assert by_id[11].allocated_budget == Decimal("25000.00")
        svc._api_keys.update.assert_awaited_once()  # only Key 11 ever written

    @pytest.mark.asyncio
    async def test_explicit_edit_targeting_a_revoked_key_rejected(self) -> None:
        svc = _svc()
        app = _application(1, allocated_budget=Decimal("50000"), allocated_percentage=Decimal("50"))
        key1 = _key(11, 1, allocated_budget=Decimal("30000"), allocated_percentage=Decimal("60"))
        key2 = _key(
            12, 1, allocated_budget=Decimal("20000"), allocated_percentage=Decimal("40"),
            is_active=False,
        )
        svc._applications.get_by_id = AsyncMock(return_value=app)
        svc._applications.get_by_id_for_update = AsyncMock(return_value=app)
        svc._api_keys.list_by_application = AsyncMock(return_value=[key1, key2])
        svc._api_keys.get_by_id = AsyncMock(return_value=key2)

        body = ApplicationBudgetAllocationRequest(
            application_id=1,
            allocation=_pct("50"),
            api_keys=[APIKeyAllocationRow(api_key_id=12, allocation=_fixed("15000"))],
        )
        with pytest.raises(ValidationError) as exc:
            await svc.update_application_key_allocations(1, body, _user(), None)
        assert exc.value.code == "API_KEY_REVOKED"


class TestSingleApiKeyScope:
    @pytest.mark.asyncio
    async def test_key_id_mismatch(self) -> None:
        svc = _svc()
        body = APIKeyBudgetAllocationRequest(api_key_id=99, allocation=_pct("50"))
        with pytest.raises(ValidationError) as exc:
            await svc.update_single_api_key_allocation(11, body, _user(), None)
        assert exc.value.code == "KEY_ID_MISMATCH"

    @pytest.mark.asyncio
    async def test_unknown_key_not_found(self) -> None:
        svc = _svc()
        svc._api_keys.get_by_id = AsyncMock(return_value=None)
        body = APIKeyBudgetAllocationRequest(api_key_id=11, allocation=_pct("50"))
        with pytest.raises(EntityNotFoundError):
            await svc.update_single_api_key_allocation(11, body, _user(), None)

    @pytest.mark.asyncio
    async def test_resolves_via_the_keys_own_application_and_returns_full_parent(self) -> None:
        """No application_id is given by the caller at all — it's derived
        from the Key itself. Response is the complete parent Application,
        siblings included, same shape as the Application-level endpoint.
        Growing Key 1 from 60% to 70% draws partly from the 10% (5000)
        unallocated headroom and partly from Key 2, the only sibling —
        refit_unlisted=True proportionally re-fits it, it isn't left as-is:
        15000 * (15000 / 20000) = 11250."""
        svc = _svc()
        app = _application(1, allocated_budget=Decimal("50000"), allocated_percentage=Decimal("50"))
        key1 = _key(11, 1, allocated_budget=Decimal("30000"), allocated_percentage=Decimal("60"))
        key2 = _key(12, 1, allocated_budget=Decimal("15000"), allocated_percentage=Decimal("30"))
        svc._api_keys.get_by_id = AsyncMock(return_value=key1)
        svc._applications.get_by_id = AsyncMock(return_value=app)
        svc._applications.get_by_id_for_update = AsyncMock(return_value=app)
        svc._api_keys.list_by_application = AsyncMock(return_value=[key1, key2])
        svc._api_keys.update = AsyncMock()

        body = APIKeyBudgetAllocationRequest(api_key_id=11, allocation=_pct("70"))
        with patch("app.services.budget_usage.fetch_budget_usage", AsyncMock(return_value={})), \
             patch("app.services.budget_usage.write_budget_snapshot", AsyncMock()):
            data = await svc.update_single_api_key_allocation(11, body, _user(), None)

        assert data.application_id == 1
        assert data.allocation == AllocationValue(type="PERCENTAGE", value=Decimal("50"))
        assert data.allocated_budget == Decimal("50000")
        by_id = {row.api_key_id: row for row in data.api_keys}
        assert by_id[11].allocated_budget == Decimal("35000.00")
        assert by_id[12].allocated_budget == Decimal("11250.00")  # proportionally re-fit, not untouched
        assert svc._api_keys.update.await_count == 2

    @pytest.mark.asyncio
    async def test_application_not_found_for_key(self) -> None:
        svc = _svc()
        key1 = _key(11, 1, allocated_budget=Decimal("30000"), allocated_percentage=Decimal("60"))
        svc._api_keys.get_by_id = AsyncMock(return_value=key1)
        svc._applications.get_by_id = AsyncMock(return_value=None)
        body = APIKeyBudgetAllocationRequest(api_key_id=11, allocation=_pct("70"))
        with pytest.raises(EntityNotFoundError):
            await svc.update_single_api_key_allocation(11, body, _user(), None)

    @pytest.mark.asyncio
    async def test_revoked_key_itself_rejected(self) -> None:
        """A revoked Key is terminal, no reissue — its own Budget allocation
        can't be edited at all via this endpoint, regardless of siblings."""
        svc = _svc()
        key1 = _key(
            11, 1, allocated_budget=Decimal("30000"), allocated_percentage=Decimal("60"),
            is_active=False,
        )
        svc._api_keys.get_by_id = AsyncMock(return_value=key1)
        body = APIKeyBudgetAllocationRequest(api_key_id=11, allocation=_pct("70"))
        with pytest.raises(ValidationError) as exc:
            await svc.update_single_api_key_allocation(11, body, _user(), None)
        assert exc.value.code == "API_KEY_REVOKED"
