"""Unit tests for app.services.pay_per_use.tier_service.

ppu_tenant_tier_assignments was dropped (AI4IDS-2923). _fetch_tenant_ids_for_tier
(used by update_tier's best-effort auth-service notification) and delete_tier's
in-use guard both used to query that table directly on `session` — an
UndefinedTableError against a migrated DB, surfacing as a hard 500 on tier
update and tier delete. Both are reconstructed here from tenants.tier_id
(auth-service, via a new auth_db cross-DB param), matching the same fix
already applied to UsageRepository.get_tenant_budgets and auth-service's
TenantService.assign_tenant_tier.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.core.exceptions import ValidationError
from app.models.pay_per_use.tier import Tier
from app.schemas.pay_per_use.tier import TierUpdate
from app.services.pay_per_use import tier_service


# The catalogue is a real collaborator of tier_service now: quota lookups
# resolve a name to an inference_type_id, and responses map ids back to names.
# These tests drive tier_service with a blanket-mocked session, so without this
# the catalogue's own SELECT would be answered with whatever that mock returns.
_CATALOGUE = {"llm": 1, "asr": 2, "nmt": 3, "tts": 4}


@pytest.fixture(autouse=True)
def _stub_inference_type_cache(monkeypatch):
    async def get_id_by_name(_session, name):
        return _CATALOGUE.get((name or "").strip().lower())

    async def get_by_name(_session, name):
        type_id = _CATALOGUE.get((name or "").strip().lower())
        return None if type_id is None else {"id": type_id, "name": name.strip().lower()}

    async def get_name_by_id(_session):
        return {v: k for k, v in _CATALOGUE.items()}

    async def get_ids_by_names(_session, names):
        return {n.strip().lower(): _CATALOGUE.get(n.strip().lower()) for n in names}

    async def get_all(_session):
        return [{"id": v, "name": k} for k, v in _CATALOGUE.items()]

    cache = tier_service.inference_type_cache
    monkeypatch.setattr(cache, "get_id_by_name", get_id_by_name)
    monkeypatch.setattr(cache, "get_by_name", get_by_name)
    monkeypatch.setattr(cache, "get_name_by_id", get_name_by_id)
    monkeypatch.setattr(cache, "get_ids_by_names", get_ids_by_names)
    monkeypatch.setattr(cache, "get_all", get_all)


def _mock_result(*, scalar=None, all_rows=None, first=None):
    r = MagicMock()
    r.scalar_one_or_none.return_value = scalar
    r.scalars.return_value.all.return_value = all_rows or []
    r.all.return_value = all_rows or []
    r.first.return_value = first
    return r


def _tier(*, tier_id=None, name="Gold", is_active=True) -> Tier:
    return Tier(id=tier_id or uuid4(), name=name, description=None, is_active=is_active)


class TestFetchTenantIdsForTier:
    """The exact bug scenario: this used to SELECT from the dropped
    ppu_tenant_tier_assignments table directly."""

    @pytest.mark.asyncio
    async def test_auth_db_none_returns_empty_without_querying(self):
        result = await tier_service._fetch_tenant_ids_for_tier(uuid4(), None)

        assert result == []

    @pytest.mark.asyncio
    async def test_queries_tenants_tier_id_not_dropped_table(self):
        tier_id = uuid4()
        row1, row2 = MagicMock(id=2), MagicMock(id=5)
        auth_db = AsyncMock()
        auth_db.execute = AsyncMock(return_value=_mock_result(all_rows=[row1, row2]))

        result = await tier_service._fetch_tenant_ids_for_tier(tier_id, auth_db)

        assert result == [2, 5]
        query_sql = str(auth_db.execute.await_args.args[0])
        assert "FROM tenants" in query_sql
        assert "ppu_tenant_tier_assignments" not in query_sql
        assert auth_db.execute.await_args.args[1] == {"tier_id": tier_id}


class TestNotifyTierUpdated:
    @pytest.mark.asyncio
    async def test_missing_auth_service_url_or_client_skips_entirely(self):
        """No notification configured — must not touch auth_db at all."""
        tier = _tier()
        auth_db = AsyncMock()

        await tier_service._notify_tier_updated(tier, "", None, auth_db)

        auth_db.execute.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_auth_db_query_failure_degrades_without_raising(self):
        """Regression: previously an UndefinedTableError from the dropped
        table propagated straight out of this function (only the HTTP call
        was try/except'd), turning a best-effort notification into a hard
        500 for the whole tier update. The DB read must now be covered by
        the same best-effort guard as the HTTP call."""
        tier = _tier()
        auth_db = AsyncMock()
        auth_db.execute = AsyncMock(side_effect=RuntimeError("relation does not exist"))
        http_client = AsyncMock()

        await tier_service._notify_tier_updated(
            tier, "http://auth-service", http_client, auth_db
        )

        http_client.post.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_notifies_with_resolved_tenant_ids(self):
        tier = _tier(name="Platinum")
        row = MagicMock(id=7)
        auth_db = AsyncMock()
        auth_db.execute = AsyncMock(return_value=_mock_result(all_rows=[row]))
        http_client = AsyncMock()
        http_client.post = AsyncMock(return_value=MagicMock(raise_for_status=MagicMock()))

        await tier_service._notify_tier_updated(
            tier, "http://auth-service", http_client, auth_db
        )

        http_client.post.assert_awaited_once()
        _, kwargs = http_client.post.await_args
        assert kwargs["json"]["tenant_ids"] == [7]
        assert kwargs["json"]["tier_name"] == "Platinum"


class TestUpdateTier:
    @pytest.mark.asyncio
    async def test_quota_change_notification_failure_does_not_fail_the_update(self):
        """End-to-end: a quota change on update_tier triggers the
        notification path; even if auth_db blows up fetching tenant_ids,
        update_tier itself must still return successfully (the tier write
        already committed by that point)."""
        tier_id = uuid4()
        tier = _tier(tier_id=tier_id)
        session = AsyncMock()
        session.execute = AsyncMock(return_value=_mock_result(scalar=tier, all_rows=[]))
        session.commit = AsyncMock()
        session.refresh = AsyncMock()

        auth_db = AsyncMock()
        auth_db.execute = AsyncMock(side_effect=RuntimeError("relation does not exist"))
        http_client = AsyncMock()

        body = TierUpdate(tier_id=str(tier_id), cancel_pending_quota=["llm"])

        result = await tier_service.update_tier(
            body,
            session,
            updated_by="admin",
            auth_service_url="http://auth-service",
            http_client=http_client,
            auth_db=auth_db,
        )

        assert result.id == str(tier_id)
        http_client.post.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_no_quota_change_skips_notification_entirely(self):
        """A name/description-only update must not touch auth_db at all —
        confirms the notification path (and its auth_db dependency) is only
        reached when actually needed."""
        tier_id = uuid4()
        tier = _tier(tier_id=tier_id)
        session = AsyncMock()
        session.execute = AsyncMock(return_value=_mock_result(scalar=tier, all_rows=[]))
        session.commit = AsyncMock()
        session.refresh = AsyncMock()
        auth_db = AsyncMock()

        body = TierUpdate(tier_id=str(tier_id), name="Renamed")

        await tier_service.update_tier(
            body, session, updated_by="admin", auth_db=auth_db
        )

        auth_db.execute.assert_not_awaited()


class TestDeleteTier:
    @pytest.mark.asyncio
    async def test_invalid_uuid_rejected(self):
        with pytest.raises(HTTPException) as exc_info:
            await tier_service.delete_tier("not-a-uuid", AsyncMock(), AsyncMock())
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_unknown_tier_rejected(self):
        session = AsyncMock()
        session.execute = AsyncMock(return_value=_mock_result(scalar=None))
        with pytest.raises(HTTPException) as exc_info:
            await tier_service.delete_tier(str(uuid4()), session, AsyncMock())
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_auth_db_none_fails_closed(self):
        """The exact bug scenario, made safe rather than silently wrong:
        without auth_db there is no way to verify no tenant is still on this
        tier, so this must reject the delete rather than let it proceed
        unchecked (or crash on the dropped table, as it did before)."""
        tier_id = uuid4()
        tier = _tier(tier_id=tier_id)
        session = AsyncMock()
        session.execute = AsyncMock(return_value=_mock_result(scalar=tier))

        with pytest.raises(ValidationError) as exc_info:
            await tier_service.delete_tier(str(tier_id), session, None)

        assert exc_info.value.code == "AUTH_DB_NOT_CONFIGURED"
        session.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_tier_still_assigned_to_a_tenant_rejected(self):
        tier_id = uuid4()
        tier = _tier(tier_id=tier_id)
        session = AsyncMock()
        session.execute = AsyncMock(return_value=_mock_result(scalar=tier))
        session.commit = AsyncMock()
        auth_db = AsyncMock()
        auth_db.execute = AsyncMock(return_value=_mock_result(first=(1,)))

        with pytest.raises(HTTPException) as exc_info:
            await tier_service.delete_tier(str(tier_id), session, auth_db)

        assert exc_info.value.status_code == 409
        session.commit.assert_not_awaited()
        query_sql = str(auth_db.execute.await_args.args[0])
        assert "FROM tenants" in query_sql
        assert "ppu_tenant_tier_assignments" not in query_sql

    @pytest.mark.asyncio
    async def test_tier_with_no_tenants_deletes_successfully(self):
        tier_id = uuid4()
        tier = _tier(tier_id=tier_id, name="Bronze")
        session = AsyncMock()
        session.execute = AsyncMock(return_value=_mock_result(scalar=tier))
        session.commit = AsyncMock()
        auth_db = AsyncMock()
        auth_db.execute = AsyncMock(return_value=_mock_result(first=None))

        await tier_service.delete_tier(str(tier_id), session, auth_db)

        assert tier.is_active is False
        session.commit.assert_awaited_once()
