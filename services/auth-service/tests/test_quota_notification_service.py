"""Unit tests for QuotaNotificationService.notify_quota_limit_updated.

The caller (platform-core-service) can no longer compute
tenant_ids itself (ppu_tenant_tier_assignments has been dropped) — it sends
tier_id instead and this resolves the affected tenants from tenants.tier_id
(the live source of truth) via TenantRepository.list_with_tier. The old
tenant_ids-only path is kept as a fallback for a rolling-deploy window
against an older caller (see QuotaLimitUpdatedRequest).
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.services.quota_notification_service import QuotaNotificationService


def _svc():
    role_repo = AsyncMock()
    role_repo.get_tenant_admins = AsyncMock(return_value=[])
    tenant_repo = AsyncMock()
    email_client = MagicMock()
    svc = QuotaNotificationService(
        role_repo=role_repo, email_client=email_client, tenant_repo=tenant_repo
    )
    return svc, role_repo, tenant_repo


class TestNotifyQuotaLimitUpdated:
    @pytest.mark.asyncio
    async def test_tier_id_resolves_tenants_from_tenant_repo(self):
        svc, role_repo, tenant_repo = _svc()
        tier_id = uuid4()
        tenant_repo.list_with_tier = AsyncMock(
            return_value=[MagicMock(id=1), MagicMock(id=2)]
        )
        background_tasks = MagicMock()

        await svc.notify_quota_limit_updated(
            "Pro", [], background_tasks, tier_id=str(tier_id)
        )

        tenant_repo.list_with_tier.assert_awaited_once_with(tier_id)
        assert role_repo.get_tenant_admins.await_args_list == [
            ((1,),), ((2,),),
        ]

    @pytest.mark.asyncio
    async def test_tier_id_takes_priority_over_passed_tenant_ids(self):
        """A caller passing both must be resolved from tier_id, not the stale
        tenant_ids it also sent — tier_id is the source of truth now."""
        svc, role_repo, tenant_repo = _svc()
        tenant_repo.list_with_tier = AsyncMock(return_value=[MagicMock(id=9)])
        background_tasks = MagicMock()

        await svc.notify_quota_limit_updated(
            "Pro", ["1", "2"], background_tasks, tier_id=str(uuid4())
        )

        role_repo.get_tenant_admins.assert_awaited_once_with(9)

    @pytest.mark.asyncio
    async def test_invalid_tier_id_resolves_to_no_tenants(self):
        svc, role_repo, tenant_repo = _svc()
        background_tasks = MagicMock()

        await svc.notify_quota_limit_updated(
            "Pro", [], background_tasks, tier_id="not-a-uuid"
        )

        tenant_repo.list_with_tier.assert_not_awaited()
        role_repo.get_tenant_admins.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_no_tier_id_falls_back_to_passed_tenant_ids(self):
        """Rolling-deploy compatibility: an older caller that only sends
        tenant_ids (no tier_id) must still work."""
        svc, role_repo, tenant_repo = _svc()
        background_tasks = MagicMock()

        await svc.notify_quota_limit_updated("Pro", ["5"], background_tasks)

        tenant_repo.list_with_tier.assert_not_awaited()
        role_repo.get_tenant_admins.assert_awaited_once_with(5)

    @pytest.mark.asyncio
    async def test_non_numeric_tenant_id_is_skipped_not_raised(self):
        svc, role_repo, tenant_repo = _svc()
        background_tasks = MagicMock()

        await svc.notify_quota_limit_updated("Pro", ["abc"], background_tasks)

        role_repo.get_tenant_admins.assert_not_awaited()
