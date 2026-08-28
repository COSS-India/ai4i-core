"""Tests for the three tenant tier/budget endpoints that replaced
platform-core-service's pay-per-use tenant routes (assign_tenant_tier,
revise_tenant_budget, list_tenant_tiers) — added because the PR that
introduced them deleted the 509-line test file covering the endpoints they
replace without adding coverage of its own.

Focus is the reviewer-flagged enforcement-path reconnection: assigning a
tier must write a ppu_tenant_tier_assignments row (or the billing consumer
never sees an active assignment and quota-flags the tenant after its first
request), a budget top-up must clear a stale budget-exhausted flag, and a
reassignment must clear stale quota flags and force-refresh cached tier_id.
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.core.exceptions import ValidationError
from app.models.tenant import Tenant, TenantStatus
from app.models.user import User
from app.services.tenant_service import TenantService


def _admin_user() -> User:
    return User(id=uuid4(), email="test-admin@example.invalid", username=uuid4().hex[:12])


def _tenant(*, tier_id=None, allocated_budget=None, budget_effective_from=None, budget_effective_to=None) -> Tenant:
    return Tenant(
        id=1, name="Acme", organisation="Acme", email="test-contact@example.invalid",
        status=TenantStatus.ACTIVE, tier_id=tier_id, allocated_budget=allocated_budget,
        budget_effective_from=budget_effective_from, budget_effective_to=budget_effective_to,
    )


def _svc(*, roles=("ADMIN",)) -> TenantService:
    svc = TenantService(
        tenant_repo=AsyncMock(),
        user_repo=AsyncMock(),
        role_service=AsyncMock(),
        verification_repo=AsyncMock(),
        credentials_repo=AsyncMock(),
        token_service=AsyncMock(),
        email_client=AsyncMock(),
        api_key_service=AsyncMock(),
    )
    svc._roles.get_user_roles = AsyncMock(return_value=list(roles))
    return svc


def _core_db(*, tier_row=(), existing_assignment=None) -> AsyncMock:
    """A platform_core_db mock whose .execute() responses are queued in the
    call order assign_tenant_tier/list_tenant_tiers/revise_tenant_budget
    actually issue them."""
    db = AsyncMock()
    responses = list(tier_row) if isinstance(tier_row, list) else [tier_row]

    def _result(value):
        r = MagicMock()
        r.first.return_value = value
        r.all.return_value = value if isinstance(value, list) else []
        return r

    db.execute = AsyncMock(side_effect=[_result(v) for v in responses])
    return db


class TestAssignTenantTierAuthAndValidation:
    @pytest.mark.asyncio
    async def test_non_admin_rejected(self) -> None:
        svc = _svc(roles=["TENANT ADMIN"])
        with pytest.raises(HTTPException) as exc_info:
            await svc.assign_tenant_tier(_admin_user(), 1, str(uuid4()), AsyncMock())
        assert exc_info.value.status_code == 403
        assert exc_info.value.detail["code"] == "INSUFFICIENT_PERMISSIONS"

    @pytest.mark.asyncio
    async def test_invalid_uuid_rejected(self) -> None:
        svc = _svc()
        with pytest.raises(HTTPException) as exc_info:
            await svc.assign_tenant_tier(_admin_user(), 1, "not-a-uuid", AsyncMock())
        assert exc_info.value.status_code == 400
        assert exc_info.value.detail["code"] == "INVALID_TIER_ID"

    @pytest.mark.asyncio
    async def test_platform_core_db_none_rejected(self) -> None:
        svc = _svc()
        svc._tenants.get_by_id_for_update = AsyncMock(return_value=_tenant())
        with pytest.raises(ValidationError) as exc_info:
            await svc.assign_tenant_tier(_admin_user(), 1, str(uuid4()), None)
        assert exc_info.value.code == "PLATFORM_CORE_DB_NOT_CONFIGURED"

    @pytest.mark.asyncio
    async def test_unknown_tier_rejected(self) -> None:
        svc = _svc()
        svc._tenants.get_by_id_for_update = AsyncMock(return_value=_tenant())
        db = _core_db(tier_row=None)
        with pytest.raises(HTTPException) as exc_info:
            await svc.assign_tenant_tier(_admin_user(), 1, str(uuid4()), db)
        assert exc_info.value.status_code == 404
        assert exc_info.value.detail["code"] == "TIER_NOT_FOUND"

    @pytest.mark.asyncio
    async def test_already_on_tier_rejected(self) -> None:
        tier_id = uuid4()
        svc = _svc()
        svc._tenants.get_by_id_for_update = AsyncMock(return_value=_tenant(tier_id=tier_id))
        tier_row = MagicMock(id=tier_id)
        tier_row.name = "Gold"
        # 1st execute: tier lookup. 2nd: an active assignment DOES exist —
        # genuinely a no-op, must still 409.
        active_row = MagicMock()
        db = _core_db(tier_row=[tier_row, active_row])
        with pytest.raises(HTTPException) as exc_info:
            await svc.assign_tenant_tier(_admin_user(), 1, str(tier_id), db)
        assert exc_info.value.status_code == 409
        assert exc_info.value.detail["code"] == "TENANT_ALREADY_ON_TIER"
        svc._tenants.update.assert_not_awaited()


class TestAssignTenantTierIdempotentRepair:
    """The failure mode of the write-through itself: tenants.tier_id can
    commit on one PATCH, then the required ppu_tenant_tier_assignments
    write can fail (core DB down, constraint, network) — unguarded on
    purpose, so that failure surfaces as a 500 rather than being silently
    swallowed. What must not happen is the retry becoming a dead end."""

    @pytest.mark.asyncio
    async def test_retry_after_partial_failure_repairs_missing_assignment_row(self) -> None:
        """tenant.tier_id already equals the requested tier (committed by
        the failed first attempt) but no active assignment row exists (that
        attempt's ppu write never landed) — must repair by inserting the
        row, not reject with TENANT_ALREADY_ON_TIER, or the admin has no
        way to fix this tenant through the API at all."""
        tier_id = uuid4()
        tenant = _tenant(tier_id=tier_id, allocated_budget=Decimal("100"))
        svc = _svc()
        svc._tenants.get_by_id_for_update = AsyncMock(return_value=tenant)
        tier_row = MagicMock(id=tier_id)
        tier_row.name = "Gold"
        # 1st execute: tier lookup. 2nd: no active assignment (the repair
        # case). 3rd: "existing row?" inside the upsert -> none. 4th: the
        # INSERT itself.
        db = _core_db(tier_row=[tier_row, None, None, None])

        result = await svc.assign_tenant_tier(_admin_user(), 1, str(tier_id), db)

        assert result is tenant
        svc._tenants.update.assert_not_awaited()  # tier_id already correct — nothing to change there
        insert_call = db.execute.await_args_list[-1]
        assert "INSERT INTO ppu_tenant_tier_assignments" in str(insert_call.args[0])
        svc._api_keys.clear_quota_flags_for_tenant.assert_awaited_once_with(1)
        svc._api_keys.set_tier_id_for_tenant.assert_awaited_once_with(1, str(tier_id))

    @pytest.mark.asyncio
    async def test_retry_after_reassignment_partial_failure_repairs_stale_row(self) -> None:
        """Worse than the missing-row case: tenants.tier_id committed to
        the NEW tier on a failed reassignment attempt, but the upsert's
        UPDATE (which moves an existing row's tier_id in place rather than
        inserting) never landed — the active row still points at the OLD
        tier. The existence check must be scoped to tier_id, not just
        tenant_id, or this reads as "already on the requested tier" and
        409s forever, leaving auth/billing/cache permanently disagreeing
        with no repair path."""
        old_tier_id, new_tier_id = uuid4(), uuid4()
        # tenants.tier_id already committed to new_tier_id by the failed attempt.
        tenant = _tenant(tier_id=new_tier_id)
        svc = _svc()
        svc._tenants.get_by_id_for_update = AsyncMock(return_value=tenant)
        tier_row = MagicMock(id=new_tier_id)
        tier_row.name = "Platinum"
        stale_row = MagicMock(id=uuid4())
        # 1st execute: tier lookup. 2nd: has_active_ppu_assignment scoped to
        # new_tier_id -> no match (the row that exists is still old_tier_id).
        # 3rd: the upsert's own untier'd "existing row?" lookup -> finds the
        # stale row. 4th: UPDATE it onto new_tier_id.
        db = _core_db(tier_row=[tier_row, None, stale_row, None])

        result = await svc.assign_tenant_tier(_admin_user(), 1, str(new_tier_id), db)

        assert result is tenant
        svc._tenants.update.assert_not_awaited()  # tier_id already correct
        repair_call = db.execute.await_args_list[-1]
        repair_sql = str(repair_call.args[0])
        assert "UPDATE ppu_tenant_tier_assignments" in repair_sql
        assert repair_call.args[1]["tier_id"] == new_tier_id
        assert repair_call.args[1]["id"] == stale_row.id
        svc._api_keys.clear_quota_flags_for_tenant.assert_awaited_once_with(1)
        svc._api_keys.set_tier_id_for_tenant.assert_awaited_once_with(1, str(new_tier_id))

    @pytest.mark.asyncio
    async def test_genuine_reassignment_still_updates_tenant_row(self) -> None:
        """Sanity check the repair path doesn't leak into the normal
        (different-tier) case: tenants.tier_id must still be updated when
        it's actually changing."""
        old_tier_id, new_tier_id = uuid4(), uuid4()
        tenant = _tenant(tier_id=old_tier_id)
        svc = _svc()
        svc._tenants.get_by_id_for_update = AsyncMock(return_value=tenant)
        svc._tenants.update = AsyncMock()
        svc._tenants.save_and_refresh = AsyncMock()
        tier_row = MagicMock(id=new_tier_id)
        tier_row.name = "Platinum"
        db = _core_db(tier_row=[tier_row, None, None])  # tier lookup, no existing assignment, INSERT

        await svc.assign_tenant_tier(_admin_user(), 1, str(new_tier_id), db)

        svc._tenants.update.assert_awaited_once()
        assert svc._tenants.update.await_args.args[1]["tier_id"] == new_tier_id


class TestAssignTenantTierEnforcementReconnection:
    @pytest.mark.asyncio
    async def test_first_assignment_inserts_ppu_assignment_row(self) -> None:
        """No active row exists yet — must INSERT one seeded from the
        tenant's own budget fields, or the billing consumer's wallet_update
        CTE matches nothing on this tenant's very next inference request."""
        new_tier_id = uuid4()
        tenant = _tenant(
            tier_id=None,
            allocated_budget=Decimal("1000.00"),
            budget_effective_from=datetime(2026, 1, 1, tzinfo=timezone.utc),
            budget_effective_to=datetime(2027, 1, 1, tzinfo=timezone.utc),
        )
        svc = _svc()
        svc._tenants.get_by_id_for_update = AsyncMock(return_value=tenant)
        svc._tenants.update = AsyncMock()
        svc._tenants.save_and_refresh = AsyncMock()
        tier_row = MagicMock(id=new_tier_id)
        tier_row.name = "Gold"
        # 1st execute: tier lookup. 2nd: "existing active assignment?" -> none.
        # 3rd: the INSERT itself (return value unused).
        db = _core_db(tier_row=[tier_row, None, None])

        await svc.assign_tenant_tier(_admin_user(), 1, str(new_tier_id), db)

        insert_call = db.execute.await_args_list[-1]
        insert_sql = str(insert_call.args[0])
        assert "INSERT INTO ppu_tenant_tier_assignments" in insert_sql
        params = insert_call.args[1]
        assert params["tenant_id"] == "1"
        assert params["tier_id"] == new_tier_id
        assert params["budget"] == Decimal("1000.00")
        assert params["effective_from"] == tenant.budget_effective_from
        assert params["effective_to"] == tenant.budget_effective_to
        db.commit.assert_awaited()
        svc._api_keys.clear_quota_flags_for_tenant.assert_awaited_once_with(1)
        svc._api_keys.set_tier_id_for_tenant.assert_awaited_once_with(1, str(new_tier_id))

    @pytest.mark.asyncio
    async def test_reassignment_updates_existing_row_not_insert(self) -> None:
        """An active row already covers now() — must UPDATE its tier_id in
        place, carrying budget_limit/available_balance over unchanged
        (matches the old reassign_tier's documented behavior), not insert
        a second row."""
        old_tier_id, new_tier_id = uuid4(), uuid4()
        tenant = _tenant(tier_id=old_tier_id)
        svc = _svc()
        svc._tenants.get_by_id_for_update = AsyncMock(return_value=tenant)
        svc._tenants.update = AsyncMock()
        svc._tenants.save_and_refresh = AsyncMock()
        tier_row = MagicMock(id=new_tier_id)
        tier_row.name = "Platinum"
        existing_row = MagicMock(id=uuid4())
        # 1st execute: tier lookup. 2nd: existing active assignment found.
        # 3rd: the UPDATE itself (return value unused).
        db = _core_db(tier_row=[tier_row, existing_row, None])

        await svc.assign_tenant_tier(_admin_user(), 1, str(new_tier_id), db)

        update_call = db.execute.await_args_list[-1]
        update_sql = str(update_call.args[0])
        assert "UPDATE ppu_tenant_tier_assignments" in update_sql
        assert "INSERT" not in update_sql
        assert update_call.args[1]["tier_id"] == new_tier_id
        assert update_call.args[1]["id"] == existing_row.id
        svc._api_keys.clear_quota_flags_for_tenant.assert_awaited_once_with(1)
        svc._api_keys.set_tier_id_for_tenant.assert_awaited_once_with(1, str(new_tier_id))


class TestReviseTenantBudget:
    @pytest.mark.asyncio
    async def test_non_admin_rejected(self) -> None:
        svc = _svc(roles=["TENANT ADMIN"])
        with pytest.raises(HTTPException) as exc_info:
            await svc.revise_tenant_budget(_admin_user(), 1, "top-up", Decimal("100"))
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_top_up_exceeding_ceiling_rejected(self) -> None:
        svc = _svc()
        svc._tenants.get_by_id_for_update = AsyncMock(
            return_value=_tenant(allocated_budget=Decimal("0"))
        )
        with pytest.raises(HTTPException) as exc_info:
            await svc.revise_tenant_budget(
                _admin_user(), 1, "top-up", Decimal("99999999999999.00")
            )
        assert exc_info.value.status_code == 422
        assert exc_info.value.detail["error"] == "budget_limit_exceeded"

    @pytest.mark.asyncio
    async def test_top_down_below_zero_rejected(self) -> None:
        svc = _svc()
        svc._tenants.get_by_id_for_update = AsyncMock(
            return_value=_tenant(allocated_budget=Decimal("50"))
        )
        with pytest.raises(HTTPException) as exc_info:
            await svc.revise_tenant_budget(_admin_user(), 1, "top-down", Decimal("100"))
        assert exc_info.value.status_code == 422
        assert exc_info.value.detail["error"] == "budget_negative"

    @pytest.mark.asyncio
    async def test_top_up_clears_budget_exhausted_flag(self) -> None:
        """Closes the gap the endpoint this replaces didn't have: the
        consumer only ever posts {"exhausted": true}, so a key already
        flagged budget-exhausted=1 needs this call to have any path back."""
        svc = _svc()
        svc._tenants.get_by_id_for_update = AsyncMock(
            return_value=_tenant(allocated_budget=Decimal("0"))
        )
        svc._tenants.update = AsyncMock()
        svc._tenants.save_and_refresh = AsyncMock()
        wallet_row = MagicMock(available_balance=Decimal("500.00"))
        db = _core_db(tier_row=wallet_row)

        await svc.revise_tenant_budget(_admin_user(), 1, "top-up", Decimal("500"), db)

        svc._api_keys.set_budget_exhausted_for_tenant.assert_awaited_once_with(1, False)

    @pytest.mark.asyncio
    async def test_top_down_to_zero_sets_budget_exhausted_flag(self) -> None:
        svc = _svc()
        svc._tenants.get_by_id_for_update = AsyncMock(
            return_value=_tenant(allocated_budget=Decimal("500"))
        )
        svc._tenants.update = AsyncMock()
        svc._tenants.save_and_refresh = AsyncMock()
        wallet_row = MagicMock(available_balance=Decimal("0"))
        db = _core_db(tier_row=wallet_row)

        await svc.revise_tenant_budget(_admin_user(), 1, "top-down", Decimal("500"), db)

        svc._api_keys.set_budget_exhausted_for_tenant.assert_awaited_once_with(1, True)

    @pytest.mark.asyncio
    async def test_no_active_assignment_skips_flag_sync(self) -> None:
        """Tenant has never been tier-assigned (or its window lapsed) — no
        wallet row to update, so nothing is written and the cache flag is
        left alone rather than guessed at."""
        svc = _svc()
        svc._tenants.get_by_id_for_update = AsyncMock(
            return_value=_tenant(allocated_budget=Decimal("0"))
        )
        svc._tenants.update = AsyncMock()
        svc._tenants.save_and_refresh = AsyncMock()
        db = _core_db(tier_row=None)  # UPDATE ... RETURNING matched no row

        await svc.revise_tenant_budget(_admin_user(), 1, "top-up", Decimal("500"), db)

        svc._api_keys.set_budget_exhausted_for_tenant.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_platform_core_db_none_still_updates_tenant_budget(self) -> None:
        """The ppu-wallet sync is best-effort — an unconfigured/unreachable
        platform-core DB must not block the primary allocated_budget write."""
        svc = _svc()
        svc._tenants.get_by_id_for_update = AsyncMock(
            return_value=_tenant(allocated_budget=Decimal("0"))
        )
        svc._tenants.update = AsyncMock()
        svc._tenants.save_and_refresh = AsyncMock()

        tenant = await svc.revise_tenant_budget(
            _admin_user(), 1, "top-up", Decimal("500"), None
        )

        svc._tenants.update.assert_awaited_once()
        assert svc._tenants.update.await_args.args[1]["allocated_budget"] == Decimal("500")
        svc._api_keys.set_budget_exhausted_for_tenant.assert_not_awaited()


class TestListTenantTiers:
    @pytest.mark.asyncio
    async def test_non_admin_rejected(self) -> None:
        svc = _svc(roles=["TENANT ADMIN"])
        with pytest.raises(HTTPException) as exc_info:
            await svc.list_tenant_tiers(_admin_user(), None, AsyncMock())
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_platform_core_db_none_fails_closed(self) -> None:
        """Previously degraded silently: every tier_name came back null with
        no log line, and a tier_id filter's existence check was skipped
        outright (an unknown tier_id returned 200 + [] instead of 404).
        Must match assign_tenant_tier's handling of the same condition."""
        svc = _svc()
        with pytest.raises(ValidationError) as exc_info:
            await svc.list_tenant_tiers(_admin_user(), None, None)
        assert exc_info.value.code == "PLATFORM_CORE_DB_NOT_CONFIGURED"

    @pytest.mark.asyncio
    async def test_invalid_tier_id_format_rejected(self) -> None:
        svc = _svc()
        with pytest.raises(HTTPException) as exc_info:
            await svc.list_tenant_tiers(_admin_user(), "not-a-uuid", AsyncMock())
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_inactive_tier_filter_404s_consistently_with_assign(self) -> None:
        """The existence check must apply the same is_active = true filter
        assign_tenant_tier uses — otherwise a tier listable here could be
        rejected as not-found by assign, a visible inconsistency."""
        svc = _svc()
        db = _core_db(tier_row=None)  # is_active filter excludes it
        with pytest.raises(HTTPException) as exc_info:
            await svc.list_tenant_tiers(_admin_user(), str(uuid4()), db)
        assert exc_info.value.status_code == 404
        query_sql = str(db.execute.await_args_list[0].args[0])
        assert "is_active = true" in query_sql

    @pytest.mark.asyncio
    async def test_resolves_tier_names_for_listed_tenants(self) -> None:
        tier_id = uuid4()
        tenant = _tenant(tier_id=tier_id, allocated_budget=Decimal("100"))
        svc = _svc()
        svc._tenants.list_with_tier = AsyncMock(return_value=[tenant])
        name_row = MagicMock(id=tier_id)
        name_row.name = "Gold"
        db = AsyncMock()
        db.execute = AsyncMock(return_value=MagicMock(all=MagicMock(return_value=[name_row])))

        result = await svc.list_tenant_tiers(_admin_user(), None, db)

        assert result[0]["tenant_id"] == 1
        assert result[0]["tier_name"] == "Gold"
