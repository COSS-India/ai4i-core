"""Unit tests for tier_service's cross-service calls into auth-service —
_notify_tier_updated and delete_tier's tenant-in-use check.

Both used to read/write ppu_tenant_tier_assignments directly; that table has
since been dropped, and tenant<->tier assignment now lives solely on auth-service's
tenants.tier_id. tier_service has no DB-local way to answer "which tenants
are on this tier" or "is this tier in use" any more, so both now go over
HTTP to auth-service instead.
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from app.services.pay_per_use import tier_service


def _tier(**kwargs):
    defaults = dict(id=uuid.uuid4(), name="Pro", is_active=True)
    return MagicMock(**{**defaults, **kwargs})


def _http_client(*, json_return=None, raise_for_status_error=None) -> AsyncMock:
    client = AsyncMock()
    resp = MagicMock()
    if raise_for_status_error is not None:
        resp.raise_for_status.side_effect = raise_for_status_error
    if json_return is not None:
        resp.json.return_value = json_return
    client.post = AsyncMock(return_value=resp)
    client.get = AsyncMock(return_value=resp)
    return client


class TestNotifyTierUpdated:
    @pytest.mark.asyncio
    async def test_posts_tier_id_not_computed_tenant_ids(self):
        """tier_service can no longer compute tenant_ids itself (no DB-local
        assignment table) — it must hand the tier_id to auth-service instead
        and let it resolve affected tenants."""
        client = _http_client()
        tier = _tier()

        await tier_service._notify_tier_updated(tier, "http://auth", client)

        client.post.assert_awaited_once()
        args, kwargs = client.post.call_args
        assert args[0] == "http://auth/internal/ppu/tier/quota-limit-updated"
        assert kwargs["json"] == {"tier_name": tier.name, "tier_id": str(tier.id)}

    @pytest.mark.asyncio
    async def test_missing_auth_service_url_or_client_is_a_noop(self):
        tier = _tier()
        await tier_service._notify_tier_updated(tier, "", None)
        await tier_service._notify_tier_updated(tier, "http://auth", None)
        # no exception raised either way — nothing to assert on a plain no-op

    @pytest.mark.asyncio
    async def test_notification_failure_is_logged_not_raised(self):
        client = _http_client(raise_for_status_error=Exception("boom"))
        tier = _tier()

        await tier_service._notify_tier_updated(tier, "http://auth", client)  # must not raise


class TestTenantCountForTier:
    @pytest.mark.asyncio
    async def test_returns_count_from_auth_service(self):
        tier_id = uuid.uuid4()
        client = _http_client(json_return={"count": 3})

        count = await tier_service._tenant_count_for_tier(tier_id, "http://auth", client)

        assert count == 3
        client.get.assert_awaited_once_with(
            f"http://auth/internal/tenants/tier/{tier_id}/count", timeout=5.0
        )

    @pytest.mark.asyncio
    async def test_missing_auth_service_config_fails_closed(self):
        """No auth_service_url/http_client configured must raise, not silently
        report 0 (in-use) tenants — that would let a genuinely in-use tier be
        deleted out from under real tenants."""
        with pytest.raises(HTTPException) as exc_info:
            await tier_service._tenant_count_for_tier(uuid.uuid4(), "", None)
        assert exc_info.value.status_code == 503

    @pytest.mark.asyncio
    async def test_auth_service_call_failure_fails_closed(self):
        client = _http_client(raise_for_status_error=Exception("boom"))

        with pytest.raises(HTTPException) as exc_info:
            await tier_service._tenant_count_for_tier(uuid.uuid4(), "http://auth", client)
        assert exc_info.value.status_code == 503


class TestDeleteTier:
    def _session_with_tier(self, tier):
        session = AsyncMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = tier
        session.execute = AsyncMock(return_value=result)
        session.commit = AsyncMock()
        return session

    @pytest.mark.asyncio
    async def test_deletes_when_tier_not_in_use(self):
        tier = _tier()
        session = self._session_with_tier(tier)
        client = _http_client(json_return={"count": 0})

        await tier_service.delete_tier(str(tier.id), session, "http://auth", client)

        assert tier.is_active is False
        session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_refuses_to_delete_when_tier_in_use(self):
        tier = _tier()
        session = self._session_with_tier(tier)
        client = _http_client(json_return={"count": 1})

        with pytest.raises(HTTPException) as exc_info:
            await tier_service.delete_tier(str(tier.id), session, "http://auth", client)

        assert exc_info.value.status_code == 409
        assert tier.is_active is True
        session.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_invalid_tier_id_400s_before_any_auth_service_call(self):
        session = AsyncMock()
        client = _http_client()

        with pytest.raises(HTTPException) as exc_info:
            await tier_service.delete_tier("not-a-uuid", session, "http://auth", client)

        assert exc_info.value.status_code == 400
        client.get.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_tier_not_found_404s_before_any_auth_service_call(self):
        session = self._session_with_tier(None)
        client = _http_client()

        with pytest.raises(HTTPException) as exc_info:
            await tier_service.delete_tier(str(uuid.uuid4()), session, "http://auth", client)

        assert exc_info.value.status_code == 404
        client.get.assert_not_awaited()
