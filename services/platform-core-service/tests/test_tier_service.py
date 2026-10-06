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

import httpx
import pytest
from fastapi import HTTPException

from app.core.constants import TierStatus
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


def _tier(*, tier_id=None, name="Gold", status=TierStatus.INACTIVE) -> Tier:
    t = Tier(id=tier_id or uuid4(), name=name, description=None)
    t.status = status
    return t


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


class _SessionContext:
    def __init__(self, session):
        self.session = session

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, *exc):
        return False


def _runtime_with_tenants(rows=None, error=None):
    auth_session = AsyncMock()
    if error is not None:
        auth_session.execute = AsyncMock(side_effect=error)
    else:
        result = MagicMock()
        result.mappings.return_value.all.return_value = rows or []
        auth_session.execute = AsyncMock(return_value=result)
    runtime = MagicMock()
    runtime.auth_session_factory = lambda: _SessionContext(auth_session)
    runtime.failures.record = AsyncMock()
    return runtime


class TestPublishQuotaLimitUpdated:
    """QUOTA_LIMIT_UPDATED: one STATE pair per tenant on the tier x changed
    model task type, handed to the shared pipeline (emit_state_bulk)."""

    @pytest.mark.asyncio
    async def test_fans_out_one_pair_per_tenant_and_changed_task_type(self, monkeypatch):
        runtime = _runtime_with_tenants(rows=[
            {"tenant_id": "1", "tenant_name": "IIT Madras"},
            {"tenant_id": "2", "tenant_name": "IISc"},
        ])
        monkeypatch.setattr(tier_service, "get_notification_runtime", lambda: runtime)
        emit = AsyncMock()
        monkeypatch.setattr(tier_service, "emit_state_bulk", emit)

        await tier_service._publish_quota_limit_updated(
            "tier-1", "Gold",
            [{"inference_name": "ASR", "previous": 1000, "current": 2000},
             {"inference_name": "nmt", "previous": 500, "current": 800}],
        )

        name, items = emit.await_args.args
        assert name.value == "QUOTA_LIMIT_UPDATED"
        assert len(items) == 4
        first = items[0]
        assert first.tenant_id == "1" and first.tenant_name == "IIT Madras"
        assert first.subject == {"model_task_type": "asr"}
        assert first.new_state["from_quota"] == "1000" and first.new_state["to_quota"] == "2000"
        assert first.new_state["tier_id"] == "tier-1"
        assert first.details[0] == "Gold"
        assert first.details[1] == ["ASR: changed from 1,000 to 2,000"]
        assert "tier tier-1" in emit.await_args.kwargs["summary"]

    def test_tenant_name_is_the_institution_not_the_contact(self):
        """Q-D2's tenant_name fills the email subject and headline: it must be
        tenants.organisation (the institution), never tenants.name (the contact)."""
        sql = tier_service._TENANTS_ON_TIER_SQL.text
        assert "organisation AS tenant_name" in sql
        assert " name AS tenant_name" not in sql

    @pytest.mark.asyncio
    async def test_tenant_lookup_failure_is_a_source_failure_row(self, monkeypatch):
        runtime = _runtime_with_tenants(error=RuntimeError("auth db down"))
        monkeypatch.setattr(tier_service, "get_notification_runtime", lambda: runtime)
        emit = AsyncMock()
        monkeypatch.setattr(tier_service, "emit_state_bulk", emit)

        await tier_service._publish_quota_limit_updated(
            "tier-1", "Gold", [{"inference_name": "asr", "previous": 1, "current": 2}]
        )

        emit.assert_not_awaited()
        stage, code = runtime.failures.record.await_args.args
        assert stage.value == "SOURCE" and code.value == "TENANT_LOOKUP_FAILED"

    @pytest.mark.asyncio
    async def test_no_tenants_on_the_tier_sends_nothing(self, monkeypatch):
        runtime = _runtime_with_tenants(rows=[])
        monkeypatch.setattr(tier_service, "get_notification_runtime", lambda: runtime)
        emit = AsyncMock()
        monkeypatch.setattr(tier_service, "emit_state_bulk", emit)

        await tier_service._publish_quota_limit_updated(
            "tier-1", "Gold", [{"inference_name": "asr", "previous": 1, "current": 2}]
        )

        emit.assert_not_awaited()


class TestUpdateTier:
    @pytest.mark.asyncio
    async def test_quota_change_notification_failure_does_not_fail_the_update(self):
        """The notification runs in the background after the tier commit, so
        update_tier returns successfully whatever happens to it."""
        tier_id = uuid4()
        tier = _tier(tier_id=tier_id)
        session = AsyncMock()
        session.execute = AsyncMock(return_value=_mock_result(scalar=tier, all_rows=[]))
        session.commit = AsyncMock()
        session.refresh = AsyncMock()

        body = TierUpdate(tier_id=str(tier_id), cancel_pending_quota=["llm"])

        result = await tier_service.update_tier(body, session, updated_by="admin")

        assert result.id == str(tier_id)

    @pytest.mark.asyncio
    async def test_no_quota_change_skips_notification_entirely(self, monkeypatch):
        """A name/description-only update never schedules QUOTA_LIMIT_UPDATED."""
        tier_id = uuid4()
        tier = _tier(tier_id=tier_id)
        session = AsyncMock()
        session.execute = AsyncMock(return_value=_mock_result(scalar=tier, all_rows=[]))
        session.commit = AsyncMock()
        session.refresh = AsyncMock()
        scheduled = []
        monkeypatch.setattr(tier_service, "notifications_configured", lambda: True)
        monkeypatch.setattr(tier_service, "run_in_background", scheduled.append)

        body = TierUpdate(tier_id=str(tier_id), name="Renamed")

        await tier_service.update_tier(body, session, updated_by="admin")

        assert scheduled == []


class TestDeleteTier:
    @pytest.mark.asyncio
    async def test_invalid_uuid_rejected(self):
        with pytest.raises(HTTPException) as exc_info:
            await tier_service.update_tier_status(
                "not-a-uuid", TierStatus.DELETED, AsyncMock(), auth_db=AsyncMock()
            )
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_unknown_tier_rejected(self):
        session = AsyncMock()
        session.execute = AsyncMock(return_value=_mock_result(scalar=None))
        with pytest.raises(HTTPException) as exc_info:
            await tier_service.update_tier_status(
                str(uuid4()), TierStatus.DELETED, session, auth_db=AsyncMock()
            )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_auth_db_none_fails_closed(self):
        """The exact bug scenario, made safe rather than silently wrong:
        without auth_db there is no way to verify no tenant is still on this
        tier, so this must reject the delete rather than let it proceed
        unchecked (or crash on the dropped table, as it did before)."""
        tier_id = uuid4()
        tier = _tier(tier_id=tier_id, status=TierStatus.DEACTIVATED)
        session = AsyncMock()
        session.execute = AsyncMock(return_value=_mock_result(scalar=tier))

        with pytest.raises(ValidationError) as exc_info:
            await tier_service.update_tier_status(
                str(tier_id), TierStatus.DELETED, session, auth_db=None
            )

        assert exc_info.value.code == "AUTH_DB_NOT_CONFIGURED"
        session.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_tier_still_assigned_to_a_tenant_rejected(self):
        tier_id = uuid4()
        tier = _tier(tier_id=tier_id, status=TierStatus.DEACTIVATED)
        session = AsyncMock()
        session.execute = AsyncMock(return_value=_mock_result(scalar=tier))
        session.commit = AsyncMock()
        auth_db = AsyncMock()
        auth_db.execute = AsyncMock(return_value=_mock_result(first=(1,)))

        with pytest.raises(HTTPException) as exc_info:
            await tier_service.update_tier_status(
                str(tier_id), TierStatus.DELETED, session, auth_db=auth_db
            )

        assert exc_info.value.status_code == 409
        session.commit.assert_not_awaited()
        query_sql = str(auth_db.execute.await_args.args[0])
        assert "FROM tenants" in query_sql
        assert "ppu_tenant_tier_assignments" not in query_sql

    @pytest.mark.asyncio
    async def test_tier_with_no_tenants_deletes_successfully(self):
        tier_id = uuid4()
        tier = _tier(tier_id=tier_id, name="Bronze", status=TierStatus.DEACTIVATED)
        session = AsyncMock()
        session.execute = AsyncMock(return_value=_mock_result(scalar=tier))
        session.commit = AsyncMock()
        auth_db = AsyncMock()
        auth_db.execute = AsyncMock(return_value=_mock_result(first=None))

        await tier_service.update_tier_status(
            str(tier_id), TierStatus.DELETED, session, auth_db=auth_db
        )

        assert tier.status == TierStatus.DELETED
        session.commit.assert_awaited_once()


class TestNotifyTierReactivated:
    @pytest.mark.asyncio
    async def test_skips_when_no_url_or_client(self):
        auth_db = AsyncMock()
        await tier_service._notify_tier_reactivated(_tier(), "", None, auth_db)
        auth_db.execute.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_auth_db_failure_skips_without_raising(self):
        auth_db = AsyncMock()
        auth_db.execute = AsyncMock(side_effect=RuntimeError("gone"))
        http_client = AsyncMock()

        await tier_service._notify_tier_reactivated(
            _tier(), "http://auth-service", http_client, auth_db
        )

        http_client.post.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_retries_on_transient_error_and_succeeds(self, monkeypatch):
        auth_db = AsyncMock()
        auth_db.execute = AsyncMock(return_value=_mock_result(all_rows=[]))
        ok = MagicMock(raise_for_status=MagicMock())
        http_client = AsyncMock()
        http_client.post = AsyncMock(side_effect=[httpx.ConnectError("refused"), ok])

        slept = []

        async def _fake_sleep(s):
            slept.append(s)

        monkeypatch.setattr("asyncio.sleep", _fake_sleep)

        await tier_service._notify_tier_reactivated(
            _tier(), "http://auth-service", http_client, auth_db
        )

        assert http_client.post.await_count == 2
        assert len(slept) == 1

    @pytest.mark.asyncio
    async def test_no_retry_on_4xx(self, monkeypatch):
        auth_db = AsyncMock()
        auth_db.execute = AsyncMock(return_value=_mock_result(all_rows=[]))
        resp = MagicMock(status_code=404)
        http_client = AsyncMock()
        http_client.post = AsyncMock(
            side_effect=httpx.HTTPStatusError("not found", request=MagicMock(), response=resp)
        )

        slept = []

        async def _fake_sleep(s):
            slept.append(s)

        monkeypatch.setattr("asyncio.sleep", _fake_sleep)

        await tier_service._notify_tier_reactivated(
            _tier(), "http://auth-service", http_client, auth_db
        )

        assert http_client.post.await_count == 1
        assert not slept

    @pytest.mark.asyncio
    async def test_error_logged_after_max_attempts(self, monkeypatch, caplog):
        import logging

        auth_db = AsyncMock()
        auth_db.execute = AsyncMock(return_value=_mock_result(all_rows=[]))
        http_client = AsyncMock()
        http_client.post = AsyncMock(side_effect=httpx.ConnectError("refused"))

        monkeypatch.setattr("asyncio.sleep", AsyncMock())

        with caplog.at_level(logging.ERROR, logger="app.services.pay_per_use.tier_service"):
            await tier_service._notify_tier_reactivated(
                _tier(), "http://auth-service", http_client, auth_db
            )

        assert http_client.post.await_count == tier_service._REACTIVATE_NOTIFY_MAX_ATTEMPTS
        assert any("failed after" in r.message for r in caplog.records if r.levelno >= logging.ERROR)


class TestUpsertQuotasReportsOnlyChanges:
    """QUOTA_LIMIT_UPDATED is sent only for quotas that actually change,
    once per task type (a repeated type in one body would otherwise put
    two rows with the same key into one bulk claim)."""

    @staticmethod
    def _session(existing):
        from types import SimpleNamespace

        rows = dict(existing)

        async def execute(stmt):
            type_id = next(
                clause.right.value for clause in stmt.whereclause.clauses
                if clause.left.key == "inference_type_id"
            )
            return SimpleNamespace(scalar_one_or_none=lambda: rows.get(type_id))

        return SimpleNamespace(execute=execute)

    @staticmethod
    def _quota(task, limit):
        from types import SimpleNamespace

        return SimpleNamespace(modelTaskType=task, limit=limit)

    @staticmethod
    def _existing(monthly, pending=None):
        from types import SimpleNamespace

        return SimpleNamespace(monthly_quota=monthly, pending_monthly_quota=pending, updated_by=None)

    @pytest.mark.asyncio
    async def test_unchanged_quota_is_not_reported(self):
        asr = self._existing(1000)
        changes = await tier_service._upsert_quotas(
            self._session({2: asr}), Tier(id=uuid4(), name="Gold"), [self._quota("ASR", 1000)], "admin"
        )
        assert changes == []
        assert asr.pending_monthly_quota == 1000

    @pytest.mark.asyncio
    async def test_resending_an_already_scheduled_quota_is_not_reported_again(self):
        changes = await tier_service._upsert_quotas(
            self._session({2: self._existing(1000, pending=2000)}), Tier(id=uuid4(), name="Gold"),
            [self._quota("asr", 2000)], "admin",
        )
        assert changes == []

    @pytest.mark.asyncio
    async def test_changed_quota_is_reported_once_per_task_type(self):
        changes = await tier_service._upsert_quotas(
            self._session({2: self._existing(1000), 3: self._existing(500)}), Tier(id=uuid4(), name="Gold"),
            [self._quota("ASR", 1500), self._quota("asr", 2000), self._quota("nmt", 500)], "admin",
        )
        assert changes == [{"inference_name": "asr", "previous": 1000, "current": 2000}]
