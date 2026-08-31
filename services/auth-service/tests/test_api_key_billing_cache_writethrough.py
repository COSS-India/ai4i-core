"""Write-through of PPU billing/quota flags into api_key.cached_data.

kafka-consumers' handle_ppu_usage (payperuse_consumer/handler.py) drives
budget-exhausted (per API Key, via auth-service's
/internal/ppu/api-key/{id}/budget-exhausted -> APIKeyService.
set_budget_exhausted_for_key) and quota-exhausted (per tenant, via
set_quota_exhausted_for_tenant). budget-exhausted used to also be
tenant-wide (set_budget_exhausted_for_tenant, patching every key under the
tenant from a single key's own usage) — re-scoped to one key, since budget
is now tracked per key (budget_usage), not a shared tenant wallet. Cleared
back to false only as a side effect of AllocationService/create_api_key
raising that same key's own ceiling (write_budget_snapshot's callers) —
never as a standalone admin action; see set_budget_exhausted_for_key's
docstring. quota-exhausted stays tenant-wide (the same tenant-cache-
patching helper also backs the tier-reassignment and monthly-cron
quota-reset paths) — quota is still a tier-wide entitlement, not a per-key
ceiling. All of these previously patched Redis only, silently drifting from
cached_data (the DB-fallback source of truth validate_api_key rehydrates
from on a miss) — this locks in that both now stay in sync.

Keys are owned by Applications, not Users (migration e9f0a1b2c3d4 dropped
api_key.user_id in favor of api_key.application_id); the tenant-wide cache
cascade (_for_each_active_tenant_key) walks api_keys directly via a
join-through-Application query, not per-user.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from ai4i_core.ppu import get_inference_types

from app.models.api_key import APIKey
from app.repositories.api_key_repository import APIKeyRepository
from app.services.api_key_service import APIKeyService

_INFERENCE_FIELDS = [f"quota-{entry['name']}" for entry in get_inference_types()]


def _api_key(*, is_active: bool = True, application_id: int = 1) -> APIKey:
    return APIKey(
        id=1,
        application_id=application_id,
        key_name="test",
        api_key="a" * 32,
        permissions=[1],
        is_active=is_active,
        cached_data={"api_key": "x"},
    )


def _service_with_one_active_key():
    """A repo yielding exactly one active key for tenant_id=1, wired the way
    _for_each_active_tenant_key walks it (one keyset page, shorter than the
    page size, so the loop stops after processing it)."""
    repo = AsyncMock()
    cache = AsyncMock()
    key = _api_key()
    repo.list_active_keys_for_tenant = AsyncMock(return_value=[key])
    svc = APIKeyService(repo, cache)
    return svc, repo, cache, key


_UNSET = object()


def _service_with_one_key(*, cached_data=_UNSET) -> tuple:
    """A repo yielding exactly one key by id — the shape
    set_budget_exhausted_for_key looks it up with, not the tenant-wide
    keyset-paginated walk the other setters below use. cached_data=None is a
    real, distinct case (a key with no snapshot yet) from "not passed" —
    hence the sentinel rather than defaulting the param to None itself."""
    repo = AsyncMock()
    cache = AsyncMock()
    key = _api_key()
    if cached_data is not _UNSET:
        key.cached_data = cached_data
    repo.get_by_id = AsyncMock(return_value=key)
    svc = APIKeyService(repo, cache)
    return svc, repo, cache, key


class TestSetBudgetExhaustedForKey:
    """Scoped to exactly one Key — never fans out to sibling Keys under the
    same tenant, unlike set_tier_id_for_tenant/set_quota_exhausted_for_tenant
    below (both still legitimately tenant-wide: a tier or quota entitlement
    applies to the whole tenant; a ₹ ceiling does not)."""

    @pytest.mark.asyncio
    async def test_patches_only_this_keys_redis_and_cached_data(self) -> None:
        svc, repo, cache, key = _service_with_one_key(cached_data={"api_key": "a" * 32})
        await svc.set_budget_exhausted_for_key(1, True)
        repo.get_by_id.assert_awaited_once_with(1)
        cache.patch_api_key_cache_field.assert_awaited_once_with(key.api_key, "budget-exhausted", "1")
        repo.update.assert_awaited_once_with(key, {"cached_data": {"api_key": key.api_key, "budget-exhausted": "1"}})
        repo.commit.assert_awaited_once()
        # Never the tenant-wide walk — no other key could be touched by this call.
        repo.list_active_keys_for_tenant.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_preserves_other_cached_data_fields(self) -> None:
        svc, repo, _cache, key = _service_with_one_key(
            cached_data={"api_key": "a" * 32, "quota-nmt": "1", "tier_id": "t1"}
        )
        await svc.set_budget_exhausted_for_key(1, True)
        written = repo.update.await_args.args[1]["cached_data"]
        assert written == {"api_key": key.api_key, "quota-nmt": "1", "tier_id": "t1", "budget-exhausted": "1"}

    @pytest.mark.asyncio
    async def test_unknown_key_id_is_a_noop(self) -> None:
        repo = AsyncMock()
        repo.get_by_id = AsyncMock(return_value=None)
        cache = AsyncMock()
        svc = APIKeyService(repo, cache)
        await svc.set_budget_exhausted_for_key(999, True)
        cache.patch_api_key_cache_field.assert_not_awaited()
        repo.update.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_missing_repo_skips_everything(self) -> None:
        cache = AsyncMock()
        svc = APIKeyService(None, cache)
        await svc.set_budget_exhausted_for_key(1, True)
        cache.patch_api_key_cache_field.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_key_with_no_cached_data_snapshot_is_skipped(self) -> None:
        """Migration 75a838d63699 added cached_data nullable with no
        backfill — a key issued before it can still have NULL here.
        Writing {"budget-exhausted": value} as its first-ever snapshot
        would drop every other field (permissions, application_id, ...);
        _rehydrate_cache_from_db serves that verbatim on a later Redis
        miss, and /auth/validate then answers with an empty permission
        list instead of failing loudly. Matches
        patch_cached_data_field_for_tenant's require_cached_data=True
        filter on the tenant-wide path this replaced."""
        svc, repo, cache, _key = _service_with_one_key(cached_data=None)
        await svc.set_budget_exhausted_for_key(1, True)
        cache.patch_api_key_cache_field.assert_not_awaited()
        repo.update.assert_not_awaited()
        repo.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_inactive_key_is_skipped(self) -> None:
        repo = AsyncMock()
        cache = AsyncMock()
        key = _api_key(is_active=False)
        key.cached_data = {"api_key": key.api_key}
        repo.get_by_id = AsyncMock(return_value=key)
        svc = APIKeyService(repo, cache)
        await svc.set_budget_exhausted_for_key(1, True)
        cache.patch_api_key_cache_field.assert_not_awaited()
        repo.update.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_expired_key_is_skipped(self) -> None:
        repo = AsyncMock()
        cache = AsyncMock()
        key = _api_key()
        key.cached_data = {"api_key": key.api_key}
        key.expires_at = datetime.now(timezone.utc) - timedelta(days=1)
        repo.get_by_id = AsyncMock(return_value=key)
        svc = APIKeyService(repo, cache)
        await svc.set_budget_exhausted_for_key(1, True)
        cache.patch_api_key_cache_field.assert_not_awaited()
        repo.update.assert_not_awaited()


class TestSetBudgetExhaustedForKeys:
    """Batched sibling of set_budget_exhausted_for_key — one repo call plus
    one commit for the whole id list, not a per-key round trip. Used by
    AllocationService._clear_exhaustion_for_changed_keys, which already has
    every affected key id in hand from a single reallocation call."""

    @pytest.mark.asyncio
    async def test_patches_redis_for_every_returned_key_and_commits_once(self) -> None:
        repo = AsyncMock()
        cache = AsyncMock()
        repo.patch_cached_data_field_for_keys = AsyncMock(return_value=["key-a", "key-b"])
        svc = APIKeyService(repo, cache)

        await svc.set_budget_exhausted_for_keys([1, 2], False)

        repo.patch_cached_data_field_for_keys.assert_awaited_once_with([1, 2], "budget-exhausted", "0")
        assert cache.patch_api_key_cache_field.await_args_list == [
            (("key-a", "budget-exhausted", "0"),),
            (("key-b", "budget-exhausted", "0"),),
        ]
        repo.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_ineligible_key_ids_are_simply_absent_from_the_redis_patch(self) -> None:
        """The repo's own eligibility filter (active, non-expired, has
        cached_data) decides what's returned — an id that doesn't qualify
        just isn't in the RETURNING list, no separate lookup needed here."""
        repo = AsyncMock()
        cache = AsyncMock()
        repo.patch_cached_data_field_for_keys = AsyncMock(return_value=["key-a"])
        svc = APIKeyService(repo, cache)

        await svc.set_budget_exhausted_for_keys([1, 2, 3], True)

        cache.patch_api_key_cache_field.assert_awaited_once_with("key-a", "budget-exhausted", "1")

    @pytest.mark.asyncio
    async def test_empty_id_list_is_a_noop(self) -> None:
        repo = AsyncMock()
        cache = AsyncMock()
        svc = APIKeyService(repo, cache)

        await svc.set_budget_exhausted_for_keys([], False)

        repo.patch_cached_data_field_for_keys.assert_not_awaited()
        cache.patch_api_key_cache_field.assert_not_awaited()
        repo.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_missing_repo_skips_everything(self) -> None:
        cache = AsyncMock()
        svc = APIKeyService(None, cache)

        await svc.set_budget_exhausted_for_keys([1, 2], False)

        cache.patch_api_key_cache_field.assert_not_awaited()


class TestSetQuotaExhaustedForTenant:
    @pytest.mark.asyncio
    async def test_patches_redis_and_cached_data(self) -> None:
        svc, repo, cache, key = _service_with_one_active_key()
        await svc.set_quota_exhausted_for_tenant(1, "nmt")
        cache.patch_api_key_cache_field.assert_awaited_once_with(key.api_key, "quota-nmt", "1")
        repo.patch_cached_data_field_for_tenant.assert_awaited_once_with(1, "quota-nmt", "1")
        repo.commit.assert_awaited_once()


class TestClearQuotaFlagsForTenant:
    @pytest.mark.asyncio
    async def test_clears_redis_and_cached_data(self) -> None:
        svc, repo, cache, key = _service_with_one_active_key()
        await svc.clear_quota_flags_for_tenant(1)
        cache.delete_api_key_cache_fields.assert_awaited_once_with(key.api_key, _INFERENCE_FIELDS)
        repo.remove_cached_data_fields_for_tenant.assert_awaited_once_with(1, _INFERENCE_FIELDS)
        repo.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_missing_repositories_skips(self) -> None:
        cache = AsyncMock()
        svc = APIKeyService(None, cache)
        await svc.clear_quota_flags_for_tenant(1)
        cache.delete_api_key_cache_fields.assert_not_awaited()


class TestResetAllQuotaFields:
    @pytest.mark.asyncio
    async def test_clears_redis_pages_then_cached_data_once(self) -> None:
        repo = AsyncMock()
        cache = AsyncMock()
        key = _api_key()
        repo.list_active_keys = AsyncMock(side_effect=[[key], []])
        svc = APIKeyService(repo, cache)
        await svc.reset_all_quota_fields()
        cache.delete_api_key_cache_fields_bulk.assert_awaited_once_with([key.api_key], _INFERENCE_FIELDS)
        repo.remove_cached_data_fields_globally.assert_awaited_once_with(_INFERENCE_FIELDS)
        # No trailing service-level commit: remove_cached_data_fields_globally now
        # commits per batch internally (keyset-paginated).
        repo.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_missing_repo_skips(self) -> None:
        cache = AsyncMock()
        svc = APIKeyService(None, cache)
        await svc.reset_all_quota_fields()
        cache.delete_api_key_cache_fields_bulk.assert_not_awaited()


class TestRemoveCachedDataFieldsGloballyBatching:
    """The monthly-cron cached_data clear must keyset-paginate with a commit
    per batch, not one table-wide UPDATE — see remove_cached_data_fields_globally."""

    @staticmethod
    def _select_result(ids: list[int]) -> MagicMock:
        r = MagicMock()
        r.scalars.return_value.all.return_value = ids
        return r

    @staticmethod
    def _update_result(rowcount: int) -> MagicMock:
        r = MagicMock()
        r.rowcount = rowcount
        return r

    @pytest.mark.asyncio
    async def test_paginates_by_id_and_commits_each_batch(self) -> None:
        db = AsyncMock()
        # batch 1: ids [1,2] (== batch_size, keep going); batch 2: ids [3] (short, stop).
        db.execute = AsyncMock(
            side_effect=[
                self._select_result([1, 2]), self._update_result(2),
                self._select_result([3]), self._update_result(1),
            ]
        )
        repo = APIKeyRepository(db)

        total = await repo.remove_cached_data_fields_globally(["quota-nmt"], batch_size=2)

        assert total == 3                      # rowcounts accumulated across batches
        assert db.commit.await_count == 2      # one commit per batch, not one at the end
        assert db.execute.await_count == 4     # (select + update) x 2 batches

    @pytest.mark.asyncio
    async def test_empty_fields_is_a_noop(self) -> None:
        db = AsyncMock()
        repo = APIKeyRepository(db)
        assert await repo.remove_cached_data_fields_globally([]) == 0
        db.execute.assert_not_awaited()
        db.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_no_matching_keys_does_nothing(self) -> None:
        db = AsyncMock()
        db.execute = AsyncMock(side_effect=[self._select_result([])])
        repo = APIKeyRepository(db)
        assert await repo.remove_cached_data_fields_globally(["quota-nmt"]) == 0
        db.commit.assert_not_awaited()


class TestRevokeWhileExhausted:
    """revoke_by_obj never touches cached_data, so a stale budget-exhausted/quota-*
    flag can persist there after revocation. That's harmless: get_by_api_key_if_valid
    hard-filters is_active.is_(True) in SQL, so once is_active flips to False this row
    can never be returned by the DB-fallback lookup again, making cached_data's
    content permanently inert regardless of what it holds. That reasoning had no test
    until now. Proves the two things revoke_by_obj is actually responsible for —
    Redis fully cleared, is_active flipped False — and confirms cached_data is left
    untouched (the intended behavior, relying on the SQL filter above rather than an
    explicit clear), not silently scrubbed by accident.
    """

    @staticmethod
    def _service_with_revoke_side_effect():
        repo = AsyncMock()

        async def _revoke(key: APIKey) -> None:
            key.is_active = False

        repo.revoke = AsyncMock(side_effect=_revoke)
        cache = AsyncMock()
        return APIKeyService(repo, cache), repo, cache

    @pytest.mark.asyncio
    async def test_revoking_an_exhausted_key_clears_redis_and_deactivates_it(self) -> None:
        svc, repo, cache = self._service_with_revoke_side_effect()
        key = _api_key(is_active=True)
        key.cached_data = {"api_key": key.api_key, "budget-exhausted": "1", "quota-nmt": "1"}

        await svc.revoke_by_obj(key)

        assert key.is_active is False
        cache.delete_api_key_cache.assert_awaited_once_with(key.api_key)
        cache.set_api_key_cache.assert_not_awaited()
        repo.commit.assert_awaited_once()
        # cached_data is never touched by revoke_by_obj — the stale flags survive in
        # the DB, which is fine precisely because is_active=False makes this row
        # unreachable via get_by_api_key_if_valid from now on (that SQL filter itself
        # isn't re-verified by this test — it's a separate, already-reviewed query).
        repo.update.assert_not_awaited()
        assert key.cached_data == {
            "api_key": key.api_key, "budget-exhausted": "1", "quota-nmt": "1"
        }
