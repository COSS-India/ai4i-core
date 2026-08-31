"""Tests for the three tenant tier/budget endpoints that replaced
platform-core-service's pay-per-use tenant routes (assign_tenant_tier,
revise_tenant_budget, list_tenant_tiers) — added because the PR that
introduced them deleted the 509-line test file covering the endpoints they
replace without adding coverage of its own.

These endpoints used to also write through to platform-core's
``ppu_tenant_tier_assignments`` — a per-tenant wallet the old billing
consumer read to find an active assignment and deduct spend from, with its
own idempotent-repair logic for a partial failure between the two writes,
and a budget revision would sync that wallet's balance and recompute a
tenant-wide cached budget-exhausted flag from it. That table was dropped
(migration a1b3c5d7e9f0 / PR #1505, AI4IDS-2923): billing now reads
``tenants.tier_id`` live per request (via the X-Tier-ID header -> OTel span)
and tracks spend per API Key in ``budget_usage``, not per tenant. So there
is no second write left to reconnect, no partial-failure window, and no
tenant-level wallet to sync — assign_tenant_tier and revise_tenant_budget
only ever touch the ``tenants`` row (plus the tier-scoped quota/cache calls
that are still meaningful) now. The tests that used to pin the
now-removed write-through/repair/sync behaviour are gone with it; what's
left here covers what those two endpoints actually still do.
"""

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
        """tenants.tier_id already matches — unconditionally a 409 now,
        since there's no second write whose partial failure could make this
        state ambiguous (see the module docstring)."""
        tier_id = uuid4()
        svc = _svc()
        svc._tenants.get_by_id_for_update = AsyncMock(return_value=_tenant(tier_id=tier_id))
        tier_row = MagicMock(id=tier_id)
        tier_row.name = "Gold"
        db = _core_db(tier_row=tier_row)  # only the tier lookup — one execute
        with pytest.raises(HTTPException) as exc_info:
            await svc.assign_tenant_tier(_admin_user(), 1, str(tier_id), db)
        assert exc_info.value.status_code == 409
        assert exc_info.value.detail["code"] == "TENANT_ALREADY_ON_TIER"
        svc._tenants.update.assert_not_awaited()


class TestAssignTenantTierEffects:
    """What a genuine (different-tier) assignment/reassignment actually does
    now: update tenants.tier_id, clear stale quota flags, force-write the
    new tier_id into cached API key data. No second write anywhere else —
    see the module docstring for what used to happen here and why it
    doesn't any more."""

    @pytest.mark.asyncio
    async def test_first_assignment_updates_tenant_and_cache(self) -> None:
        new_tier_id = uuid4()
        tenant = _tenant(tier_id=None, allocated_budget=Decimal("1000.00"))
        svc = _svc()
        svc._tenants.get_by_id_for_update = AsyncMock(return_value=tenant)
        svc._tenants.update = AsyncMock()
        svc._tenants.save_and_refresh = AsyncMock()
        tier_row = MagicMock(id=new_tier_id)
        tier_row.name = "Gold"
        db = _core_db(tier_row=tier_row)  # only the tier lookup — one execute

        result = await svc.assign_tenant_tier(_admin_user(), 1, str(new_tier_id), db)

        assert result is tenant
        svc._tenants.update.assert_awaited_once()
        assert svc._tenants.update.await_args.args[1]["tier_id"] == new_tier_id
        svc._api_keys.clear_quota_flags_for_tenant.assert_awaited_once_with(1)
        svc._api_keys.set_tier_id_for_tenant.assert_awaited_once_with(1, str(new_tier_id))
        # Nothing else was ever queried from platform-core beyond the tier lookup.
        assert db.execute.await_count == 1

    @pytest.mark.asyncio
    async def test_reassignment_updates_tenant_and_cache(self) -> None:
        old_tier_id, new_tier_id = uuid4(), uuid4()
        tenant = _tenant(tier_id=old_tier_id)
        svc = _svc()
        svc._tenants.get_by_id_for_update = AsyncMock(return_value=tenant)
        svc._tenants.update = AsyncMock()
        svc._tenants.save_and_refresh = AsyncMock()
        tier_row = MagicMock(id=new_tier_id)
        tier_row.name = "Platinum"
        db = _core_db(tier_row=tier_row)

        await svc.assign_tenant_tier(_admin_user(), 1, str(new_tier_id), db)

        assert svc._tenants.update.await_args.args[1]["tier_id"] == new_tier_id
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
    async def test_top_up_updates_allocated_budget_only(self) -> None:
        """No platform-core dependency at all any more — a top-up only
        touches tenants.allocated_budget. See the module docstring for why
        there's nothing left to sync alongside it."""
        svc = _svc()
        svc._tenants.get_by_id_for_update = AsyncMock(
            return_value=_tenant(allocated_budget=Decimal("0"))
        )
        svc._tenants.update = AsyncMock()
        svc._tenants.save_and_refresh = AsyncMock()

        tenant = await svc.revise_tenant_budget(_admin_user(), 1, "top-up", Decimal("500"))

        svc._tenants.update.assert_awaited_once()
        assert svc._tenants.update.await_args.args[1]["allocated_budget"] == Decimal("500")
        assert tenant is not None


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


class TestTenantCountForTier:
    """Backs GET /internal/tenants/tier/{tier_id}/count — platform-core-service's
    delete_tier in-use check now asks auth-service this, since tier<->tenant
    assignment lives solely on tenants.tier_id and platform-core-service has no
    DB-local way to answer it any more (ppu_tenant_tier_assignments dropped)."""

    @pytest.mark.asyncio
    async def test_counts_tenants_on_the_tier(self) -> None:
        tier_id = uuid4()
        svc = _svc()
        svc._tenants.list_with_tier = AsyncMock(return_value=[_tenant(), _tenant()])

        count = await svc.tenant_count_for_tier(str(tier_id))

        assert count == 2
        svc._tenants.list_with_tier.assert_awaited_once_with(tier_id)

    @pytest.mark.asyncio
    async def test_zero_when_no_tenants_on_the_tier(self) -> None:
        svc = _svc()
        svc._tenants.list_with_tier = AsyncMock(return_value=[])

        count = await svc.tenant_count_for_tier(str(uuid4()))

        assert count == 0

    @pytest.mark.asyncio
    async def test_invalid_uuid_returns_zero_without_querying(self) -> None:
        svc = _svc()
        svc._tenants.list_with_tier = AsyncMock(return_value=[])

        count = await svc.tenant_count_for_tier("not-a-uuid")

        assert count == 0
        svc._tenants.list_with_tier.assert_not_awaited()
