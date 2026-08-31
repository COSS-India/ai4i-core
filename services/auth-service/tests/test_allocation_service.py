"""AllocationService — the orchestrator behind PUT /auth/allocations.

allocation_validator's own math is covered exhaustively in
test_allocation_validator.py; these tests focus on orchestration: scope
authorization, which repository gets locked, request-shape rejections
(ROW_SCOPE_MISMATCH / KEY_APPLICATION_MISMATCH), persistence of resolved
rows, the Application -> its own Keys cascade, and the budget_usage
write-through.
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
    AllocationUpdateRequest,
    APIKeyAllocationInput,
    ApplicationAllocationInput,
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


def _key(id_, application_id, *, allocated_budget, allocated_percentage) -> APIKey:
    return APIKey(
        id=id_, application_id=application_id, key_name=f"Key{id_}", api_key=uuid4().hex,
        allocated_budget=allocated_budget, allocated_percentage=allocated_percentage,
    )


def _svc(*, roles=("ADMIN",)) -> AllocationService:
    svc = AllocationService(
        application_repo=AsyncMock(),
        api_key_repo=AsyncMock(),
        tenant_repo=AsyncMock(),
        role_repo=AsyncMock(),
        db=AsyncMock(),
        api_key_service=AsyncMock(),
    )
    svc._roles.get_user_roles = AsyncMock(return_value=list(roles))
    return svc


# The acceptance-criteria worked example, reused across several tests:
# App A=50%/50000 (40000 used), App B=30%/30000 (30000 used, exhausted),
# App C=20%/20000 (5000 used).
def _three_apps():
    return [
        _application(1, allocated_budget=Decimal("50000"), allocated_percentage=Decimal("50")),
        _application(2, allocated_budget=Decimal("30000"), allocated_percentage=Decimal("30")),
        _application(3, allocated_budget=Decimal("20000"), allocated_percentage=Decimal("20")),
    ]


def _usage_side_effect(used_by_key: dict[int, Decimal]):
    async def _fetch(key_ids, platform_core_db):
        return {kid: (used_by_key[kid], None) for kid in key_ids if kid in used_by_key}
    return _fetch


class TestTenantScopeAuthAndShape:
    @pytest.mark.asyncio
    async def test_no_qualifying_role_rejected(self) -> None:
        svc = _svc(roles=["MODERATOR"])
        body = AllocationUpdateRequest(application_allocations=[
            ApplicationAllocationInput(application_id=1, allocated_percentage=Decimal("45"))
        ])
        with pytest.raises(HTTPException) as exc:
            await svc.update_tenant_application_allocations(101, body, _user(), None)
        assert exc.value.status_code == 403

    @pytest.mark.asyncio
    async def test_tenant_admin_of_different_tenant_masked_404(self) -> None:
        svc = _svc(roles=["TENANT ADMIN"])
        body = AllocationUpdateRequest(application_allocations=[
            ApplicationAllocationInput(application_id=1, allocated_percentage=Decimal("45"))
        ])
        with pytest.raises(HTTPException) as exc:
            await svc.update_tenant_application_allocations(101, body, _user(tenant_id=999), None)
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_api_key_allocations_at_tenant_scope_rejected(self) -> None:
        svc = _svc()
        body = AllocationUpdateRequest(api_key_allocations=[
            APIKeyAllocationInput(api_key_id=1, allocated_percentage=Decimal("50"))
        ])
        with pytest.raises(ValidationError) as exc:
            await svc.update_tenant_application_allocations(101, body, _user(), None)
        assert exc.value.code == "ROW_SCOPE_MISMATCH"

    @pytest.mark.asyncio
    async def test_empty_application_allocations_rejected(self) -> None:
        svc = _svc()
        body = AllocationUpdateRequest(application_allocations=[])
        with pytest.raises(ValidationError) as exc:
            await svc.update_tenant_application_allocations(101, body, _user(), None)
        assert exc.value.code == "ROW_SCOPE_MISMATCH"

    @pytest.mark.asyncio
    async def test_tenant_not_found(self) -> None:
        svc = _svc()
        svc._tenants.get_by_id_for_update = AsyncMock(return_value=None)
        body = AllocationUpdateRequest(application_allocations=[
            ApplicationAllocationInput(application_id=1, allocated_percentage=Decimal("45"))
        ])
        with pytest.raises(EntityNotFoundError):
            await svc.update_tenant_application_allocations(101, body, _user(), None)

    @pytest.mark.asyncio
    async def test_tenant_with_no_budget_set_rejected(self) -> None:
        svc = _svc()
        svc._tenants.get_by_id_for_update = AsyncMock(return_value=_tenant(allocated_budget=None))
        body = AllocationUpdateRequest(application_allocations=[
            ApplicationAllocationInput(application_id=1, allocated_percentage=Decimal("45"))
        ])
        with pytest.raises(ValidationError) as exc:
            await svc.update_tenant_application_allocations(101, body, _user(), None)
        assert exc.value.code == "TENANT_BUDGET_NOT_SET"


class TestTenantScopeResolution:
    @pytest.mark.asyncio
    async def test_reduce_a_to_45_percent_allowed_siblings_untouched_in_response(self) -> None:
        svc = _svc()
        svc._tenants.get_by_id_for_update = AsyncMock(return_value=_tenant())
        apps = _three_apps()
        svc._applications.list_by_tenant = AsyncMock(return_value=apps)
        svc._applications.update = AsyncMock()
        svc._applications.sum_allocated_percentage = AsyncMock(return_value=Decimal("95"))
        svc._api_keys.list_by_applications = AsyncMock(return_value=[])

        body = AllocationUpdateRequest(application_allocations=[
            ApplicationAllocationInput(application_id=1, allocated_percentage=Decimal("45"))
        ])
        with patch("app.services.budget_usage.fetch_budget_usage", AsyncMock(return_value={})), \
             patch("app.services.budget_usage.write_budget_snapshot", AsyncMock()) as write_snap:
            data = await svc.update_tenant_application_allocations(101, body, _user(), None)

        assert [row.application_id for row in data.application_allocations] == [1]
        assert data.application_allocations[0].allocated_budget == Decimal("45000.00")
        svc._applications.update.assert_awaited_once()
        write_snap.assert_awaited_once_with({}, None)
        svc._db.commit.assert_awaited_once()
        # The listed Application (id=1) is locked before its Keys are read —
        # same lock create_api_key takes, so a concurrent key create under it
        # can't slip in between this call's read and write.
        svc._applications.get_by_id_for_update.assert_awaited_once_with(1)

    @pytest.mark.asyncio
    async def test_only_listed_applications_are_locked(self) -> None:
        """Apps 2 and 3 aren't mentioned in the request — no reason to take a
        row lock on them; only the explicitly listed App 1 is locked."""
        svc = _svc()
        svc._tenants.get_by_id_for_update = AsyncMock(return_value=_tenant())
        apps = _three_apps()
        svc._applications.list_by_tenant = AsyncMock(return_value=apps)
        svc._applications.update = AsyncMock()
        svc._applications.sum_allocated_percentage = AsyncMock(return_value=Decimal("95"))
        svc._api_keys.list_by_applications = AsyncMock(return_value=[])

        body = AllocationUpdateRequest(application_allocations=[
            ApplicationAllocationInput(application_id=1, allocated_percentage=Decimal("45"))
        ])
        with patch("app.services.budget_usage.fetch_budget_usage", AsyncMock(return_value={})), \
             patch("app.services.budget_usage.write_budget_snapshot", AsyncMock()):
            await svc.update_tenant_application_allocations(101, body, _user(), None)

        locked_ids = [call.args[0] for call in svc._applications.get_by_id_for_update.await_args_list]
        assert locked_ids == [1]

    @pytest.mark.asyncio
    async def test_reduce_fully_exhausted_app_b_blocked(self) -> None:
        svc = _svc()
        svc._tenants.get_by_id_for_update = AsyncMock(return_value=_tenant())
        apps = _three_apps()
        keys = [_key(21, 2, allocated_budget=Decimal("30000"), allocated_percentage=Decimal("100"))]
        svc._applications.list_by_tenant = AsyncMock(return_value=apps)
        svc._api_keys.list_by_applications = AsyncMock(return_value=keys)

        body = AllocationUpdateRequest(application_allocations=[
            ApplicationAllocationInput(application_id=2, allocated_percentage=Decimal("25"))
        ])
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
        svc._applications.list_by_tenant = AsyncMock(return_value=apps)
        svc._applications.update = AsyncMock()
        svc._applications.sum_allocated_percentage = AsyncMock(return_value=Decimal("90"))
        svc._api_keys.list_by_applications = AsyncMock(return_value=[key1, key2])
        svc._api_keys.update = AsyncMock()

        body = AllocationUpdateRequest(application_allocations=[
            ApplicationAllocationInput(application_id=1, allocated_budget=Decimal("40000"))
        ])
        with patch("app.services.budget_usage.fetch_budget_usage", AsyncMock(return_value={})), \
             patch("app.services.budget_usage.write_budget_snapshot", AsyncMock()) as write_snap:
            data = await svc.update_tenant_application_allocations(101, body, _user(), None)

        app_row = data.application_allocations[0]
        assert app_row.allocated_budget == Decimal("40000.00")
        key_rows = {r.api_key_id: r for r in app_row.api_key_allocations}
        assert key_rows[11].allocated_budget == Decimal("24000.00")
        assert key_rows[12].allocated_budget == Decimal("16000.00")
        assert key_rows[11].auto_refitted is True
        assert svc._api_keys.update.await_count == 2
        write_snap.assert_awaited_once()
        snapshot_arg = write_snap.await_args.args[0]
        assert snapshot_arg == {11: Decimal("24000.00"), 12: Decimal("16000.00")}

    @pytest.mark.asyncio
    async def test_unchanged_application_with_explicit_key_edits_still_cascades(self) -> None:
        """App A's own amount stays 50000 (explicit but equal to current), yet
        the caller explicitly listed api_key_allocations under it — the cascade
        must still run: explicit Key edits are never skipped just because the
        parent's own total didn't move."""
        svc = _svc()
        svc._tenants.get_by_id_for_update = AsyncMock(return_value=_tenant())
        apps = _three_apps()
        key1 = _key(11, 1, allocated_budget=Decimal("30000"), allocated_percentage=Decimal("60"))
        key2 = _key(12, 1, allocated_budget=Decimal("20000"), allocated_percentage=Decimal("40"))
        svc._applications.list_by_tenant = AsyncMock(return_value=apps)
        svc._applications.update = AsyncMock()
        svc._applications.sum_allocated_percentage = AsyncMock(return_value=Decimal("100"))
        svc._api_keys.list_by_applications = AsyncMock(return_value=[key1, key2])
        svc._api_keys.update = AsyncMock()

        body = AllocationUpdateRequest(application_allocations=[
            ApplicationAllocationInput(
                application_id=1, allocated_budget=Decimal("50000"),
                api_key_allocations=[APIKeyAllocationInput(api_key_id=11, allocated_budget=Decimal("35000"))],
            )
        ])
        with patch("app.services.budget_usage.fetch_budget_usage", AsyncMock(return_value={})), \
             patch("app.services.budget_usage.write_budget_snapshot", AsyncMock()):
            data = await svc.update_tenant_application_allocations(101, body, _user(), None)

        app_row = data.application_allocations[0]
        # App's own amount didn't change -> not persisted via _applications.update
        svc._applications.update.assert_not_awaited()
        key_rows = {r.api_key_id: r for r in app_row.api_key_allocations}
        assert key_rows[11].allocated_budget == Decimal("35000.00")
        assert key_rows[11].auto_refitted is False
        assert key_rows[12].allocated_budget == Decimal("15000.00")
        assert key_rows[12].auto_refitted is True

    @pytest.mark.asyncio
    async def test_key_application_mismatch(self) -> None:
        svc = _svc()
        svc._tenants.get_by_id_for_update = AsyncMock(return_value=_tenant())
        apps = _three_apps()
        key_under_app2 = _key(99, 2, allocated_budget=Decimal("30000"), allocated_percentage=Decimal("100"))
        svc._applications.list_by_tenant = AsyncMock(return_value=apps)
        svc._api_keys.list_by_applications = AsyncMock(return_value=[key_under_app2])
        svc._api_keys.get_by_id = AsyncMock(return_value=key_under_app2)

        body = AllocationUpdateRequest(application_allocations=[
            ApplicationAllocationInput(
                application_id=1, allocated_budget=Decimal("40000"),
                api_key_allocations=[APIKeyAllocationInput(api_key_id=99, allocated_budget=Decimal("1000"))],
            )
        ])
        with patch("app.services.budget_usage.fetch_budget_usage", AsyncMock(return_value={})):
            with pytest.raises(ValidationError) as exc:
                await svc.update_tenant_application_allocations(101, body, _user(), None)
        assert exc.value.code == "KEY_APPLICATION_MISMATCH"


class TestApplicationScope:
    @pytest.mark.asyncio
    async def test_application_allocations_at_key_scope_rejected(self) -> None:
        svc = _svc()
        body = AllocationUpdateRequest(application_allocations=[
            ApplicationAllocationInput(application_id=1, allocated_percentage=Decimal("50"))
        ])
        with pytest.raises(ValidationError) as exc:
            await svc.update_application_key_allocations(1, body, _user(), None)
        assert exc.value.code == "ROW_SCOPE_MISMATCH"

    @pytest.mark.asyncio
    async def test_application_not_found(self) -> None:
        svc = _svc()
        svc._applications.get_by_id = AsyncMock(return_value=None)
        body = AllocationUpdateRequest(api_key_allocations=[
            APIKeyAllocationInput(api_key_id=1, allocated_percentage=Decimal("50"))
        ])
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
        body = AllocationUpdateRequest(api_key_allocations=[
            APIKeyAllocationInput(api_key_id=1, allocated_percentage=Decimal("50"))
        ])
        with pytest.raises(EntityNotFoundError):
            await svc.update_application_key_allocations(1, body, _user(), None)

    @pytest.mark.asyncio
    async def test_application_with_no_budget_set_rejected(self) -> None:
        svc = _svc()
        app = _application(1, allocated_budget=None, allocated_percentage=None)
        svc._applications.get_by_id = AsyncMock(return_value=app)
        svc._applications.get_by_id_for_update = AsyncMock(return_value=app)
        body = AllocationUpdateRequest(api_key_allocations=[
            APIKeyAllocationInput(api_key_id=1, allocated_percentage=Decimal("50"))
        ])
        with pytest.raises(ValidationError) as exc:
            await svc.update_application_key_allocations(1, body, _user(), None)
        assert exc.value.code == "APPLICATION_BUDGET_NOT_SET"

    @pytest.mark.asyncio
    async def test_direct_key_reduction_leaves_siblings_untouched(self) -> None:
        svc = _svc()
        app = _application(1, allocated_budget=Decimal("50000"), allocated_percentage=Decimal("50"))
        key1 = _key(11, 1, allocated_budget=Decimal("30000"), allocated_percentage=Decimal("60"))
        key2 = _key(12, 1, allocated_budget=Decimal("20000"), allocated_percentage=Decimal("40"))
        svc._applications.get_by_id = AsyncMock(return_value=app)
        svc._applications.get_by_id_for_update = AsyncMock(return_value=app)
        svc._applications.sum_api_key_allocated_percentage = AsyncMock(return_value=Decimal("90"))
        svc._api_keys.list_by_application = AsyncMock(return_value=[key1, key2])
        svc._api_keys.update = AsyncMock()

        body = AllocationUpdateRequest(api_key_allocations=[
            APIKeyAllocationInput(api_key_id=11, allocated_budget=Decimal("25000"))
        ])
        with patch("app.services.budget_usage.fetch_budget_usage", AsyncMock(return_value={})), \
             patch("app.services.budget_usage.write_budget_snapshot", AsyncMock()):
            data = await svc.update_application_key_allocations(1, body, _user(), None)

        assert data.parent_id == "1"
        assert [r.api_key_id for r in data.api_key_allocations] == [11]
        assert data.api_key_allocations[0].allocated_budget == Decimal("25000.00")
        svc._api_keys.update.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_raising_a_keys_ceiling_clears_its_exhaustion_flag(self) -> None:
        """resolve_level's own floor-check already guarantees the new
        ceiling is >= what's consumed, so a Key that was exhausted under
        its OLD ceiling cannot still be exhausted under this new one —
        set_budget_exhausted_for_keys(..., False) must run for it, batched
        in one call rather than a per-key loop."""
        svc = _svc()
        app = _application(1, allocated_budget=Decimal("50000"), allocated_percentage=Decimal("50"))
        key1 = _key(11, 1, allocated_budget=Decimal("20000"), allocated_percentage=Decimal("40"))
        key2 = _key(12, 1, allocated_budget=Decimal("15000"), allocated_percentage=Decimal("30"))
        svc._applications.get_by_id = AsyncMock(return_value=app)
        svc._applications.get_by_id_for_update = AsyncMock(return_value=app)
        svc._applications.sum_api_key_allocated_percentage = AsyncMock(return_value=Decimal("100"))
        svc._api_keys.list_by_application = AsyncMock(return_value=[key1, key2])
        svc._api_keys.update = AsyncMock()

        # Key 12 stays fixed at 15000 (untouched at this scope); raising Key
        # 11 to 35000 leaves the total exactly at the Application's 50000.
        body = AllocationUpdateRequest(api_key_allocations=[
            APIKeyAllocationInput(api_key_id=11, allocated_budget=Decimal("35000"))
        ])
        with patch("app.services.budget_usage.fetch_budget_usage", AsyncMock(return_value={})), \
             patch("app.services.budget_usage.write_budget_snapshot", AsyncMock()):
            await svc.update_application_key_allocations(1, body, _user(), None)

        # Only Key 11 changed (Key 12 stays untouched at this scope) — only
        # its id is in the batch, not a tenant- or application-wide sweep.
        svc._api_key_service.set_budget_exhausted_for_keys.assert_awaited_once_with([11], False)

    @pytest.mark.asyncio
    async def test_unchanged_keys_have_no_exhaustion_call(self) -> None:
        """No write_budget_snapshot entry -> nothing to clear for that Key —
        the batch call still runs (uniformly, not conditionally skipped),
        just with an empty id list."""
        svc = _svc()
        app = _application(1, allocated_budget=Decimal("50000"), allocated_percentage=Decimal("50"))
        key1 = _key(11, 1, allocated_budget=Decimal("30000"), allocated_percentage=Decimal("60"))
        svc._applications.get_by_id = AsyncMock(return_value=app)
        svc._applications.get_by_id_for_update = AsyncMock(return_value=app)
        svc._applications.sum_api_key_allocated_percentage = AsyncMock(return_value=Decimal("60"))
        svc._api_keys.list_by_application = AsyncMock(return_value=[key1])
        svc._api_keys.update = AsyncMock()

        # Same value as it already has -> resolved.changed is False.
        body = AllocationUpdateRequest(api_key_allocations=[
            APIKeyAllocationInput(api_key_id=11, allocated_budget=Decimal("30000"))
        ])
        with patch("app.services.budget_usage.fetch_budget_usage", AsyncMock(return_value={})), \
             patch("app.services.budget_usage.write_budget_snapshot", AsyncMock()):
            await svc.update_application_key_allocations(1, body, _user(), None)

        svc._api_key_service.set_budget_exhausted_for_keys.assert_awaited_once_with([], False)

    @pytest.mark.asyncio
    async def test_key_raised_to_exactly_its_consumed_amount_is_not_cleared(self) -> None:
        """resolve_level's floor-check only requires amount >= consumed —
        exactly equal passes it, but a Key sitting exactly at its own
        consumption still has zero headroom. Clearing it here would let one
        more request slip through before its next billed request re-trips
        the flag, so it must be excluded from the cleared set even though
        it's a real, persisted change."""
        svc = _svc()
        app = _application(1, allocated_budget=Decimal("50000"), allocated_percentage=Decimal("50"))
        key1 = _key(11, 1, allocated_budget=Decimal("20000"), allocated_percentage=Decimal("40"))
        svc._applications.get_by_id = AsyncMock(return_value=app)
        svc._applications.get_by_id_for_update = AsyncMock(return_value=app)
        svc._applications.sum_api_key_allocated_percentage = AsyncMock(return_value=Decimal("60"))
        svc._api_keys.list_by_application = AsyncMock(return_value=[key1])
        svc._api_keys.update = AsyncMock()

        # Key 11 has consumed exactly 30000 — raising its ceiling to exactly
        # 30000 changes it (old was 20000) and passes the floor-check
        # (30000 >= 30000), but leaves zero headroom.
        body = AllocationUpdateRequest(api_key_allocations=[
            APIKeyAllocationInput(api_key_id=11, allocated_budget=Decimal("30000"))
        ])
        with patch(
            "app.services.budget_usage.fetch_budget_usage",
            AsyncMock(return_value={11: (Decimal("30000"), None)}),
        ), patch("app.services.budget_usage.write_budget_snapshot", AsyncMock()) as write_snap:
            await svc.update_application_key_allocations(1, body, _user(), None)

        # The reallocation itself still happened...
        svc._api_keys.update.assert_awaited_once()
        write_snap.assert_awaited_once_with({11: Decimal("30000.00")}, None)
        # ...but the exhaustion flag is not cleared for a Key with no real headroom.
        svc._api_key_service.set_budget_exhausted_for_keys.assert_awaited_once_with([], False)
