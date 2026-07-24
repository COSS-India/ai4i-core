"""API key Redis cache vs tenant/user access — Suspend=Inactive (no DB revoke), Deactivate=Revoke."""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.models.api_key import APIKey
from app.models.tenant import Tenant, TenantStatus
from app.models.user import User
from app.services.api_key_service import APIKeyService


def _api_key(*, is_active: bool = True) -> APIKey:
    return APIKey(
        id=1,
        user_id=uuid4(),
        key_name="test",
        api_key=uuid4().hex,
        permissions=[1],
        expires_at=datetime.now(timezone.utc) + timedelta(days=30),
        is_active=is_active,
    )


class TestAPIKeyIsExpired:
    def test_inactive_key_is_not_calendar_expired(self) -> None:
        key = _api_key(is_active=False)
        assert key.is_expired() is False

    def test_past_expires_at_is_expired(self) -> None:
        key = _api_key()
        key.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        assert key.is_expired() is True


class TestAPIKeyCacheLifecycle:
    @pytest.mark.asyncio
    async def test_refresh_repopulates_redis_after_tenant_reactivation(self) -> None:
        user = User(
            id=uuid4(),
            email="test-user@example.invalid",
            username=uuid4().hex[:12],
            tenant_id=1,
            is_active=True,
            is_tenant_active=True,
        )
        tenant = Tenant(
            id=1,
            name="Acme",
            organisation="Acme",
            email="test-contact@example.invalid",
            status=TenantStatus.ACTIVE,
        )
        key = _api_key(is_active=True)

        cache = AsyncMock()
        cache.get_api_key_cache = AsyncMock(return_value={})
        repo = AsyncMock()
        repo.list_by_user = AsyncMock(return_value=[key])
        users = AsyncMock()
        tenants = AsyncMock()
        tenants.get_by_id = AsyncMock(return_value=tenant)

        svc = APIKeyService(repo, cache, user_repo=users, tenant_repo=tenants)
        await svc.refresh_keys_cache_for_user(user, tenant)

        cache.set_api_key_cache.assert_awaited_once()
        cache.delete_api_key_cache.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_refresh_does_not_reactivate_revoked_keys(self) -> None:
        user = User(
            id=uuid4(),
            email="test-user@example.invalid",
            username=uuid4().hex[:12],
            tenant_id=1,
            is_active=True,
            is_tenant_active=True,
        )
        tenant = Tenant(
            id=1,
            name="Acme",
            organisation="Acme",
            email="test-contact@example.invalid",
            status=TenantStatus.ACTIVE,
        )
        key = _api_key(is_active=False)

        cache = AsyncMock()
        repo = AsyncMock()
        repo.list_by_user = AsyncMock(return_value=[key])

        svc = APIKeyService(repo, cache)
        await svc.refresh_keys_cache_for_user(user, tenant)

        cache.set_api_key_cache.assert_not_awaited()
        cache.delete_api_key_cache.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_evict_removes_all_user_keys_from_redis(self) -> None:
        keys = [_api_key(), _api_key()]
        keys[1].api_key = uuid4().hex
        cache = AsyncMock()
        repo = AsyncMock()
        repo.list_by_user = AsyncMock(return_value=keys)

        svc = APIKeyService(repo, cache)
        await svc.evict_keys_for_user(keys[0].user_id)

        assert cache.delete_api_key_cache.await_count == 2

    @pytest.mark.asyncio
    async def test_revoke_keys_for_tenant_sets_inactive_and_evicts_redis(self) -> None:
        user = User(
            id=uuid4(),
            email="test-user@example.invalid",
            username=uuid4().hex[:12],
            tenant_id=1,
            is_active=True,
            is_tenant_active=False,
        )
        active_key = _api_key(is_active=True)
        already_revoked = _api_key(is_active=False)
        already_revoked.api_key = uuid4().hex
        active_key.user_id = user.id
        already_revoked.user_id = user.id

        cache = AsyncMock()
        repo = AsyncMock()
        repo.list_by_user = AsyncMock(return_value=[active_key, already_revoked])
        repo.revoke = AsyncMock()
        repo.commit = AsyncMock()
        users = AsyncMock()
        users.list_by_tenant = AsyncMock(side_effect=[[user], []])

        svc = APIKeyService(repo, cache, user_repo=users)
        await svc.revoke_keys_for_tenant(1)

        repo.revoke.assert_awaited_once_with(active_key)
        cache.delete_api_key_cache.assert_awaited_once_with(active_key.api_key)
        repo.commit.assert_awaited_once()

    def test_user_may_use_api_keys_false_when_tenant_suspended(self) -> None:
        user = User(
            id=uuid4(),
            email="test-user@example.invalid",
            username=uuid4().hex[:12],
            tenant_id=1,
            is_active=True,
            is_tenant_active=False,
        )
        tenant = Tenant(
            id=1,
            name="Acme",
            organisation="Acme",
            email="test-contact@example.invalid",
            status=TenantStatus.SUSPENDED,
        )
        assert APIKeyService.user_may_use_api_keys(user, tenant) is False

    def test_effective_is_active_false_when_key_revoked(self) -> None:
        user = User(
            id=uuid4(),
            email="test-user@example.invalid",
            username=uuid4().hex[:12],
            tenant_id=1,
            is_active=True,
            is_tenant_active=True,
        )
        tenant = Tenant(
            id=1,
            name="Acme",
            organisation="Acme",
            email="test-contact@example.invalid",
            status=TenantStatus.ACTIVE,
        )
        key = _api_key(is_active=False)
        assert APIKeyService.effective_is_active(key, user, tenant) is False
