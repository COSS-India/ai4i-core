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
    async def test_reduce_app_a_unmentioned_siblings_never_move(self) -> None:
        """refit_unlisted=False at this edge: reducing App A never moves
        App B or C — they're merged back in from their current DB values,
        untouched, api_keys=None (not resolved this call). The freed room
        (50000 -> 45000 = 5000) becomes genuinely unallocated: 45000 (A) +
        30000 (B, untouched) + 20000 (C, untouched) = 95000, 5000 free."""
        svc = _svc()
        svc._tenants.get_by_id_for_update = AsyncMock(return_value=_tenant())
        apps = _three_apps()
        svc._applications.list_by_tenant_for_update = AsyncMock(return_value=apps)
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
        assert by_id[2].allocated_budget == Decimal("30000")  # untouched, merged back
        assert by_id[3].allocated_budget == Decimal("20000")  # untouched, merged back
        assert svc._applications.update.await_count == 1  # only App A written
        write_snap.assert_awaited_once()
        svc._db.commit.assert_awaited_once()
        # App A was resolved this call (empty api_keys — none in this
        # fixture); B/C were never touched — api_keys=None distinguishes
        # "not resolved" from "resolved, genuinely has none."
        assert by_id[1].api_keys == []
        assert by_id[2].api_keys is None
        assert by_id[3].api_keys is None

    @pytest.mark.asyncio
    async def test_growing_beyond_available_headroom_is_blocked_siblings_never_move(
        self,
    ) -> None:
        """The exact scenario refit_unlisted=False exists for: Applications
        are fully allocated (50+30+20=100%, no headroom). Growing App A to
        60% would require shrinking App B or C to fit — instead of doing
        that, the whole call is rejected. Nobody's ₹ moves, App A's own
        included."""
        svc = _svc()
        svc._tenants.get_by_id_for_update = AsyncMock(return_value=_tenant())
        apps = _three_apps()
        svc._applications.list_by_tenant_for_update = AsyncMock(return_value=apps)
        svc._applications.update = AsyncMock()
        svc._api_keys.list_by_applications = AsyncMock(return_value=[])

        body = TenantBudgetAllocationRequest(
            applications=[ApplicationAllocationRow(application_id=1, allocation=_pct("60"))]
        )
        with patch("app.services.budget_usage.fetch_budget_usage", AsyncMock(return_value={})):
            with pytest.raises(ValidationError) as exc:
                await svc.update_tenant_application_allocations(101, body, _user(), None)

        assert exc.value.code == "ALLOCATION_TOTAL_EXCEEDED"
        svc._applications.update.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_every_application_is_locked_not_just_listed(self) -> None:
        """refit_unlisted=True means any Application may end up written, so
        every one under the Tenant is locked up front, not just the row(s)
        explicitly listed — via one batched list_by_tenant_for_update
        (SELECT ... FOR UPDATE over every row), not a per-row lock loop."""
        svc = _svc()
        svc._tenants.get_by_id_for_update = AsyncMock(return_value=_tenant())
        apps = _three_apps()
        svc._applications.list_by_tenant_for_update = AsyncMock(return_value=apps)
        svc._applications.update = AsyncMock()
        svc._api_keys.list_by_applications = AsyncMock(return_value=[])

        body = TenantBudgetAllocationRequest(
            applications=[ApplicationAllocationRow(application_id=1, allocation=_pct("45"))]
        )
        with patch("app.services.budget_usage.fetch_budget_usage", AsyncMock(return_value={})), \
             patch("app.services.budget_usage.write_budget_snapshot", AsyncMock()):
            await svc.update_tenant_application_allocations(101, body, _user(), None)

        svc._applications.list_by_tenant_for_update.assert_awaited_once_with(101)
        svc._applications.get_by_id_for_update.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_reduce_fully_exhausted_app_b_blocked(self) -> None:
        svc = _svc()
        svc._tenants.get_by_id_for_update = AsyncMock(return_value=_tenant())
        apps = _three_apps()
        keys = [_key(21, 2, allocated_budget=Decimal("30000"), allocated_percentage=Decimal("100"))]
        svc._applications.list_by_tenant_for_update = AsyncMock(return_value=apps)
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
        svc._applications.list_by_tenant_for_update = AsyncMock(return_value=apps)
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
    async def test_resized_application_cascades_into_its_own_unlisted_keys(self) -> None:
        """App A resized 50000 -> 40000; two Keys (30000/20000, unlisted) must
        proportionally re-fit to sum <= 40000, and get persisted + snapshotted."""
        svc = _svc()
        svc._tenants.get_by_id_for_update = AsyncMock(return_value=_tenant())
        apps = _three_apps()
        key1 = _key(11, 1, allocated_budget=Decimal("30000"), allocated_percentage=Decimal("60"))
        key2 = _key(12, 1, allocated_budget=Decimal("20000"), allocated_percentage=Decimal("40"))
        svc._applications.list_by_tenant_for_update = AsyncMock(return_value=apps)
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
    async def test_unchanged_application_with_explicit_key_edits_still_cascades(self) -> None:
        """App A is explicitly listed at its CURRENT value (50%, so
        resolved.changed is False at the Application level) but WITH
        nested api_keys — the cascade must still fire off the `or
        nested_api_keys` half of the check, not just a parent resize.
        App B/C are genuinely untouched (no explicit row, no nesting,
        and the unlisted re-fit scale factor is 1.0 since App A's own
        total didn't move) — their api_keys must come back None, not [],
        since they were never resolved this call at all."""
        svc = _svc()
        svc._tenants.get_by_id_for_update = AsyncMock(return_value=_tenant())
        apps = _three_apps()
        key1 = _key(11, 1, allocated_budget=Decimal("30000"), allocated_percentage=Decimal("60"))
        key2 = _key(12, 1, allocated_budget=Decimal("20000"), allocated_percentage=Decimal("40"))
        svc._applications.list_by_tenant_for_update = AsyncMock(return_value=apps)
        svc._applications.update = AsyncMock()
        svc._api_keys.list_by_applications = AsyncMock(return_value=[key1, key2])
        svc._api_keys.update = AsyncMock()

        body = TenantBudgetAllocationRequest(
            applications=[
                ApplicationAllocationRow(
                    application_id=1,
                    allocation=_pct("50"),  # same as App A's current value
                    api_keys=[APIKeyAllocationRow(api_key_id=11, allocation=_fixed("35000"))],
                )
            ]
        )
        with patch("app.services.budget_usage.fetch_budget_usage", AsyncMock(return_value={})), \
             patch("app.services.budget_usage.write_budget_snapshot", AsyncMock()):
            data = await svc.update_tenant_application_allocations(101, body, _user(), None)

        by_id = {row.application_id: row for row in data}
        # App A's own amount never changed -> no Application-level write.
        svc._applications.update.assert_not_awaited()
        # But its Keys still cascaded: Key 11 to the requested 35000, Key
        # 12 (unlisted) proportionally re-fit to absorb what's left:
        # 20000 * (15000 / 20000) = 15000.
        key_rows = {r.api_key_id: r for r in by_id[1].api_keys}
        assert key_rows[11].allocated_budget == Decimal("35000.00")
        assert key_rows[12].allocated_budget == Decimal("15000.00")
        assert svc._api_keys.update.await_count == 2
        # App B/C: no explicit row, no nesting, and the unlisted re-fit
        # scale factor is 1.0 (App A's total didn't move) -> genuinely not
        # resolved this call. None, not [] — they were never queried.
        assert by_id[2].api_keys is None
        assert by_id[3].api_keys is None

    @pytest.mark.asyncio
    async def test_key_application_mismatch(self) -> None:
        svc = _svc()
        svc._tenants.get_by_id_for_update = AsyncMock(return_value=_tenant())
        apps = _three_apps()
        key_under_app2 = _key(99, 2, allocated_budget=Decimal("30000"), allocated_percentage=Decimal("100"))
        svc._applications.list_by_tenant_for_update = AsyncMock(return_value=apps)
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


class TestTenantBudgetCascade:
    """AllocationService.cascade_tenant_budget_revision — PATCH
    /auth/tenants/{id}/budget's own cascade, called by
    TenantService.revise_tenant_budget (see test_tenant_tier_budget.py for
    that integration; these tests exercise this method directly, since
    nothing here otherwise did)."""

    @pytest.mark.asyncio
    async def test_batched_lock_not_per_row(self) -> None:
        """Every Application under the tenant is locked via one
        list_by_tenant_for_update call, not a get_by_id_for_update loop —
        same reasoning as update_tenant_application_allocations's own
        locking, since this cascade can end up writing any of them too."""
        svc = _svc()
        apps = _three_apps()
        svc._applications.list_by_tenant_for_update = AsyncMock(return_value=apps)
        svc._applications.update = AsyncMock()
        svc._api_keys.list_by_applications = AsyncMock(return_value=[])

        with patch("app.services.budget_usage.fetch_budget_usage", AsyncMock(return_value={})):
            await svc.cascade_tenant_budget_revision(
                101, Decimal("120000"), Decimal("100000"), _user(), None
            )

        svc._applications.list_by_tenant_for_update.assert_awaited_once_with(101)
        svc._applications.get_by_id_for_update.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_top_up_leaves_every_applications_budget_unchanged_recomputes_percentage(
        self,
    ) -> None:
        """A Tenant top-up never moves any Application's ₹ — only
        allocated_percentage is recomputed, since the same ₹ is now a
        different share of a bigger total: 100000 -> 120000, so
        50000/30000/20000 stay exactly 50000/30000/20000, and their
        percentages become 41.67/25.00/16.67 (the growth itself becomes
        additional unallocated headroom, never distributed)."""
        svc = _svc()
        apps = _three_apps()
        svc._applications.list_by_tenant_for_update = AsyncMock(return_value=apps)
        svc._applications.update = AsyncMock()
        svc._api_keys.list_by_applications = AsyncMock(return_value=[])

        with patch("app.services.budget_usage.fetch_budget_usage", AsyncMock(return_value={})):
            applications_recomputed, keys_recomputed, snapshot_writes = (
                await svc.cascade_tenant_budget_revision(
                    101, Decimal("120000"), Decimal("100000"), _user(), None
                )
            )

        assert applications_recomputed == 3
        assert keys_recomputed == 0  # no Application's ₹ ever moves here -> nothing cascades
        assert snapshot_writes == {}
        assert svc._applications.update.await_count == 3
        updates_by_app = {
            call.args[0].id: call.args[1] for call in svc._applications.update.await_args_list
        }
        assert updates_by_app[1]["allocated_percentage"] == Decimal("41.67")
        assert updates_by_app[2]["allocated_percentage"] == Decimal("25.00")
        assert updates_by_app[3]["allocated_percentage"] == Decimal("16.67")
        # allocated_budget is never in the update dict — it's never touched.
        assert "allocated_budget" not in updates_by_app[1]

    @pytest.mark.asyncio
    async def test_top_down_that_still_fits_every_applications_current_budget_succeeds(
        self,
    ) -> None:
        """100000 -> 90000: still >= 50000+30000+20000=100000? No — this
        must actually be infeasible (100000 already allocated > 90000).
        Use a case that DOES fit: only App1(50000)+App2(30000)=80000
        currently exist under the tenant (App3 excluded from this
        fixture), so 90000 still covers them; only percentages move."""
        svc = _svc()
        apps = _three_apps()[:2]  # App1 (50000/50%), App2 (30000/30%) only
        svc._applications.list_by_tenant_for_update = AsyncMock(return_value=apps)
        svc._applications.update = AsyncMock()
        svc._api_keys.list_by_applications = AsyncMock(return_value=[])

        with patch("app.services.budget_usage.fetch_budget_usage", AsyncMock(return_value={})):
            applications_recomputed, keys_recomputed, snapshot_writes = (
                await svc.cascade_tenant_budget_revision(
                    101, Decimal("90000"), Decimal("100000"), _user(), None
                )
            )

        assert applications_recomputed == 2
        assert keys_recomputed == 0
        updates_by_app = {
            call.args[0].id: call.args[1] for call in svc._applications.update.await_args_list
        }
        # 50000/90000*100 = 55.56, 30000/90000*100 = 33.33 — budgets unchanged.
        assert updates_by_app[1]["allocated_percentage"] == Decimal("55.56")
        assert updates_by_app[2]["allocated_percentage"] == Decimal("33.33")

    @pytest.mark.asyncio
    async def test_top_down_below_what_applications_already_hold_is_rejected(self) -> None:
        """App1(50000) + App2(30000) + App3(20000) = 100000 already
        allocated. Topping the tenant down to 90000 doesn't leave enough
        room to cover what's already allocated — nobody auto-shrinks
        anymore, so the whole revision is rejected instead."""
        svc = _svc()
        apps = _three_apps()
        svc._applications.list_by_tenant_for_update = AsyncMock(return_value=apps)
        svc._applications.update = AsyncMock()
        svc._api_keys.list_by_applications = AsyncMock(return_value=[])

        with patch("app.services.budget_usage.fetch_budget_usage", AsyncMock(return_value={})):
            with pytest.raises(ValidationError) as exc:
                await svc.cascade_tenant_budget_revision(
                    101, Decimal("90000"), Decimal("100000"), _user(), None
                )

        assert exc.value.code == "ALLOCATION_TOTAL_EXCEEDED"
        svc._applications.update.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_no_applications_under_tenant_is_a_no_op(self) -> None:
        svc = _svc()
        svc._applications.list_by_tenant_for_update = AsyncMock(return_value=[])

        result = await svc.cascade_tenant_budget_revision(
            101, Decimal("120000"), Decimal("100000"), _user(), None
        )

        assert result == (0, 0, {})
        svc._applications.update.assert_not_awaited()


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
    async def test_direct_key_reduction_leaves_untouched_sibling_in_response(self) -> None:
        """Key 12 isn't listed and isn't re-fit (refit_unlisted=False at
        this edge — resizing one Key never moves another) — but it's still
        merged back into the response from its current DB values, since
        the contract returns every Key. Reducing Key 11 to 25000 leaves
        the freed 5000 (30000+20000=50000 was fully allocated) genuinely
        unallocated, not given to Key 12."""
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
        # Untouched sibling — merged back from its current DB values, still PERCENTAGE.
        assert by_id[12].allocated_budget == Decimal("20000.00")
        assert by_id[12].allocation == AllocationValue(type="PERCENTAGE", value=Decimal("40"))
        svc._api_keys.update.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_growing_a_key_beyond_available_headroom_is_blocked(self) -> None:
        """The exact scenario refit_unlisted=False exists for at this edge:
        Key 1 + Key 2 already sum to the Application's full 50000 (fully
        allocated). Growing Key 1 to 35000 would require shrinking Key 2 —
        instead the whole call is rejected, and neither Key's ₹ moves."""
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
            api_keys=[APIKeyAllocationRow(api_key_id=11, allocation=_fixed("35000"))],
        )
        with patch("app.services.budget_usage.fetch_budget_usage", AsyncMock(return_value={})):
            with pytest.raises(ValidationError) as exc:
                await svc.update_application_key_allocations(1, body, _user(), None)

        assert exc.value.code == "ALLOCATION_TOTAL_EXCEEDED"
        svc._api_keys.update.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_revoked_sibling_is_excluded_not_refit_and_freed_room_stays_unallocated(
        self,
    ) -> None:
        """A revoked Key is terminal — it's excluded from the response
        entirely, unlike an active unlisted sibling (which is merged back
        in from its current DB values — see
        test_direct_key_reduction_leaves_untouched_sibling_in_response).
        Key 12's own stale allocated_budget never changes either way."""
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
        60% + 30% = 90%, leaving 10% (5000) genuinely unallocated headroom
        — Key 1 growing from 60% to 70% draws exactly that (+5000) without
        touching Key 2 at all (refit_unlisted=False: siblings never move,
        an explicit edit only ever draws on unallocated room)."""
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
        assert by_id[12].allocated_budget == Decimal("15000.00")  # untouched, merged back in
        svc._api_keys.update.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_growing_a_key_beyond_headroom_via_single_key_endpoint_is_blocked(
        self,
    ) -> None:
        """Same rejection as the Application-level endpoint's own headroom
        test, via the single-Key endpoint: Key 1 + Key 2 already fill the
        Application (30000+15000... plus this fixture's own 5000 slack is
        removed by pre-allocating Key 2 to fill it), so growing Key 1
        beyond what's left is rejected rather than shrinking Key 2."""
        svc = _svc()
        app = _application(1, allocated_budget=Decimal("50000"), allocated_percentage=Decimal("50"))
        key1 = _key(11, 1, allocated_budget=Decimal("30000"), allocated_percentage=Decimal("60"))
        key2 = _key(12, 1, allocated_budget=Decimal("20000"), allocated_percentage=Decimal("40"))
        svc._api_keys.get_by_id = AsyncMock(return_value=key1)
        svc._applications.get_by_id = AsyncMock(return_value=app)
        svc._applications.get_by_id_for_update = AsyncMock(return_value=app)
        svc._api_keys.list_by_application = AsyncMock(return_value=[key1, key2])
        svc._api_keys.update = AsyncMock()

        body = APIKeyBudgetAllocationRequest(api_key_id=11, allocation=_pct("70"))
        with patch("app.services.budget_usage.fetch_budget_usage", AsyncMock(return_value={})):
            with pytest.raises(ValidationError) as exc:
                await svc.update_single_api_key_allocation(11, body, _user(), None)

        assert exc.value.code == "ALLOCATION_TOTAL_EXCEEDED"
        svc._api_keys.update.assert_not_awaited()

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
