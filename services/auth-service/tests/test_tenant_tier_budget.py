"""Tests for the three tenant tier/budget endpoints that replaced
platform-core-service's pay-per-use tenant routes (assign_tenant_tier,
revise_tenant_budget, list_tenant_tiers) — added because the PR that
introduced them deleted the 509-line test file covering the endpoints they
replace without adding coverage of its own.

AI4IDS-2923 dropped platform-core's ppu_tenant_tier_assignments table.
assign_tenant_tier and revise_tenant_budget both used to write/read it via a
cross-DB call; that write-through is now removed entirely
(assign_tenant_tier — tenants.tier_id is the sole source of truth, matching
create_api_key's NO_ACTIVE_TIER gate, which already only reads that column)
or reconstructed from currently-live tables
(revise_tenant_budget/_sync_ppu_wallet_and_exhaustion — allocated_budget on
tenants plus spend summed from platform-core's budget_usage ledger, the same
reconstruction platform-core-service's own get_tenant_budgets already does).
Focus here is that the enforcement-path reconnection this file originally
covered (a tier assignment must be visible to billing/quota enforcement; a
budget top-up must clear a stale budget-exhausted flag) still holds under the
new implementation, without depending on a table that no longer exists.
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import ANY, AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.core.exceptions import ValidationError
from app.models.tenant import Tenant, TenantStatus
from app.models.user import User
from app.services.tenant_service import TenantService

# A valid budget window for tests that aren't specifically exercising the
# From/To validation itself — From is "now" (always >= today's UTC date),
# To is comfortably more than one calendar day after it.
_VALID_EFFECTIVE_FROM = datetime.now(timezone.utc)
_VALID_EFFECTIVE_TO = _VALID_EFFECTIVE_FROM + timedelta(days=30)


def _admin_user() -> User:
    return User(id=uuid4(), email="test-admin@example.invalid", username=uuid4().hex[:12])


def _tenant(*, tier_id=None, allocated_budget=None) -> Tenant:
    return Tenant(
        id=1, name="Acme", organisation="Acme", email="test-contact@example.invalid",
        status=TenantStatus.ACTIVE, tier_id=tier_id, allocated_budget=allocated_budget,
    )


def _svc(*, roles=("ADMIN",), allocation_service=None) -> TenantService:
    if allocation_service is None:
        # Default double for revise_tenant_budget's cascade: no Applications/
        # Keys actually recomputed, nothing to snapshot. Tests exercising the
        # cascade itself pass their own mock with a more specific
        # cascade_tenant_budget_revision return value.
        allocation_service = AsyncMock()
        allocation_service.cascade_tenant_budget_revision = AsyncMock(
            return_value=(0, 0, {})
        )
    svc = TenantService(
        tenant_repo=AsyncMock(),
        user_repo=AsyncMock(),
        role_service=AsyncMock(),
        verification_repo=AsyncMock(),
        credentials_repo=AsyncMock(),
        token_service=AsyncMock(),
        email_client=AsyncMock(),
        api_key_service=AsyncMock(),
        allocation_service=allocation_service,
    )
    svc._roles.get_user_roles = AsyncMock(return_value=list(roles))
    return svc


def _core_db(*, tier_row=(), budget_usage_rows=None) -> AsyncMock:
    """A platform_core_db mock whose .execute() responses are queued in the
    call order assign_tenant_tier/list_tenant_tiers/revise_tenant_budget
    actually issue them. ``budget_usage_rows`` (used only by
    revise_tenant_budget's flow) is appended after ``tier_row``.

    A top-down revision now calls fetch_budget_usage TWICE — once to verify
    spend before the write (revise_tenant_budget's own gate), once again in
    _sync_ppu_wallet_and_exhaustion after it commits — while a top-up only
    ever calls it once (the sync). Pass a flat list of rows for a single
    fetch (top-up), or a list of two row-lists (one per fetch_budget_usage
    call) for a top-down that reaches both."""
    db = AsyncMock()
    if tier_row == ():
        # Default sentinel: no tier-lookup response queued at all (used by
        # revise_tenant_budget tests, which never query the tiers table).
        responses = []
    elif isinstance(tier_row, list):
        responses = list(tier_row)
    else:
        responses = [tier_row]

    def _result(value):
        r = MagicMock()
        r.first.return_value = value
        r.all.return_value = value if isinstance(value, list) else []
        return r

    side_effects = [_result(v) for v in responses]
    if budget_usage_rows is not None:
        if budget_usage_rows and isinstance(budget_usage_rows[0], list):
            side_effects.extend(_result(v) for v in budget_usage_rows)
        else:
            side_effects.append(_result(budget_usage_rows))
    db.execute = AsyncMock(side_effect=side_effects)
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
        """tenants.tier_id is the sole source of truth now — no second table
        to check, so this is a straight comparison, not a two-step lookup."""
        tier_id = uuid4()
        svc = _svc()
        svc._tenants.get_by_id_for_update = AsyncMock(return_value=_tenant(tier_id=tier_id))
        tier_row = MagicMock(id=tier_id)
        tier_row.name = "Gold"
        db = _core_db(tier_row=[tier_row])  # only the tier lookup — no assignment table left to query

        with pytest.raises(HTTPException) as exc_info:
            await svc.assign_tenant_tier(_admin_user(), 1, str(tier_id), db)

        assert exc_info.value.status_code == 409
        assert exc_info.value.detail["code"] == "TENANT_ALREADY_ON_TIER"
        svc._tenants.update.assert_not_awaited()
        # Exactly one platform_core_db call (the tier lookup) — confirms no
        # leftover query against the dropped ppu_tenant_tier_assignments table.
        assert db.execute.await_count == 1


class TestAssignTenantTierReassignment:
    @pytest.mark.asyncio
    async def test_reassignment_updates_tenant_tier_id(self) -> None:
        """A genuine (different-tier) reassignment updates tenants.tier_id —
        this is now the ONLY write assign_tenant_tier makes; no second table
        to also write through to."""
        old_tier_id, new_tier_id = uuid4(), uuid4()
        tenant = _tenant(tier_id=old_tier_id)
        svc = _svc()
        svc._tenants.get_by_id_for_update = AsyncMock(return_value=tenant)
        svc._tenants.update = AsyncMock()
        svc._tenants.save_and_refresh = AsyncMock()
        tier_row = MagicMock(id=new_tier_id)
        tier_row.name = "Platinum"
        db = _core_db(tier_row=[tier_row])  # only the tier lookup

        result = await svc.assign_tenant_tier(_admin_user(), 1, str(new_tier_id), db)

        assert result is tenant
        svc._tenants.update.assert_awaited_once()
        assert svc._tenants.update.await_args.args[1]["tier_id"] == new_tier_id
        svc._tenants.save_and_refresh.assert_awaited_once()
        # No lingering write to any platform_core_db table beyond the tier lookup.
        assert db.execute.await_count == 1
        db.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_first_assignment_updates_tenant_tier_id(self) -> None:
        """First-ever assignment (tenant.tier_id currently None) behaves the
        same as any other reassignment — no separate INSERT path needed now
        that there's only one column to write."""
        new_tier_id = uuid4()
        tenant = _tenant(tier_id=None, allocated_budget=Decimal("1000.00"))
        svc = _svc()
        svc._tenants.get_by_id_for_update = AsyncMock(return_value=tenant)
        svc._tenants.update = AsyncMock()
        svc._tenants.save_and_refresh = AsyncMock()
        tier_row = MagicMock(id=new_tier_id)
        tier_row.name = "Gold"
        db = _core_db(tier_row=[tier_row])

        await svc.assign_tenant_tier(_admin_user(), 1, str(new_tier_id), db)

        svc._tenants.update.assert_awaited_once()
        assert svc._tenants.update.await_args.args[1]["tier_id"] == new_tier_id

    @pytest.mark.asyncio
    async def test_reassignment_reconnects_quota_and_cache(self) -> None:
        """Quota flags earned under the old tier must clear, and the cached
        tier_id must be force-written to the new tier — the actual
        enforcement-path reconnection this file exists to pin, independent
        of how the tier itself is now persisted."""
        old_tier_id, new_tier_id = uuid4(), uuid4()
        tenant = _tenant(tier_id=old_tier_id)
        svc = _svc()
        svc._tenants.get_by_id_for_update = AsyncMock(return_value=tenant)
        svc._tenants.update = AsyncMock()
        svc._tenants.save_and_refresh = AsyncMock()
        tier_row = MagicMock(id=new_tier_id)
        tier_row.name = "Platinum"
        db = _core_db(tier_row=[tier_row])

        await svc.assign_tenant_tier(_admin_user(), 1, str(new_tier_id), db)

        svc._api_keys.clear_quota_flags_for_tenant.assert_awaited_once_with(1)
        svc._api_keys.set_tier_id_for_tenant.assert_awaited_once_with(1, str(new_tier_id))

    @pytest.mark.asyncio
    async def test_api_keys_service_missing_does_not_block_assignment(self) -> None:
        """Cache reconnection is best-effort-adjacent — a deployment without
        api_key_service wired up must still let the tier assignment itself
        succeed."""
        new_tier_id = uuid4()
        tenant = _tenant(tier_id=None)
        svc = _svc()
        svc._api_keys = None
        svc._tenants.get_by_id_for_update = AsyncMock(return_value=tenant)
        svc._tenants.update = AsyncMock()
        svc._tenants.save_and_refresh = AsyncMock()
        tier_row = MagicMock(id=new_tier_id)
        tier_row.name = "Gold"
        db = _core_db(tier_row=[tier_row])

        result = await svc.assign_tenant_tier(_admin_user(), 1, str(new_tier_id), db)

        assert result is tenant
        svc._tenants.update.assert_awaited_once()


class TestReviseTenantBudget:
    @pytest.mark.asyncio
    async def test_non_admin_rejected(self) -> None:
        svc = _svc(roles=["TENANT ADMIN"])
        with pytest.raises(HTTPException) as exc_info:
            await svc.revise_tenant_budget(_admin_user(), 1, "top-up", Decimal("100"), _VALID_EFFECTIVE_FROM, _VALID_EFFECTIVE_TO)
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_top_up_exceeding_ceiling_rejected(self) -> None:
        svc = _svc()
        svc._tenants.get_by_id_for_update = AsyncMock(
            return_value=_tenant(allocated_budget=Decimal("0"))
        )
        with pytest.raises(HTTPException) as exc_info:
            await svc.revise_tenant_budget(
                _admin_user(), 1, "top-up", Decimal("99999999999999.00"), _VALID_EFFECTIVE_FROM, _VALID_EFFECTIVE_TO)
        assert exc_info.value.status_code == 422
        assert exc_info.value.detail["error"] == "budget_limit_exceeded"

    @pytest.mark.asyncio
    async def test_top_down_below_zero_rejected(self) -> None:
        svc = _svc()
        svc._tenants.get_by_id_for_update = AsyncMock(
            return_value=_tenant(allocated_budget=Decimal("50"))
        )
        with pytest.raises(HTTPException) as exc_info:
            await svc.revise_tenant_budget(_admin_user(), 1, "top-down", Decimal("100"), _VALID_EFFECTIVE_FROM, _VALID_EFFECTIVE_TO)
        assert exc_info.value.status_code == 422
        assert exc_info.value.detail["error"] == "budget_negative"

    @pytest.mark.asyncio
    async def test_top_down_rejected_when_it_would_drop_below_total_spend(self) -> None:
        """Restores the check the old platform-core endpoint had — a
        top-down that would leave the tenant's budget below what its keys
        have already spent is refused outright, not just silently flagged
        exhausted after the fact."""
        svc = _svc()
        svc._tenants.get_by_id_for_update = AsyncMock(
            return_value=_tenant(allocated_budget=Decimal("1000"))
        )
        svc._tenants.update = AsyncMock()
        svc._api_keys.list_key_ids_for_tenant = AsyncMock(return_value=[10, 11])
        usage_rows = [self._usage_row(10, Decimal("400.00")), self._usage_row(11, Decimal("300.00"))]
        db = _core_db(budget_usage_rows=usage_rows)  # only the verification fetch runs

        with pytest.raises(HTTPException) as exc_info:
            # 1000 - 400 = 600, below the 700 already spent across both keys.
            await svc.revise_tenant_budget(_admin_user(), 1, "top-down", Decimal("400"), _VALID_EFFECTIVE_FROM, _VALID_EFFECTIVE_TO, db)

        assert exc_info.value.status_code == 409
        assert exc_info.value.detail["error"] == "budget_below_consumed"
        svc._tenants.update.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_top_down_allowed_when_it_stays_above_total_spend(self) -> None:
        svc = _svc()
        svc._tenants.get_by_id_for_update = AsyncMock(
            return_value=_tenant(allocated_budget=Decimal("1000"))
        )
        svc._tenants.update = AsyncMock()
        svc._api_keys.list_key_ids_for_tenant = AsyncMock(return_value=[10])
        rows = [self._usage_row(10, Decimal("300.00"))]
        db = _core_db(budget_usage_rows=[rows, rows])  # verification, then the post-commit sync

        # 1000 - 200 = 800, still above the 300 already spent.
        await svc.revise_tenant_budget(_admin_user(), 1, "top-down", Decimal("200"), _VALID_EFFECTIVE_FROM, _VALID_EFFECTIVE_TO, db)

        svc._tenants.update.assert_awaited_once()
        assert svc._tenants.update.await_args.args[1]["allocated_budget"] == Decimal("800")
        # 800 - 300 = 500 > 0 -> not tenant-exhausted -> per-key clear, not a blanket set.
        svc._api_keys.set_budget_exhausted_for_tenant.assert_not_awaited()
        svc._api_keys.set_budget_exhausted_for_keys.assert_awaited_once_with([10], False)

    @pytest.mark.asyncio
    async def test_top_down_refused_when_platform_core_db_is_none(self) -> None:
        """Unlike the post-commit sync (best-effort), the top-down gate
        itself must fail closed — an unverifiable spend figure must not
        silently let an under-provisioning top-down through."""
        svc = _svc()
        svc._tenants.get_by_id_for_update = AsyncMock(
            return_value=_tenant(allocated_budget=Decimal("1000"))
        )
        svc._tenants.update = AsyncMock()

        with pytest.raises(HTTPException) as exc_info:
            await svc.revise_tenant_budget(_admin_user(), 1, "top-down", Decimal("200"), _VALID_EFFECTIVE_FROM, _VALID_EFFECTIVE_TO, None)

        assert exc_info.value.status_code == 503
        assert exc_info.value.detail["error"] == "spend_verification_unavailable"
        svc._tenants.update.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_top_down_refused_when_api_keys_service_missing(self) -> None:
        svc = _svc()
        svc._api_keys = None
        svc._tenants.get_by_id_for_update = AsyncMock(
            return_value=_tenant(allocated_budget=Decimal("1000"))
        )
        svc._tenants.update = AsyncMock()
        db = AsyncMock()

        with pytest.raises(HTTPException) as exc_info:
            await svc.revise_tenant_budget(_admin_user(), 1, "top-down", Decimal("200"), _VALID_EFFECTIVE_FROM, _VALID_EFFECTIVE_TO, db)

        assert exc_info.value.status_code == 503
        assert exc_info.value.detail["error"] == "spend_verification_unavailable"
        svc._tenants.update.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_top_down_refused_when_spend_fetch_fails(self) -> None:
        svc = _svc()
        svc._tenants.get_by_id_for_update = AsyncMock(
            return_value=_tenant(allocated_budget=Decimal("1000"))
        )
        svc._tenants.update = AsyncMock()
        svc._api_keys.list_key_ids_for_tenant = AsyncMock(
            side_effect=RuntimeError("local DB connection lost")
        )
        db = AsyncMock()

        with pytest.raises(HTTPException) as exc_info:
            await svc.revise_tenant_budget(_admin_user(), 1, "top-down", Decimal("200"), _VALID_EFFECTIVE_FROM, _VALID_EFFECTIVE_TO, db)

        assert exc_info.value.status_code == 503
        assert exc_info.value.detail["error"] == "spend_verification_unavailable"
        svc._tenants.update.assert_not_awaited()

    @staticmethod
    def _usage_row(api_key_id: int, used: Decimal, snap: Decimal | None = None) -> MagicMock:
        row = MagicMock()
        row.api_key_id = api_key_id
        row.api_key_budget_used = used
        row.api_key_budget_snap = snap
        return row

    @pytest.mark.asyncio
    async def test_top_up_clears_flags_for_keys_not_individually_exhausted(self) -> None:
        """Closes the gap the endpoint this replaces didn't have: the
        consumer only ever posts {"exhausted": true} per key, so a key
        already flagged budget-exhausted=1 needs this call to have any path
        back. Tenant tops up to 500; total spend across its keys is 100 →
        the tenant pool isn't exhausted, so each key is cleared
        individually (asymmetric recompute — see
        _sync_ppu_wallet_and_exhaustion) rather than a tenant-wide flip."""
        svc = _svc()
        svc._tenants.get_by_id_for_update = AsyncMock(
            return_value=_tenant(allocated_budget=Decimal("0"))
        )
        svc._tenants.update = AsyncMock()
        svc._api_keys.list_key_ids_for_tenant = AsyncMock(return_value=[10, 11])
        usage_rows = [self._usage_row(10, Decimal("60.00")), self._usage_row(11, Decimal("40.00"))]
        db = _core_db(budget_usage_rows=usage_rows)

        await svc.revise_tenant_budget(_admin_user(), 1, "top-up", Decimal("500"), _VALID_EFFECTIVE_FROM, _VALID_EFFECTIVE_TO, db)

        svc._api_keys.set_budget_exhausted_for_tenant.assert_not_awaited()
        svc._api_keys.set_budget_exhausted_for_keys.assert_awaited_once_with([10, 11], False)

    @pytest.mark.asyncio
    async def test_top_up_does_not_clear_a_key_still_individually_exhausted(self) -> None:
        """Tenant pool has headroom again (topped up to 500, total spend
        100), but Key 11 is individually over its OWN ceiling (used 40 >=
        snap 30) — an independent constraint from the tenant aggregate.
        Must stay flagged; only Key 10 (not individually exhausted) clears."""
        svc = _svc()
        svc._tenants.get_by_id_for_update = AsyncMock(
            return_value=_tenant(allocated_budget=Decimal("0"))
        )
        svc._tenants.update = AsyncMock()
        svc._api_keys.list_key_ids_for_tenant = AsyncMock(return_value=[10, 11])
        usage_rows = [
            self._usage_row(10, Decimal("60.00"), snap=Decimal("100.00")),
            self._usage_row(11, Decimal("40.00"), snap=Decimal("30.00")),
        ]
        db = _core_db(budget_usage_rows=usage_rows)

        await svc.revise_tenant_budget(_admin_user(), 1, "top-up", Decimal("500"), _VALID_EFFECTIVE_FROM, _VALID_EFFECTIVE_TO, db)

        svc._api_keys.set_budget_exhausted_for_tenant.assert_not_awaited()
        svc._api_keys.set_budget_exhausted_for_keys.assert_awaited_once_with([10], False)

    @pytest.mark.asyncio
    async def test_top_down_to_zero_sets_budget_exhausted_flag(self) -> None:
        """Tenant tops down to 0 remaining allocated_budget; any spend at all
        (or none) means the tenant has nothing left → exhausted — every key
        genuinely is out of budget now, so the blanket tenant-wide set still
        applies here (see _sync_ppu_wallet_and_exhaustion's asymmetry).
        fetch_budget_usage is called twice: once by revise_tenant_budget's
        own top-down spend-verification gate (0 -> not below 0 spent, so the
        top-down is allowed), once more by the post-commit sync."""
        svc = _svc()
        svc._tenants.get_by_id_for_update = AsyncMock(
            return_value=_tenant(allocated_budget=Decimal("500"))
        )
        svc._tenants.update = AsyncMock()
        svc._api_keys.list_key_ids_for_tenant = AsyncMock(return_value=[10])
        rows = [self._usage_row(10, Decimal("0"))]
        db = _core_db(budget_usage_rows=[rows, rows])

        await svc.revise_tenant_budget(_admin_user(), 1, "top-down", Decimal("500"), _VALID_EFFECTIVE_FROM, _VALID_EFFECTIVE_TO, db)

        svc._api_keys.set_budget_exhausted_for_tenant.assert_awaited_once_with(1, True)

    @pytest.mark.asyncio
    async def test_spend_exceeding_new_allocation_sets_budget_exhausted_flag(self) -> None:
        """A tenant whose recorded spend already exceeds the freshly-set
        allocated_budget (e.g. a top-down applied after heavy usage) must
        read as exhausted, not just an exact-zero match."""
        svc = _svc()
        svc._tenants.get_by_id_for_update = AsyncMock(
            return_value=_tenant(allocated_budget=Decimal("1000"))
        )
        svc._tenants.update = AsyncMock()
        svc._api_keys.list_key_ids_for_tenant = AsyncMock(return_value=[10])
        db = _core_db(budget_usage_rows=[self._usage_row(10, Decimal("1200.00"))])

        await svc.revise_tenant_budget(_admin_user(), 1, "top-up", Decimal("0"), _VALID_EFFECTIVE_FROM, _VALID_EFFECTIVE_TO, db)

        svc._api_keys.set_budget_exhausted_for_tenant.assert_awaited_once_with(1, True)

    @pytest.mark.asyncio
    async def test_tenant_with_no_api_keys_is_not_exhausted_when_budget_positive(self) -> None:
        """A brand-new tenant with a positive allocated_budget and no keys
        yet (zero spend) must not be flagged exhausted — and with no keys to
        loop over, neither the tenant-wide nor the per-key setter has
        anything to call."""
        svc = _svc()
        svc._tenants.get_by_id_for_update = AsyncMock(
            return_value=_tenant(allocated_budget=Decimal("0"))
        )
        svc._tenants.update = AsyncMock()
        svc._api_keys.list_key_ids_for_tenant = AsyncMock(return_value=[])
        db = _core_db()  # fetch_budget_usage short-circuits on empty key_ids — no execute call

        await svc.revise_tenant_budget(_admin_user(), 1, "top-up", Decimal("500"), _VALID_EFFECTIVE_FROM, _VALID_EFFECTIVE_TO, db)

        svc._api_keys.set_budget_exhausted_for_tenant.assert_not_awaited()
        svc._api_keys.set_budget_exhausted_for_keys.assert_awaited_once_with([], False)
        db.execute.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_platform_core_db_none_still_updates_tenant_budget(self) -> None:
        """The exhaustion-flag sync is best-effort — an unconfigured/
        unreachable platform-core DB must not block the primary
        allocated_budget write."""
        svc = _svc()
        svc._tenants.get_by_id_for_update = AsyncMock(
            return_value=_tenant(allocated_budget=Decimal("0"))
        )
        svc._tenants.update = AsyncMock()

        tenant = await svc.revise_tenant_budget(
            _admin_user(), 1, "top-up", Decimal("500"), _VALID_EFFECTIVE_FROM, _VALID_EFFECTIVE_TO, None)

        svc._tenants.update.assert_awaited_once()
        assert svc._tenants.update.await_args.args[1]["allocated_budget"] == Decimal("500")
        svc._api_keys.set_budget_exhausted_for_tenant.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_budget_usage_fetch_failure_degrades_without_raising(self) -> None:
        """A platform-core outage while summing spend must not roll back the
        already-committed allocated_budget write, and must not raise past
        this method — matches the documented best-effort contract."""
        svc = _svc()
        svc._tenants.get_by_id_for_update = AsyncMock(
            return_value=_tenant(allocated_budget=Decimal("0"))
        )
        svc._tenants.update = AsyncMock()
        svc._api_keys.list_key_ids_for_tenant = AsyncMock(
            side_effect=RuntimeError("local DB connection lost")
        )
        db = AsyncMock()

        await svc.revise_tenant_budget(_admin_user(), 1, "top-up", Decimal("500"), _VALID_EFFECTIVE_FROM, _VALID_EFFECTIVE_TO, db)

        # The primary write already happened before the sync ever runs —
        # checking the call args, not tenant.allocated_budget, since
        # svc._tenants.update is mocked here and does not mutate the object
        # (unlike the real BaseRepository.update()).
        assert svc._tenants.update.await_args.args[1]["allocated_budget"] == Decimal("500")
        svc._api_keys.set_budget_exhausted_for_tenant.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_budget_usage_query_failure_does_not_clear_exhausted_flag(self) -> None:
        """Regression: unlike list_key_ids_for_tenant failing (covered by
        test_budget_usage_fetch_failure_degrades_without_raising), this is
        fetch_budget_usage's OWN query failing after key_ids was fetched
        fine. fetch_budget_usage used to swallow that and return {}, which
        is indistinguishable from "these keys genuinely have zero spend" —
        so a platform-core hiccup mid-sync computed total_spent=0,
        exhausted=False, and overwrote an over-budget tenant's
        budget-exhausted=1 flag with 0. The fix makes fetch_budget_usage
        raise here (raise_on_error=True) so this method's existing
        best-effort except catches it and skips the write instead, matching
        test_budget_usage_fetch_failure_degrades_without_raising's contract."""
        svc = _svc()
        svc._tenants.get_by_id_for_update = AsyncMock(
            return_value=_tenant(allocated_budget=Decimal("1000"))
        )
        svc._tenants.update = AsyncMock()
        svc._api_keys.list_key_ids_for_tenant = AsyncMock(return_value=[10, 11])
        db = AsyncMock()
        db.execute = AsyncMock(side_effect=RuntimeError("platform-core unreachable"))

        await svc.revise_tenant_budget(_admin_user(), 1, "top-up", Decimal("0"), _VALID_EFFECTIVE_FROM, _VALID_EFFECTIVE_TO, db)

        assert svc._tenants.update.await_args.args[1]["allocated_budget"] == Decimal("1000")
        svc._api_keys.set_budget_exhausted_for_tenant.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_api_keys_service_missing_skips_sync_without_error(self) -> None:
        """A deployment without api_key_service wired up must still let the
        budget revision itself succeed."""
        svc = _svc()
        svc._api_keys = None
        svc._tenants.get_by_id_for_update = AsyncMock(
            return_value=_tenant(allocated_budget=Decimal("0"))
        )
        svc._tenants.update = AsyncMock()
        db = AsyncMock()

        await svc.revise_tenant_budget(_admin_user(), 1, "top-up", Decimal("500"), _VALID_EFFECTIVE_FROM, _VALID_EFFECTIVE_TO, db)

        assert svc._tenants.update.await_args.args[1]["allocated_budget"] == Decimal("500")
        db.execute.assert_not_awaited()


class TestReviseTenantBudgetCascade:
    """A tenant budget revision proportionally cascades into every
    Application under it (and, for one whose own amount changes, its own
    Keys in turn) via AllocationService.cascade_tenant_budget_revision —
    the same resolve_level algorithm the Budget Allocation endpoints use,
    not a separate implementation. These tests treat the cascade itself as
    already covered by test_allocation_service.py and focus on
    revise_tenant_budget's own contract with it: it's called with the
    right arguments before anything commits, its counts flow through to
    the response, and a failure anywhere in it rejects the WHOLE revision
    — including the Tenant's own allocated_budget change — not just the
    piece that broke."""

    @pytest.mark.asyncio
    async def test_allocation_service_missing_fails_closed(self) -> None:
        """Same fail-closed reasoning as the top-down spend gate: an
        un-cascade-able revision must not silently leave Applications/Keys
        out of sync with the Tenant's new total."""
        svc = _svc()
        svc._allocations = None
        svc._tenants.get_by_id_for_update = AsyncMock(
            return_value=_tenant(allocated_budget=Decimal("0"))
        )
        svc._tenants.update = AsyncMock()

        with pytest.raises(HTTPException) as exc_info:
            await svc.revise_tenant_budget(_admin_user(), 1, "top-up", Decimal("500"), _VALID_EFFECTIVE_FROM, _VALID_EFFECTIVE_TO)

        assert exc_info.value.status_code == 503
        assert exc_info.value.detail["error"] == "allocation_cascade_unavailable"
        svc._tenants.update.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_cascade_invoked_with_the_new_amount_before_commit(self) -> None:
        """Verifies the cascade sees new_budget (the ONLY amount it takes —
        it no longer needs the Tenant's old total, since it never
        proportionally scales anything off it any more) and runs before
        the Tenant's own row is staged, so its side effects are part of
        the same not-yet-committed transaction."""
        allocation_service = AsyncMock()
        allocation_service.cascade_tenant_budget_revision = AsyncMock(
            return_value=(2, 3, {7: Decimal("40.00")})
        )
        svc = _svc(allocation_service=allocation_service)
        svc._tenants.get_by_id_for_update = AsyncMock(
            return_value=_tenant(allocated_budget=Decimal("1000"))
        )
        svc._tenants.update = AsyncMock()

        await svc.revise_tenant_budget(_admin_user(), 1, "top-up", Decimal("500"), _VALID_EFFECTIVE_FROM, _VALID_EFFECTIVE_TO)

        allocation_service.cascade_tenant_budget_revision.assert_awaited_once_with(
            1, Decimal("1500"), ANY, None
        )
        svc._tenants.update.assert_awaited_once()
        assert svc._tenants.update.await_args.args[1]["allocated_budget"] == Decimal("1500")

    @pytest.mark.asyncio
    async def test_increase_cascade_counts_flow_into_the_response(self) -> None:
        """A top-up that proportionally grows N Applications and M of their
        Keys reports those exact counts back, not hardcoded None/0."""
        allocation_service = AsyncMock()
        allocation_service.cascade_tenant_budget_revision = AsyncMock(
            return_value=(3, 5, {})
        )
        svc = _svc(allocation_service=allocation_service)
        svc._tenants.get_by_id_for_update = AsyncMock(
            return_value=_tenant(allocated_budget=Decimal("1000"))
        )
        svc._tenants.update = AsyncMock()

        tenant, applications_recomputed, keys_recomputed, snapshot_write_failed = (
            await svc.revise_tenant_budget(_admin_user(), 1, "top-up", Decimal("500"), _VALID_EFFECTIVE_FROM, _VALID_EFFECTIVE_TO)
        )

        assert (applications_recomputed, keys_recomputed) == (3, 5)
        assert snapshot_write_failed is False

    @pytest.mark.asyncio
    async def test_decrease_cascade_counts_flow_into_the_response(self) -> None:
        """Same as the increase case, for a top-down that stays above total
        spend and so is allowed through to the cascade."""
        allocation_service = AsyncMock()
        allocation_service.cascade_tenant_budget_revision = AsyncMock(
            return_value=(2, 4, {})
        )
        svc = _svc(allocation_service=allocation_service)
        svc._tenants.get_by_id_for_update = AsyncMock(
            return_value=_tenant(allocated_budget=Decimal("1000"))
        )
        svc._tenants.update = AsyncMock()
        svc._api_keys.list_key_ids_for_tenant = AsyncMock(return_value=[10])
        rows = [TestReviseTenantBudget._usage_row(10, Decimal("100.00"))]
        db = _core_db(budget_usage_rows=[rows, rows])

        tenant, applications_recomputed, keys_recomputed, snapshot_write_failed = (
            await svc.revise_tenant_budget(_admin_user(), 1, "top-down", Decimal("200"), _VALID_EFFECTIVE_FROM, _VALID_EFFECTIVE_TO, db)
        )

        assert (applications_recomputed, keys_recomputed) == (2, 4)
        assert snapshot_write_failed is False
        assert svc._tenants.update.await_args.args[1]["allocated_budget"] == Decimal("800")

    @pytest.mark.asyncio
    async def test_decrease_pushing_a_descendant_below_spend_rejects_the_whole_revision(
        self,
    ) -> None:
        """If the cascade finds that squeezing the Tenant's total would push
        some Application or Key below what it's already spent, resolve_level
        raises out of cascade_tenant_budget_revision before this method ever
        stages the Tenant's own allocated_budget change — so that change
        never happens either. Nothing here explicitly rolls the Tenant row
        back; the point is svc._tenants.update is simply never reached, and
        it's the session-level rollback (on the real DB session, outside
        this unit test's mocks) that discards the cascade's own staged
        writes together with it — this test verifies the ordering that
        makes that guarantee possible, not the DB rollback itself."""
        allocation_service = AsyncMock()
        allocation_service.cascade_tenant_budget_revision = AsyncMock(
            side_effect=ValidationError(
                message="Application 9 would drop to 40.00, below its consumed 55.00.",
                code="ALLOCATION_BELOW_CONSUMED",
            )
        )
        svc = _svc(allocation_service=allocation_service)
        svc._tenants.get_by_id_for_update = AsyncMock(
            return_value=_tenant(allocated_budget=Decimal("1000"))
        )
        svc._tenants.update = AsyncMock()
        svc._api_keys.list_key_ids_for_tenant = AsyncMock(return_value=[10])
        rows = [TestReviseTenantBudget._usage_row(10, Decimal("100.00"))]
        db = _core_db(budget_usage_rows=rows)  # only the pre-cascade spend-verification fetch runs

        with pytest.raises(ValidationError):
            await svc.revise_tenant_budget(_admin_user(), 1, "top-down", Decimal("200"), _VALID_EFFECTIVE_FROM, _VALID_EFFECTIVE_TO, db)

        svc._tenants.update.assert_not_awaited()
        svc._tenants.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_snapshot_write_failure_is_surfaced_not_silent(self) -> None:
        """The revision itself (Tenant + cascade) already committed by the
        time write_budget_snapshot runs — its failure must NOT roll back
        or re-raise (budget_usage.api_key_budget_snap is a best-effort
        cache, not the ceiling's source of truth), but it also must not
        be purely a log line: snapshot_write_failed=True on the response
        is what lets a caller tell "the revision succeeded but the ledger
        cache is briefly behind" apart from a fully-successful response."""
        allocation_service = AsyncMock()
        allocation_service.cascade_tenant_budget_revision = AsyncMock(
            return_value=(2, 3, {11: Decimal("5000.00")})
        )
        svc = _svc(allocation_service=allocation_service)
        svc._tenants.get_by_id_for_update = AsyncMock(
            return_value=_tenant(allocated_budget=Decimal("1000"))
        )
        svc._tenants.update = AsyncMock()

        with patch(
            "app.services.tenant_service.write_budget_snapshot", AsyncMock(return_value=False)
        ):
            tenant, applications_recomputed, keys_recomputed, snapshot_write_failed = (
                await svc.revise_tenant_budget(_admin_user(), 1, "top-up", Decimal("500"), _VALID_EFFECTIVE_FROM, _VALID_EFFECTIVE_TO)
            )

        # The revision itself still fully succeeded — not rolled back, not
        # re-raised — despite the snapshot mirror failing.
        svc._tenants.update.assert_awaited_once()
        svc._tenants.commit.assert_awaited_once()
        assert (applications_recomputed, keys_recomputed) == (2, 3)
        assert snapshot_write_failed is True


class TestReviseTenantBudgetEffectiveWindow:
    """These tests all exercise the tenant's window being ABSENT (the
    `_tenant()` fixture never sets budget_effective_to) — so every call
    here lands in revise_tenant_budget's "no window yet" branch, requiring
    both dates and validating From against today
    (_validate_new_effective_from) and To against From
    (_validate_effective_to_after_from). See TestReviseTenantBudgetLocking
    below for the ACTIVE-window branch (From locked, To extend-only).

    Before any of this, the ONLY place these fields could ever be set was
    tenant creation (TenantCreate), with zero validation and no way to
    correct or renew them afterwards — a tenant created with, say, a
    same-day From/To, or one whose window has since expired, had no path
    back to a sane window short of a raw DB edit. These tests cover that
    gap directly, not a simplified stand-in for it.
    """

    @pytest.mark.asyncio
    async def test_effective_from_before_today_rejected(self) -> None:
        """The concrete failing scenario this closes: an admin resubmits
        yesterday's date (e.g. a stale form, or a client in a
        behind-UTC timezone that computed "today" wrong) as From — must be
        rejected, not silently persisted as an already-expired window."""
        svc = _svc()
        svc._tenants.get_by_id_for_update = AsyncMock(
            return_value=_tenant(allocated_budget=Decimal("100"))
        )
        yesterday = _VALID_EFFECTIVE_FROM - timedelta(days=1)

        with pytest.raises(HTTPException) as exc_info:
            await svc.revise_tenant_budget(
                _admin_user(), 1, "top-up", Decimal("100"), yesterday, yesterday + timedelta(days=30)
            )

        assert exc_info.value.status_code == 422
        assert exc_info.value.detail["error"] == "budget_effective_from_invalid"
        # Validated right after the tenant is loaded — the tenant row is now
        # needed first (to see whether a window is already active, which
        # decides what's even required), unlike the top-down spend gate
        # elsewhere in this method, which stays purely request-local.
        svc._tenants.get_by_id_for_update.assert_awaited_once()
        svc._tenants.update.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_effective_to_same_calendar_day_as_from_rejected(self) -> None:
        """The other concrete failing scenario: a caller passes From/To on
        the same date (or To before From) — e.g. a UI bug that defaults
        both date pickers to "today". Must be rejected as too narrow a
        window, not accepted as a zero/negative-length one."""
        svc = _svc()
        svc._tenants.get_by_id_for_update = AsyncMock(
            return_value=_tenant(allocated_budget=Decimal("100"))
        )
        same_day_to = _VALID_EFFECTIVE_FROM.replace(hour=23, minute=59)

        with pytest.raises(HTTPException) as exc_info:
            await svc.revise_tenant_budget(
                _admin_user(), 1, "top-up", Decimal("100"), _VALID_EFFECTIVE_FROM, same_day_to
            )

        assert exc_info.value.status_code == 422
        assert exc_info.value.detail["error"] == "budget_effective_to_invalid"
        svc._tenants.update.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_effective_to_exactly_one_day_after_from_allowed(self) -> None:
        """Boundary: "at least one calendar day after" must accept exactly
        one day, not reject it off-by-one."""
        svc = _svc()
        svc._tenants.get_by_id_for_update = AsyncMock(
            return_value=_tenant(allocated_budget=Decimal("100"))
        )
        svc._tenants.update = AsyncMock()
        from_dt = _VALID_EFFECTIVE_FROM
        to_dt = from_dt + timedelta(days=1)

        await svc.revise_tenant_budget(_admin_user(), 1, "top-up", Decimal("100"), from_dt, to_dt)

        svc._tenants.update.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_effective_window_persisted_alongside_allocated_budget(self) -> None:
        """The revised window must actually be written, not just
        validated-and-discarded."""
        svc = _svc()
        svc._tenants.get_by_id_for_update = AsyncMock(
            return_value=_tenant(allocated_budget=Decimal("100"))
        )
        svc._tenants.update = AsyncMock()
        from_dt = _VALID_EFFECTIVE_FROM
        to_dt = _VALID_EFFECTIVE_TO

        await svc.revise_tenant_budget(_admin_user(), 1, "top-up", Decimal("100"), from_dt, to_dt)

        written = svc._tenants.update.await_args.args[1]
        assert written["budget_effective_from"] == from_dt
        assert written["budget_effective_to"] == to_dt

    @pytest.mark.asyncio
    async def test_renewing_an_already_expired_window_succeeds(self) -> None:
        """End-to-end version of the real-world gap: a tenant whose budget
        window already lapsed (budget_effective_to in the past) previously
        had no endpoint that could ever move that date — revise_tenant_budget
        only ever touched allocated_budget. An admin renewing the tenant now
        does it in the same top-up call, and the new window replaces the
        expired one."""
        expired_tenant = _tenant(allocated_budget=Decimal("100"))
        expired_tenant.budget_effective_from = _VALID_EFFECTIVE_FROM - timedelta(days=60)
        expired_tenant.budget_effective_to = _VALID_EFFECTIVE_FROM - timedelta(days=1)
        svc = _svc()
        svc._tenants.get_by_id_for_update = AsyncMock(return_value=expired_tenant)
        svc._tenants.update = AsyncMock()
        new_from = _VALID_EFFECTIVE_FROM
        new_to = _VALID_EFFECTIVE_TO

        await svc.revise_tenant_budget(_admin_user(), 1, "top-up", Decimal("500"), new_from, new_to)

        written = svc._tenants.update.await_args.args[1]
        assert written["budget_effective_from"] == new_from
        assert written["budget_effective_to"] == new_to
        assert written["allocated_budget"] == Decimal("600")

    @pytest.mark.asyncio
    async def test_naive_datetime_treated_as_utc_not_local(self) -> None:
        """A naive (no tzinfo) From/To — e.g. a client that stripped the
        offset — must be compared as UTC, matching the field's documented
        contract, not silently reinterpreted as local time (which would
        make the from/to check pass or fail differently depending on the
        server's own timezone)."""
        svc = _svc()
        svc._tenants.get_by_id_for_update = AsyncMock(
            return_value=_tenant(allocated_budget=Decimal("100"))
        )
        svc._tenants.update = AsyncMock()
        naive_from = datetime.now(timezone.utc).replace(tzinfo=None)
        naive_to = naive_from + timedelta(days=1)

        await svc.revise_tenant_budget(_admin_user(), 1, "top-up", Decimal("100"), naive_from, naive_to)

        svc._tenants.update.assert_awaited_once()


def _tenant_with_active_window(*, allocated_budget=None) -> Tenant:
    tenant = _tenant(allocated_budget=allocated_budget)
    tenant.budget_effective_from = _VALID_EFFECTIVE_FROM - timedelta(days=10)
    tenant.budget_effective_to = _VALID_EFFECTIVE_FROM + timedelta(days=10)
    return tenant


class TestReviseTenantBudgetLocking:
    """The ACTIVE-window branch: budget_effective_from is locked once a
    window is live (AI4IDS-2995: "Effective From is locked and cannot be
    edited"), budget_effective_to is optional and extend-only, and — the
    exact bug this closes — omitting both must still work as a plain
    amount top-up/top-down, since that's literally what the shipped UI
    (frontend/simple-ui's adjustTenantBudget) sends today: only
    {action, amount}, never any date. Requiring both unconditionally would
    422 every existing top-up/top-down the moment this deployed."""

    @pytest.mark.asyncio
    async def test_supplying_effective_from_while_window_active_is_rejected(self) -> None:
        svc = _svc()
        svc._tenants.get_by_id_for_update = AsyncMock(
            return_value=_tenant_with_active_window(allocated_budget=Decimal("100"))
        )

        with pytest.raises(HTTPException) as exc_info:
            await svc.revise_tenant_budget(
                _admin_user(), 1, "top-up", Decimal("100"), _VALID_EFFECTIVE_FROM, _VALID_EFFECTIVE_TO
            )

        assert exc_info.value.status_code == 422
        assert exc_info.value.detail["error"] == "effective_from_locked"
        svc._tenants.update.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_plain_amount_change_with_both_dates_omitted_leaves_window_untouched(self) -> None:
        """THE exact bug scenario: the shipped frontend's adjustTenantBudget
        sends only {action, amount} — this must keep working unchanged
        once the fields are required-on-some-tenants, not 422 every
        existing top-up/top-down on deploy."""
        tenant = _tenant_with_active_window(allocated_budget=Decimal("100"))
        svc = _svc()
        svc._tenants.get_by_id_for_update = AsyncMock(return_value=tenant)
        svc._tenants.update = AsyncMock()

        await svc.revise_tenant_budget(_admin_user(), 1, "top-up", Decimal("50"))

        written = svc._tenants.update.await_args.args[1]
        assert written["allocated_budget"] == Decimal("150")
        assert written["budget_effective_from"] == tenant.budget_effective_from
        assert written["budget_effective_to"] == tenant.budget_effective_to

    @pytest.mark.asyncio
    async def test_extending_effective_to_while_from_omitted_is_allowed(self) -> None:
        tenant = _tenant_with_active_window(allocated_budget=Decimal("100"))
        svc = _svc()
        svc._tenants.get_by_id_for_update = AsyncMock(return_value=tenant)
        svc._tenants.update = AsyncMock()
        extended_to = tenant.budget_effective_to + timedelta(days=30)

        await svc.revise_tenant_budget(
            _admin_user(), 1, "top-up", Decimal("100"), budget_effective_to=extended_to
        )

        written = svc._tenants.update.await_args.args[1]
        assert written["budget_effective_from"] == tenant.budget_effective_from
        assert written["budget_effective_to"] == extended_to

    @pytest.mark.asyncio
    async def test_extended_to_validated_against_stored_from_not_todays_date(self) -> None:
        """The From used for the "at least one calendar day after" check
        must be the STORED From (set up to 10 days ago here), not a
        newly-supplied one — there isn't one, since From is locked. A To
        just one day after the stored From must be accepted even though
        it's not one day after "today"."""
        tenant = _tenant_with_active_window(allocated_budget=Decimal("100"))
        svc = _svc()
        svc._tenants.get_by_id_for_update = AsyncMock(return_value=tenant)
        svc._tenants.update = AsyncMock()
        to_just_after_stored_from = tenant.budget_effective_from + timedelta(days=1)

        await svc.revise_tenant_budget(
            _admin_user(), 1, "top-up", Decimal("100"), budget_effective_to=to_just_after_stored_from
        )

        svc._tenants.update.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_extension_still_validated_against_stored_from(self) -> None:
        """A To that fails the calendar-day check against the stored From
        (same day) is still rejected, even though no new From was given."""
        tenant = _tenant_with_active_window(allocated_budget=Decimal("100"))
        svc = _svc()
        svc._tenants.get_by_id_for_update = AsyncMock(return_value=tenant)
        same_day_as_stored_from = tenant.budget_effective_from.replace(hour=23, minute=59)

        with pytest.raises(HTTPException) as exc_info:
            await svc.revise_tenant_budget(
                _admin_user(), 1, "top-up", Decimal("100"), budget_effective_to=same_day_as_stored_from
            )

        assert exc_info.value.status_code == 422
        assert exc_info.value.detail["error"] == "budget_effective_to_invalid"
        svc._tenants.update.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_both_omitted_when_no_window_exists_is_rejected(self) -> None:
        """No window at all (never assigned, or lapsed) and nothing
        supplied — this can't be a plain amount change, since there's no
        existing window to leave "untouched"."""
        svc = _svc()
        svc._tenants.get_by_id_for_update = AsyncMock(
            return_value=_tenant(allocated_budget=Decimal("100"))
        )

        with pytest.raises(HTTPException) as exc_info:
            await svc.revise_tenant_budget(_admin_user(), 1, "top-up", Decimal("100"))

        assert exc_info.value.status_code == 422
        assert exc_info.value.detail["error"] == "effective_window_required"
        svc._tenants.update.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_only_one_field_given_when_no_window_exists_is_rejected(self) -> None:
        """Partial isn't allowed when there's nothing to fall back to —
        giving only To (or only From) with no existing window must not
        silently pick a default for the other one."""
        svc = _svc()
        svc._tenants.get_by_id_for_update = AsyncMock(
            return_value=_tenant(allocated_budget=Decimal("100"))
        )

        with pytest.raises(HTTPException) as exc_info:
            await svc.revise_tenant_budget(
                _admin_user(), 1, "top-up", Decimal("100"), budget_effective_to=_VALID_EFFECTIVE_TO
            )

        assert exc_info.value.status_code == 422
        assert exc_info.value.detail["error"] == "effective_window_required"

    @pytest.mark.asyncio
    async def test_renewing_after_expiry_is_treated_as_a_fresh_assignment_not_locked(self) -> None:
        """Ties back to TestReviseTenantBudgetEffectiveWindow's
        test_renewing_an_already_expired_window_succeeds, from the locking
        angle specifically: a LAPSED window (not merely "has some From/To
        on file") does not count as "active", so From is open again here —
        confirms the lock is tied to the window's liveness, not to whether
        the fields have ever been set at all."""
        expired_tenant = _tenant(allocated_budget=Decimal("100"))
        expired_tenant.budget_effective_from = _VALID_EFFECTIVE_FROM - timedelta(days=240)
        expired_tenant.budget_effective_to = _VALID_EFFECTIVE_FROM - timedelta(days=180)
        svc = _svc()
        svc._tenants.get_by_id_for_update = AsyncMock(return_value=expired_tenant)
        svc._tenants.update = AsyncMock()

        await svc.revise_tenant_budget(
            _admin_user(), 1, "top-up", Decimal("1200"), _VALID_EFFECTIVE_FROM, _VALID_EFFECTIVE_TO
        )

        written = svc._tenants.update.await_args.args[1]
        assert written["budget_effective_from"] == _VALID_EFFECTIVE_FROM
        assert written["budget_effective_to"] == _VALID_EFFECTIVE_TO


class TestSyncBudgetEffectiveToCache:
    """TenantService.sync_budget_effective_to_cache — force-pushes
    tenants.budget_effective_to (the raw date, not a computed boolean) onto
    every cached API key for the tenant via APIKeyService.
    set_budget_effective_to_for_tenant. The only caller is
    revise_tenant_budget (covered separately below, in
    TestReviseTenantBudgetSyncsCache) — this class covers the method
    directly."""

    @pytest.mark.asyncio
    async def test_pushes_the_tenants_stored_effective_to(self) -> None:
        svc = _svc()
        tenant = _tenant()
        tenant.budget_effective_to = _VALID_EFFECTIVE_TO
        svc._tenants.get_by_id = AsyncMock(return_value=tenant)

        result = await svc.sync_budget_effective_to_cache(1)

        assert result == _VALID_EFFECTIVE_TO
        svc._api_keys.set_budget_effective_to_for_tenant.assert_awaited_once_with(1, _VALID_EFFECTIVE_TO)

    @pytest.mark.asyncio
    async def test_no_effective_to_pushes_none(self) -> None:
        svc = _svc()
        tenant = _tenant()
        tenant.budget_effective_to = None
        svc._tenants.get_by_id = AsyncMock(return_value=tenant)

        result = await svc.sync_budget_effective_to_cache(1)

        assert result is None
        svc._api_keys.set_budget_effective_to_for_tenant.assert_awaited_once_with(1, None)

    @pytest.mark.asyncio
    async def test_unknown_tenant_is_a_noop(self) -> None:
        svc = _svc()
        svc._tenants.get_by_id = AsyncMock(return_value=None)

        result = await svc.sync_budget_effective_to_cache(999)

        assert result is None
        svc._api_keys.set_budget_effective_to_for_tenant.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_missing_api_key_service_skips_without_even_loading_the_tenant(self) -> None:
        svc = _svc()
        svc._api_keys = None
        svc._tenants.get_by_id = AsyncMock(return_value=_tenant())

        result = await svc.sync_budget_effective_to_cache(1)

        assert result is None
        svc._tenants.get_by_id.assert_not_awaited()


class TestReviseTenantBudgetSyncsCache:
    """revise_tenant_budget calls sync_budget_effective_to_cache right
    after persisting the new window — without this, revise_tenant_budget
    changes tenants.budget_effective_to directly without touching any
    api_key row, so an already-cached key would never see the new date
    until something unrelated (a rename, a tier reassignment) happened to
    rebuild its cache."""

    @pytest.mark.asyncio
    async def test_revision_pushes_the_new_effective_to_to_the_cache(self) -> None:
        svc = _svc()
        svc._tenants.get_by_id_for_update = AsyncMock(
            return_value=_tenant(allocated_budget=Decimal("100"))
        )
        svc._tenants.update = AsyncMock()
        revised_tenant = _tenant(allocated_budget=Decimal("600"))
        revised_tenant.budget_effective_to = _VALID_EFFECTIVE_TO
        svc._tenants.get_by_id = AsyncMock(return_value=revised_tenant)

        await svc.revise_tenant_budget(
            _admin_user(), 1, "top-up", Decimal("500"), _VALID_EFFECTIVE_FROM, _VALID_EFFECTIVE_TO
        )

        svc._api_keys.set_budget_effective_to_for_tenant.assert_awaited_once_with(1, _VALID_EFFECTIVE_TO)

    @pytest.mark.asyncio
    async def test_sync_failure_does_not_roll_back_the_revision(self) -> None:
        """Best-effort, same as the wallet/exhaustion sync it sits next to —
        the Tenant row already committed by the time this runs, so a
        failure here must degrade to a stale cached date, not undo the
        revision or raise past this method."""
        svc = _svc()
        svc._tenants.get_by_id_for_update = AsyncMock(
            return_value=_tenant(allocated_budget=Decimal("100"))
        )
        svc._tenants.update = AsyncMock()
        svc._tenants.get_by_id = AsyncMock(side_effect=RuntimeError("auth DB connection lost"))

        await svc.revise_tenant_budget(
            _admin_user(), 1, "top-up", Decimal("500"), _VALID_EFFECTIVE_FROM, _VALID_EFFECTIVE_TO
        )

        svc._tenants.update.assert_awaited_once()
        svc._tenants.commit.assert_awaited_once()


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
        """The existence check must apply the same status = 'ACTIVE' filter
        assign_tenant_tier uses — otherwise a tier listable here could be
        rejected as not-found by assign, a visible inconsistency."""
        svc = _svc()
        db = _core_db(tier_row=None)  # status filter excludes inactive tiers
        with pytest.raises(HTTPException) as exc_info:
            await svc.list_tenant_tiers(_admin_user(), str(uuid4()), db)
        assert exc_info.value.status_code == 404
        query_sql = str(db.execute.await_args_list[0].args[0])
        assert "status = 'ACTIVE'" in query_sql

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
