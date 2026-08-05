"""Write-through of PPU billing/quota flags into api_key.cached_data.

kafka-consumers' handle_ppu_usage (payperuse_consumer/handler.py) drives
budget-exhausted/quota-exhausted via auth-service's internal endpoints
(routes/internal.py -> APIKeyService.set_budget_exhausted_for_tenant /
set_quota_exhausted_for_tenant), and the same tenant-cache-patching helper
backs the tier-reassignment and monthly-cron quota-reset paths. All four
previously patched Redis only, silently drifting from cached_data (the
DB-fallback source of truth validate_api_key rehydrates from on a miss) —
this locks in that both now stay in sync.
"""

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from ai4i_core.ppu import get_inference_types

from app.models.api_key import APIKey
from app.models.user import User
from app.services.api_key_service import APIKeyService

_INFERENCE_FIELDS = [f"quota-{entry['name']}" for entry in get_inference_types()]


def _api_key(*, is_active: bool = True) -> APIKey:
    return APIKey(
        id=1,
        user_id=uuid4(),
        key_name="test",
        api_key=uuid4().hex,
        permissions=[1],
        is_active=is_active,
        cached_data={"api_key": "x"},
    )


def _user() -> User:
    return User(
        id=uuid4(),
        email="test-user@example.invalid",
        username=uuid4().hex[:12],
        tenant_id=1,
        is_active=True,
    )


def _service_with_one_active_key():
    """A repo/users pairing that yields exactly one active key for tenant_id=1,
    wired the way _for_each_active_tenant_key walks it (users, then per-user keys)."""
    repo = AsyncMock()
    users = AsyncMock()
    cache = AsyncMock()
    key = _api_key()
    users.list_by_tenant = AsyncMock(side_effect=[[_user()], []])
    repo.list_by_user = AsyncMock(return_value=[key])
    svc = APIKeyService(repo, cache, user_repo=users)
    return svc, repo, users, cache, key


class TestSetBudgetExhaustedForTenant:
    @pytest.mark.asyncio
    async def test_patches_redis_and_cached_data(self) -> None:
        svc, repo, _users, cache, key = _service_with_one_active_key()
        await svc.set_budget_exhausted_for_tenant(1, True)
        cache.patch_api_key_cache_field.assert_awaited_once_with(key.api_key, "budget-exhausted", "1")
        repo.patch_cached_data_field_for_tenant.assert_awaited_once_with(1, "budget-exhausted", "1")
        repo.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_clearing_writes_string_zero(self) -> None:
        svc, repo, _users, _cache, _key = _service_with_one_active_key()
        await svc.set_budget_exhausted_for_tenant(1, False)
        repo.patch_cached_data_field_for_tenant.assert_awaited_once_with(1, "budget-exhausted", "0")

    @pytest.mark.asyncio
    async def test_missing_repo_skips_everything(self) -> None:
        cache = AsyncMock()
        svc = APIKeyService(None, cache, user_repo=AsyncMock())
        await svc.set_budget_exhausted_for_tenant(1, True)
        cache.patch_api_key_cache_field.assert_not_awaited()


class TestSetQuotaExhaustedForTenant:
    @pytest.mark.asyncio
    async def test_patches_redis_and_cached_data(self) -> None:
        svc, repo, _users, cache, key = _service_with_one_active_key()
        await svc.set_quota_exhausted_for_tenant(1, "nmt")
        cache.patch_api_key_cache_field.assert_awaited_once_with(key.api_key, "quota-nmt", "1")
        repo.patch_cached_data_field_for_tenant.assert_awaited_once_with(1, "quota-nmt", "1")
        repo.commit.assert_awaited_once()


class TestClearQuotaFlagsForTenant:
    @pytest.mark.asyncio
    async def test_clears_redis_and_cached_data(self) -> None:
        svc, repo, _users, cache, key = _service_with_one_active_key()
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
        repo.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_missing_repo_skips(self) -> None:
        cache = AsyncMock()
        svc = APIKeyService(None, cache)
        await svc.reset_all_quota_fields()
        cache.delete_api_key_cache_fields_bulk.assert_not_awaited()
