"""update_key_by_obj must write cached_data through even when the key isn't
currently eligible to be served (revoked, or owner/tenant temporarily
inactive) — otherwise an admin edit to a dead/inactive key's permissions
would silently be lost from cached_data until some later reactivation event,
or forever for a permanently revoked key.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.models.api_key import APIKey
from app.models.tenant import Tenant, TenantStatus
from app.models.user import User
from app.services.api_key_service import APIKeyService

_TOKEN = "a" * 32


def _api_key(*, is_active: bool = True, cached_data: dict | None = None) -> APIKey:
    return APIKey(
        id=1,
        user_id=uuid4(),
        key_name="test-key",
        api_key=_TOKEN,
        permissions=[1],
        expires_at=datetime.now(timezone.utc) + timedelta(days=30),
        is_active=is_active,
        cached_data=cached_data,
    )


def _user(*, is_active: bool = True) -> User:
    return User(
        id=uuid4(),
        email="test-user@example.invalid",
        username=uuid4().hex[:12],
        tenant_id=1,
        is_active=is_active,
        is_delete=False,
        is_tenant_active=True,
    )


def _tenant(*, status: TenantStatus = TenantStatus.ACTIVE) -> Tenant:
    return Tenant(
        id=1,
        name="Acme",
        organisation="Acme",
        email="test-contact@example.invalid",
        status=status,
    )


def _service(*, users: object = ..., tenants: object = ...):
    repo = AsyncMock()
    cache = AsyncMock()
    users = AsyncMock() if users is ... else users
    tenants = AsyncMock() if tenants is ... else tenants
    svc = APIKeyService(repo, cache, user_repo=users, tenant_repo=tenants)
    return svc, repo, cache, users, tenants


class TestUpdateKeyByObjWriteThroughWhenIneligible:
    @pytest.mark.asyncio
    async def test_revoked_key_gets_cached_data_updated_not_redis(self) -> None:
        svc, repo, cache, users, tenants = _service()
        key = _api_key(is_active=False, cached_data={"api_key": _TOKEN, "tier_id": "tier-A", "permissions": [1]})
        repo.update = AsyncMock(return_value=key)
        repo.refresh = AsyncMock()
        repo.get_permission_ids_by_names = AsyncMock(return_value={"new-perm": 99})
        users.get_by_id = AsyncMock(return_value=_user())
        tenants.get_by_id = AsyncMock(return_value=_tenant())

        await svc.update_key_by_obj(key, {"permissions": ["new-perm"]}, user_id=uuid4())

        cache.set_api_key_cache.assert_not_awaited()
        cache.delete_api_key_cache.assert_awaited_once_with(_TOKEN)
        persisted = repo.update.await_args_list[-1].args[1]["cached_data"]
        assert persisted["tier_id"] == "tier-A"
        assert persisted["tenant_id"] == "1"
        repo.commit.assert_awaited()

    @pytest.mark.asyncio
    async def test_inactive_owner_gets_cached_data_updated_not_redis(self) -> None:
        svc, repo, cache, users, tenants = _service()
        key = _api_key(is_active=True, cached_data={"api_key": _TOKEN, "tier_id": "tier-A"})
        repo.update = AsyncMock(return_value=key)
        repo.refresh = AsyncMock()
        users.get_by_id = AsyncMock(return_value=_user(is_active=False))
        tenants.get_by_id = AsyncMock(return_value=_tenant())

        await svc.update_key_by_obj(key, {"key_name": "renamed"})

        cache.set_api_key_cache.assert_not_awaited()
        cache.delete_api_key_cache.assert_awaited_once_with(_TOKEN)
        persisted = repo.update.await_args_list[-1].args[1]["cached_data"]
        assert persisted["tier_id"] == "tier-A"

    @pytest.mark.asyncio
    async def test_suspended_tenant_gets_cached_data_updated_not_redis(self) -> None:
        svc, repo, cache, users, tenants = _service()
        key = _api_key(cached_data={"api_key": _TOKEN, "tier_id": "tier-A"})
        repo.update = AsyncMock(return_value=key)
        repo.refresh = AsyncMock()
        users.get_by_id = AsyncMock(return_value=_user())
        tenants.get_by_id = AsyncMock(return_value=_tenant(status=TenantStatus.SUSPENDED))

        await svc.update_key_by_obj(key, {"key_name": "renamed"})

        cache.set_api_key_cache.assert_not_awaited()
        persisted = repo.update.await_args_list[-1].args[1]["cached_data"]
        assert persisted["tier_id"] == "tier-A"

    @pytest.mark.asyncio
    async def test_missing_owner_row_still_updates_cached_data_with_no_tenant(self) -> None:
        svc, repo, cache, users, _tenants = _service()
        key = _api_key(cached_data={"api_key": _TOKEN, "tier_id": "tier-A"})
        repo.update = AsyncMock(return_value=key)
        repo.refresh = AsyncMock()
        users.get_by_id = AsyncMock(return_value=None)

        await svc.update_key_by_obj(key, {"key_name": "renamed"})

        cache.set_api_key_cache.assert_not_awaited()
        persisted = repo.update.await_args_list[-1].args[1]["cached_data"]
        assert persisted["tenant_id"] is None
        assert persisted["tier_id"] == "tier-A"

    @pytest.mark.asyncio
    async def test_eligible_key_still_takes_the_refresh_redis_cache_path(self) -> None:
        """Regression check: merging the two ineligible branches must not change
        the eligible (normal) path — it still refreshes Redis and persists via
        _refresh_redis_cache, not the new ineligible-only helper."""
        svc, repo, cache, users, tenants = _service()
        key = _api_key(cached_data={"api_key": _TOKEN, "tier_id": "tier-A"})
        repo.update = AsyncMock(return_value=key)
        repo.refresh = AsyncMock()
        cache.get_api_key_cache = AsyncMock(return_value=None)
        users.get_by_id = AsyncMock(return_value=_user())
        tenants.get_by_id = AsyncMock(return_value=_tenant())

        await svc.update_key_by_obj(key, {"key_name": "renamed"})

        cache.set_api_key_cache.assert_awaited_once()
        cache.delete_api_key_cache.assert_not_awaited()
        written = cache.set_api_key_cache.await_args.args[2]
        assert written["tier_id"] == "tier-A"