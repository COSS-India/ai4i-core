"""update_key_by_obj must write cached_data through even when the key isn't
currently eligible to be served (revoked, or application/tenant temporarily
inactive) — otherwise an admin edit to a dead/inactive key's permissions
would silently be lost from cached_data until some later reactivation event,
or forever for a permanently revoked key.

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

_TOKEN = "a" * 32


def _api_key(*, is_active: bool = True, cached_data: dict | None = None, application_id: int = 1) -> APIKey:
    return APIKey(
        id=1,
        application_id=application_id,
        key_name="test-key",
        api_key=_TOKEN,
        permissions=[1],
        expires_at=datetime.now(timezone.utc) + timedelta(days=30),
        is_active=is_active,
        cached_data=cached_data,
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


def _service(*, applications: object = ..., tenants: object = ...):
    repo = AsyncMock()
    cache = AsyncMock()
    applications = AsyncMock() if applications is ... else applications
    tenants = AsyncMock() if tenants is ... else tenants
    svc = APIKeyService(repo, cache, application_repo=applications, tenant_repo=tenants)
    return svc, repo, cache, applications, tenants


class TestUpdateKeyByObjWriteThroughWhenIneligible:
    @pytest.mark.asyncio
    async def test_revoked_key_gets_cached_data_updated_not_redis(self) -> None:
        svc, repo, cache, applications, tenants = _service()
        key = _api_key(is_active=False, cached_data={"api_key": _TOKEN, "tier_id": "tier-A", "permissions": [1]})
        repo.update = AsyncMock(return_value=key)
        repo.refresh = AsyncMock()
        repo.get_permission_ids_by_names = AsyncMock(return_value={"new-perm": 99})
        applications.get_by_id = AsyncMock(return_value=_application())
        tenants.get_by_id = AsyncMock(return_value=_tenant())

        await svc.update_key_by_obj(key, {"permissions": ["new-perm"]}, updated_by=uuid4())

        cache.set_api_key_cache.assert_not_awaited()
        cache.delete_api_key_cache.assert_awaited_once_with(_TOKEN)
        persisted = repo.update.await_args_list[-1].args[1]["cached_data"]
        assert persisted["tier_id"] == "tier-A"
        assert persisted["tenant_id"] == "1"
        repo.commit.assert_awaited()

    @pytest.mark.asyncio
    async def test_inactive_application_gets_cached_data_updated_not_redis(self) -> None:
        svc, repo, cache, applications, tenants = _service()
        key = _api_key(is_active=True, cached_data={"api_key": _TOKEN, "tier_id": "tier-A"})
        repo.update = AsyncMock(return_value=key)
        repo.refresh = AsyncMock()
        applications.get_by_id = AsyncMock(return_value=_application(status=ApplicationStatus.INACTIVE))
        tenants.get_by_id = AsyncMock(return_value=_tenant())

        await svc.update_key_by_obj(key, {"key_name": "renamed"})

        cache.set_api_key_cache.assert_not_awaited()
        cache.delete_api_key_cache.assert_awaited_once_with(_TOKEN)
        persisted = repo.update.await_args_list[-1].args[1]["cached_data"]
        assert persisted["tier_id"] == "tier-A"

    @pytest.mark.asyncio
    async def test_suspended_tenant_gets_cached_data_updated_not_redis(self) -> None:
        svc, repo, cache, applications, tenants = _service()
        key = _api_key(cached_data={"api_key": _TOKEN, "tier_id": "tier-A"})
        repo.update = AsyncMock(return_value=key)
        repo.refresh = AsyncMock()
        applications.get_by_id = AsyncMock(return_value=_application())
        tenants.get_by_id = AsyncMock(return_value=_tenant(status=TenantStatus.SUSPENDED))

        await svc.update_key_by_obj(key, {"key_name": "renamed"})

        cache.set_api_key_cache.assert_not_awaited()
        persisted = repo.update.await_args_list[-1].args[1]["cached_data"]
        assert persisted["tier_id"] == "tier-A"

    @pytest.mark.asyncio
    async def test_missing_application_row_still_updates_cached_data_with_no_tenant(self) -> None:
        svc, repo, cache, applications, _tenants = _service()
        key = _api_key(cached_data={"api_key": _TOKEN, "tier_id": "tier-A"})
        repo.update = AsyncMock(return_value=key)
        repo.refresh = AsyncMock()
        applications.get_by_id = AsyncMock(return_value=None)

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
        svc, repo, cache, applications, tenants = _service()
        key = _api_key(cached_data={"api_key": _TOKEN, "tier_id": "tier-A"})
        repo.update = AsyncMock(return_value=key)
        repo.refresh = AsyncMock()
        cache.get_api_key_cache = AsyncMock(return_value=None)
        applications.get_by_id = AsyncMock(return_value=_application())
        tenants.get_by_id = AsyncMock(return_value=_tenant())

        await svc.update_key_by_obj(key, {"key_name": "renamed"})

        cache.set_api_key_cache.assert_awaited_once()
        cache.delete_api_key_cache.assert_not_awaited()
        written = cache.set_api_key_cache.await_args.args[2]
        assert written["tier_id"] == "tier-A"
