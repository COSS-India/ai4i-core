"""API key Redis cache vs tenant/application access — Suspend=Inactive (no DB revoke), Deactivate=Revoke.

Keys are owned by Applications, not Users (migration e9f0a1b2c3d4 dropped
api_key.user_id in favor of api_key.application_id) — eligibility depends on
the owning Application's and its Tenant's state.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.models.api_key import APIKey
from app.models.application import Application, ApplicationStatus
from app.models.tenant import Tenant, TenantStatus
from app.services.api_key_service import APIKeyService


def _api_key(*, is_active: bool = True) -> APIKey:
    return APIKey(
        id=1,
        application_id=1,
        key_name="test",
        api_key=uuid4().hex,
        permissions=[1],
        expires_at=datetime.now(timezone.utc) + timedelta(days=30),
        is_active=is_active,
    )


def _application(*, status: ApplicationStatus = ApplicationStatus.ACTIVE) -> Application:
    return Application(id=1, tenant_id=1, name="Test App", status=status)


def _tenant(*, status: TenantStatus = TenantStatus.ACTIVE) -> Tenant:
    return Tenant(
        id=1,
        name="Acme",
        organisation="Acme",
        email="test-contact@example.invalid",
        status=status,
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
        application = _application(status=ApplicationStatus.ACTIVE)
        tenant = _tenant(status=TenantStatus.ACTIVE)
        key = _api_key(is_active=True)

        cache = AsyncMock()
        cache.get_api_key_cache = AsyncMock(return_value={})
        repo = AsyncMock()
        repo.list_by_application = AsyncMock(return_value=[key])
        applications = AsyncMock()
        tenants = AsyncMock()
        tenants.get_by_id = AsyncMock(return_value=tenant)

        svc = APIKeyService(repo, cache, application_repo=applications, tenant_repo=tenants)
        await svc.refresh_keys_cache_for_application(application, tenant)

        cache.set_api_key_cache.assert_awaited_once()
        cache.delete_api_key_cache.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_refresh_does_not_reactivate_revoked_keys(self) -> None:
        application = _application()
        tenant = _tenant()
        key = _api_key(is_active=False)

        cache = AsyncMock()
        repo = AsyncMock()
        repo.list_by_application = AsyncMock(return_value=[key])

        svc = APIKeyService(repo, cache)
        await svc.refresh_keys_cache_for_application(application, tenant)

        cache.set_api_key_cache.assert_not_awaited()
        cache.delete_api_key_cache.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_evict_removes_all_application_keys_from_redis(self) -> None:
        keys = [_api_key(), _api_key()]
        keys[1].api_key = uuid4().hex
        cache = AsyncMock()
        repo = AsyncMock()
        repo.list_by_application = AsyncMock(return_value=keys)

        svc = APIKeyService(repo, cache)
        await svc.evict_keys_for_application(keys[0].application_id)

        assert cache.delete_api_key_cache.await_count == 2

    @pytest.mark.asyncio
    async def test_revoke_keys_for_tenant_commits_before_redis_delete(self) -> None:
        application = _application()
        active_key = _api_key(is_active=True)
        active_key.application_id = application.id

        cache = AsyncMock()
        repo = AsyncMock()
        repo.revoke_active_for_applications = AsyncMock(return_value=[active_key.api_key])
        applications = AsyncMock()
        applications.list_by_tenant = AsyncMock(return_value=[application])

        call_order: list[str] = []

        async def _commit() -> None:
            call_order.append("commit")

        async def _delete(_api_key: str) -> None:
            call_order.append("redis")

        repo.commit = AsyncMock(side_effect=_commit)
        cache.delete_api_key_cache = AsyncMock(side_effect=_delete)

        svc = APIKeyService(repo, cache, application_repo=applications)
        await svc.revoke_keys_for_tenant(1)

        repo.revoke_active_for_applications.assert_awaited_once_with([application.id])
        repo.commit.assert_awaited_once()
        cache.delete_api_key_cache.assert_awaited_once_with(active_key.api_key)
        assert call_order == ["commit", "redis"]

    @pytest.mark.asyncio
    async def test_revoke_keys_for_tenant_skips_redis_when_commit_fails(self) -> None:
        application = _application()
        active_key = _api_key(is_active=True)

        cache = AsyncMock()
        repo = AsyncMock()
        repo.revoke_active_for_applications = AsyncMock(return_value=[active_key.api_key])
        repo.commit = AsyncMock(side_effect=RuntimeError("db commit failed"))
        applications = AsyncMock()
        applications.list_by_tenant = AsyncMock(return_value=[application])

        svc = APIKeyService(repo, cache, application_repo=applications)
        with pytest.raises(RuntimeError, match="db commit failed"):
            await svc.revoke_keys_for_tenant(1)

        cache.delete_api_key_cache.assert_not_awaited()

    def test_application_may_use_api_keys_false_when_tenant_suspended(self) -> None:
        application = _application(status=ApplicationStatus.ACTIVE)
        tenant = _tenant(status=TenantStatus.SUSPENDED)
        assert APIKeyService.application_may_use_api_keys(application, tenant) is False

    def test_application_may_use_api_keys_false_when_application_inactive(self) -> None:
        application = _application(status=ApplicationStatus.INACTIVE)
        tenant = _tenant(status=TenantStatus.ACTIVE)
        assert APIKeyService.application_may_use_api_keys(application, tenant) is False

    def test_effective_is_active_false_when_key_revoked(self) -> None:
        application = _application()
        tenant = _tenant()
        key = _api_key(is_active=False)
        assert APIKeyService.effective_is_active(key, application, tenant) is False
