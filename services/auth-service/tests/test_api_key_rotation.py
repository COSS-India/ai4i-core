"""API key rotation: one row, two live values.

POST /auth/api-keys/{id}/rotate moves api_key to rotated_key and issues a new
api_key on the same row, so budget, quota, permissions and billing (all keyed
by api_key.id) carry over unchanged. The old value keeps working until
rotated_key_expires_at (the caller's grace_days, rejected with 422 when it
would run past the key's own expiry) or until the whole key is revoked. Until then every Redis write for
the row must reach both values' entries, and the validate DB fallback must
accept the old value.
"""

from contextlib import asynccontextmanager
from types import SimpleNamespace
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from app.core.exceptions import AppError
from app.models.api_key import APIKey
from app.models.application import Application, ApplicationStatus
from app.models.tenant import Tenant, TenantStatus
from app.repositories.api_key_repository import APIKeyRepository
from app.services.api_key_service import APIKeyService

_OLD = "a" * 32
_NEW = "b" * 32


def _key(
    *,
    rotated_key: str | None = None,
    rotated_key_expires_at: datetime | None = None,
    expires_at: datetime | None = ...,
    is_active: bool = True,
    cached_data: dict | None = ...,
) -> APIKey:
    return APIKey(
        id=7,
        application_id=1,
        key_name="prod",
        api_key=_OLD,
        permissions=[1],
        is_active=is_active,
        expires_at=(datetime.now(timezone.utc) + timedelta(days=300)) if expires_at is ... else expires_at,
        rotated_key=rotated_key,
        rotated_key_expires_at=rotated_key_expires_at,
        cached_data={"id": 7, "api_key": _OLD, "budget-exhausted": "1"} if cached_data is ... else cached_data,
    )


def _rotated_key(*, days_left: float = 5) -> APIKey:
    """A row already rotated: api_key is the new value, rotated_key the old one."""
    key = _key(
        rotated_key=_OLD,
        rotated_key_expires_at=datetime.now(timezone.utc) + timedelta(days=days_left),
    )
    key.api_key = _NEW
    return key


def _service(key: APIKey, *, app_status=ApplicationStatus.ACTIVE, tenant_status=TenantStatus.ACTIVE):
    repo = AsyncMock()
    cache = AsyncMock()
    cache.get_api_key_cache = AsyncMock(return_value=None)
    applications = AsyncMock()
    applications.get_by_id = AsyncMock(
        return_value=Application(id=1, tenant_id=3, name="App", status=app_status)
    )
    tenants = AsyncMock()
    tenants.get_operational_fields = AsyncMock(
        return_value=Tenant(id=3, name="T", organisation="T", email="t@example.invalid", status=tenant_status)
    )
    repo.key_value_in_use = AsyncMock(return_value=False)

    async def _rotate(key_id, current, new, rotated_expires_at, updated_by):
        # Mirror the UPDATE onto the in-memory row, as refresh() would load it
        # (cached_data's api_key rewritten in place by jsonb_set).
        key.rotated_key, key.api_key = key.api_key, new
        key.rotated_key_expires_at = rotated_expires_at
        if key.cached_data is not None:
            key.cached_data = {**key.cached_data, "api_key": new}
        return True

    repo.rotate = AsyncMock(side_effect=_rotate)
    svc = APIKeyService(repo, cache, applications, tenants)
    return svc, repo, cache


def _set_values(cache) -> dict[str, int]:
    """key value -> TTL for every set_api_key_cache call."""
    return {c.args[0]: c.args[1] for c in cache.set_api_key_cache.await_args_list}


class TestCacheKeyValues:
    def test_never_rotated_is_just_api_key(self) -> None:
        assert _key().cache_key_values() == [_OLD]

    def test_live_rotated_key_is_included(self) -> None:
        assert _rotated_key().cache_key_values() == [_NEW, _OLD]

    def test_expired_rotated_key_is_excluded(self) -> None:
        assert _rotated_key(days_left=-1).cache_key_values() == [_NEW]


class TestRotate:
    @pytest.mark.asyncio
    async def test_new_value_is_issued_and_old_value_moves_to_rotated_key(self, monkeypatch) -> None:
        monkeypatch.setattr(APIKeyService, "generate_api_key", staticmethod(lambda: _NEW))
        key = _key()
        svc, repo, cache = _service(key)

        new_value, row = await svc.rotate_by_obj(key, actor_user_id="u-1", grace_days=7)

        assert new_value == _NEW
        _id, current, new, rotated_expires_at, updated_by = repo.rotate.await_args.args
        assert (current, new, updated_by) == (_OLD, _NEW, "u-1")
        expected = datetime.now(timezone.utc) + timedelta(days=7)
        assert abs((rotated_expires_at - expected).total_seconds()) < 5
        repo.commit.assert_awaited()
        repo.refresh.assert_awaited_with(key)
        assert row.api_key == _NEW and row.rotated_key == _OLD

    def test_rotate_rewrites_only_the_api_key_field_of_cached_data(self) -> None:
        """A wholesale cached_data overwrite would drop a billing flag written
        concurrently between reading the row and rotating it."""
        from sqlalchemy.dialects import postgresql

        from app.repositories.api_key_repository import APIKeyRepository

        captured = {}

        class _Session:
            async def execute(self, stmt):
                captured["sql"] = str(stmt.compile(dialect=postgresql.dialect()))
                result = MagicMock()
                result.rowcount = 1
                return result

        import asyncio

        asyncio.run(
            APIKeyRepository(_Session()).rotate(
                7, _OLD, _NEW, datetime.now(timezone.utc), "u-1"
            )
        )
        assert "cached_data=jsonb_set(api_key.cached_data" in captured["sql"]
        # A revoke that committed first must make the rotation a no-op (409).
        assert "api_key.is_active IS true" in captured["sql"]

    @pytest.mark.asyncio
    async def test_revoke_landing_during_rotation_drops_the_new_entries(self, monkeypatch) -> None:
        monkeypatch.setattr(APIKeyService, "generate_api_key", staticmethod(lambda: _NEW))
        key = _key()
        svc, repo, cache = _service(key)
        refreshes = iter([None, "revoked"])

        async def _refresh(obj):
            # First refresh: right after commit. Second: the post-write
            # re-check, by which time a revoke has committed.
            if next(refreshes) == "revoked":
                obj.is_active = False
            return obj

        repo.refresh = AsyncMock(side_effect=_refresh)

        await svc.rotate_by_obj(key, actor_user_id="u-1", grace_days=7)

        assert set(_set_values(cache)) == {_NEW, _OLD}
        cache.delete_api_key_cache.assert_has_awaits([call(_NEW), call(_OLD)], any_order=True)

    @pytest.mark.asyncio
    async def test_both_values_get_the_same_redis_fields_with_their_own_ttl(self, monkeypatch) -> None:
        monkeypatch.setattr(APIKeyService, "generate_api_key", staticmethod(lambda: _NEW))
        key = _key()
        svc, _repo, cache = _service(key)

        await svc.rotate_by_obj(key, actor_user_id="u-1", grace_days=7)

        ttls = _set_values(cache)
        assert set(ttls) == {_NEW, _OLD}
        payloads = {c.args[0]: c.args[2] for c in cache.set_api_key_cache.await_args_list}
        assert payloads[_NEW] == payloads[_OLD]
        assert payloads[_NEW]["budget-exhausted"] == "1"
        # Old value's entry ends with its rotation window, not the key's expiry.
        assert ttls[_OLD] <= 7 * 86400
        assert ttls[_NEW] > ttls[_OLD]

    @pytest.mark.asyncio
    async def test_live_previous_value_is_409(self) -> None:
        key = _rotated_key()
        svc, repo, _cache = _service(key)

        with pytest.raises(AppError) as exc:
            await svc.rotate_by_obj(key, actor_user_id="u-1", grace_days=7)

        assert exc.value.status_code == 409
        assert exc.value.code == "ROTATION_IN_PROGRESS"
        repo.rotate.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_expired_previous_value_allows_a_new_rotation(self, monkeypatch) -> None:
        monkeypatch.setattr(APIKeyService, "generate_api_key", staticmethod(lambda: "c" * 32))
        key = _rotated_key(days_left=-1)
        svc, repo, _cache = _service(key)

        new_value, _row = await svc.rotate_by_obj(key, actor_user_id="u-1", grace_days=7)

        assert new_value == "c" * 32
        repo.rotate.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_losing_a_concurrent_rotation_is_409(self) -> None:
        key = _key()
        svc, repo, _cache = _service(key)
        repo.rotate = AsyncMock(return_value=False)

        with pytest.raises(AppError) as exc:
            await svc.rotate_by_obj(key, actor_user_id="u-1", grace_days=7)

        assert exc.value.status_code == 409
        repo.commit.assert_not_awaited()

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "key_kwargs, service_kwargs",
        [
            ({"is_active": False}, {}),
            ({"expires_at": datetime.now(timezone.utc) - timedelta(days=1)}, {}),
            ({}, {"app_status": ApplicationStatus.INACTIVE}),
            ({}, {"tenant_status": TenantStatus.SUSPENDED}),
        ],
    )
    async def test_inactive_key_is_not_rotatable(self, key_kwargs, service_kwargs) -> None:
        key = _key(**key_kwargs)
        svc, repo, _cache = _service(key, **service_kwargs)

        with pytest.raises(AppError) as exc:
            await svc.rotate_by_obj(key, actor_user_id="u-1", grace_days=7)

        assert (exc.value.status_code, exc.value.code) == (409, "API_KEY_NOT_ROTATABLE")
        repo.rotate.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_new_value_avoids_any_value_already_in_use(self, monkeypatch) -> None:
        values = iter(["d" * 32, _NEW])
        monkeypatch.setattr(APIKeyService, "generate_api_key", staticmethod(lambda: next(values)))
        key = _key()
        svc, repo, _cache = _service(key)
        repo.key_value_in_use = AsyncMock(side_effect=[True, False])

        new_value, _row = await svc.rotate_by_obj(key, actor_user_id="u-1", grace_days=7)

        assert new_value == _NEW

    @pytest.mark.asyncio
    async def test_redis_failure_still_returns_the_new_key_and_drops_both_entries(self, monkeypatch) -> None:
        monkeypatch.setattr(APIKeyService, "generate_api_key", staticmethod(lambda: _NEW))
        key = _key()
        svc, _repo, cache = _service(key)
        cache.set_api_key_cache = AsyncMock(side_effect=ConnectionError("redis down"))

        new_value, _row = await svc.rotate_by_obj(key, actor_user_id="u-1", grace_days=7)

        assert new_value == _NEW
        cache.delete_api_key_cache.assert_has_awaits([call(_NEW), call(_OLD)], any_order=True)

    @pytest.mark.asyncio
    async def test_zero_day_window_stops_the_old_value_now(self, monkeypatch) -> None:
        monkeypatch.setattr(APIKeyService, "generate_api_key", staticmethod(lambda: _NEW))
        key = _key()
        svc, _repo, cache = _service(key)

        await svc.rotate_by_obj(key, actor_user_id="u-1", grace_days=0)

        assert set(_set_values(cache)) == {_NEW}
        cache.delete_api_key_cache.assert_awaited_with(_OLD)


class TestWritersReachBothValues:
    @pytest.mark.asyncio
    async def test_budget_exhausted_for_key(self) -> None:
        key = _rotated_key()
        repo, cache = AsyncMock(), AsyncMock()
        repo.get_by_id = AsyncMock(return_value=key)

        await APIKeyService(repo, cache).set_budget_exhausted_for_key(7, True)

        cache.patch_api_key_cache_field.assert_has_awaits(
            [call(_NEW, "budget-exhausted", "1"), call(_OLD, "budget-exhausted", "1")]
        )

    @pytest.mark.asyncio
    async def test_tenant_wide_patch_quota_tier_budget_window(self) -> None:
        key = _rotated_key()
        repo, cache = AsyncMock(), AsyncMock()
        repo.list_active_keys_for_tenant = AsyncMock(return_value=[key])

        await APIKeyService(repo, cache).set_quota_exhausted_for_tenant(3, "nmt")

        cache.patch_api_key_cache_field.assert_has_awaits(
            [call(_NEW, "quota-nmt", "1"), call(_OLD, "quota-nmt", "1")]
        )

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "method, args, field, value, patch_name",
        [
            ("set_tier_id_for_tenant", ("tier-2",), "tier_id", "tier-2", "patch_api_key_cache_field"),
            ("mark_tier_unassigned_for_tenant", (), "tier_id", "", "patch_api_key_cache_field_if_present"),
            (
                "set_budget_effective_to_for_tenant",
                (datetime(2027, 1, 1, tzinfo=timezone.utc),),
                "budget_effective_to",
                "2027-01-01T00:00:00+00:00",
                "patch_api_key_cache_field",
            ),
        ],
    )
    async def test_tier_assign_unassign_and_budget_window(self, method, args, field, value, patch_name) -> None:
        key = _rotated_key()
        repo, cache = AsyncMock(), AsyncMock()
        repo.list_active_keys_for_tenant = AsyncMock(return_value=[key])

        await getattr(APIKeyService(repo, cache), method)(3, *args)

        getattr(cache, patch_name).assert_has_awaits([call(_NEW, field, value), call(_OLD, field, value)])

    @pytest.mark.asyncio
    async def test_tenant_deactivate_deletes_every_returned_value(self) -> None:
        repo, cache, applications = AsyncMock(), AsyncMock(), AsyncMock()
        applications.list_by_tenant = AsyncMock(return_value=[Application(id=1, tenant_id=3, name="A")])
        # The repository returns api_key and rotated_key for each revoked row.
        repo.revoke_active_for_applications = AsyncMock(return_value=[_NEW, _OLD])

        await APIKeyService(repo, cache, applications).revoke_keys_for_tenant(3)

        cache.delete_api_key_cache.assert_has_awaits([call(_NEW), call(_OLD)])

    @pytest.mark.asyncio
    async def test_application_deactivate_flags_every_returned_value(self) -> None:
        repo, cache = AsyncMock(), AsyncMock()
        # patch_cached_data_field_for_keys returns api_key plus the live rotated key.
        repo.patch_cached_data_field_for_keys = AsyncMock(return_value=[_NEW, _OLD])

        await APIKeyService(repo, cache).set_budget_exhausted_for_keys([7], True)

        cache.patch_api_key_cache_field.assert_has_awaits(
            [call(_NEW, "budget-exhausted", "1"), call(_OLD, "budget-exhausted", "1")]
        )

    @pytest.mark.asyncio
    async def test_expired_rotated_value_is_not_patched(self) -> None:
        key = _rotated_key(days_left=-1)
        repo, cache = AsyncMock(), AsyncMock()
        repo.list_active_keys_for_tenant = AsyncMock(return_value=[key])

        await APIKeyService(repo, cache).set_quota_exhausted_for_tenant(3, "nmt")

        cache.patch_api_key_cache_field.assert_awaited_once_with(_NEW, "quota-nmt", "1")

    @pytest.mark.asyncio
    async def test_quota_clear_for_tenant(self, monkeypatch) -> None:
        from app.services import api_key_service as module

        async def _names():
            return ["quota-nmt"]

        monkeypatch.setattr(module, "_quota_field_names", _names)
        key = _rotated_key()
        repo, cache = AsyncMock(), AsyncMock()
        repo.list_active_keys_for_tenant = AsyncMock(return_value=[key])

        await APIKeyService(repo, cache).clear_quota_flags_for_tenant(3)

        cache.delete_api_key_cache_fields.assert_has_awaits(
            [call(_NEW, ["quota-nmt"]), call(_OLD, ["quota-nmt"])]
        )

    @pytest.mark.asyncio
    async def test_monthly_quota_reset(self, monkeypatch) -> None:
        from app.services import api_key_service as module

        async def _names():
            return ["quota-nmt"]

        monkeypatch.setattr(module, "_quota_field_names", _names)
        key = _rotated_key()
        repo, cache = AsyncMock(), AsyncMock()
        repo.list_active_keys = AsyncMock(return_value=[key])

        await APIKeyService(repo, cache).reset_all_quota_fields()

        cache.delete_api_key_cache_fields_bulk.assert_awaited_once_with([_NEW, _OLD], ["quota-nmt"])

    @pytest.mark.asyncio
    async def test_revoke_deletes_both_entries(self) -> None:
        key = _rotated_key()
        repo, cache = AsyncMock(), AsyncMock()

        await APIKeyService(repo, cache).revoke_by_obj(key)

        cache.delete_api_key_cache.assert_has_awaits([call(_NEW), call(_OLD)])

    @pytest.mark.asyncio
    async def test_revoke_uses_the_values_the_row_holds_after_commit(self) -> None:
        """Revoke loaded the row before a concurrent rotation committed; it
        must still delete the rotation's new value."""
        key = _key()  # as loaded: api_key=_OLD, never rotated
        repo, cache = AsyncMock(), AsyncMock()

        async def _refresh(obj):
            obj.api_key, obj.rotated_key = _NEW, _OLD
            return obj

        repo.refresh = AsyncMock(side_effect=_refresh)

        await APIKeyService(repo, cache).revoke_by_obj(key)

        cache.delete_api_key_cache.assert_has_awaits([call(_NEW), call(_OLD)])

    @pytest.mark.asyncio
    async def test_tenant_suspend_evicts_both_entries(self) -> None:
        key = _rotated_key()
        repo, cache = AsyncMock(), AsyncMock()
        repo.list_active_keys_for_tenant = AsyncMock(return_value=[key])

        await APIKeyService(repo, cache).evict_keys_for_tenant(3)

        cache.delete_api_key_cache.assert_has_awaits([call(_NEW), call(_OLD)])

    @pytest.mark.asyncio
    async def test_application_deactivate_evicts_both_entries(self) -> None:
        key = _rotated_key()
        repo, cache = AsyncMock(), AsyncMock()
        repo.list_by_application = AsyncMock(return_value=[key])

        await APIKeyService(repo, cache).evict_keys_for_application(1)

        cache.delete_api_key_cache.assert_has_awaits([call(_NEW), call(_OLD)])

    @pytest.mark.asyncio
    async def test_key_edit_refreshes_both_entries(self) -> None:
        key = _rotated_key()
        svc, _repo, cache = _service(key)

        await svc.update_key_by_obj(key, {"key_name": "renamed"})

        assert set(_set_values(cache)) == {_NEW, _OLD}

    @pytest.mark.asyncio
    async def test_shortening_expiry_also_shortens_the_rotation_window(self) -> None:
        key = _rotated_key(days_left=5)
        svc, repo, _cache = _service(key)

        await svc.update_key_by_obj(key, {"expires_days": 1})

        data = repo.update.await_args_list[0].args[1]
        assert data["rotated_key_expires_at"] == data["expires_at"]


@asynccontextmanager
async def _patched_db_fallback(repo):
    @asynccontextmanager
    async def _fake_session():
        yield MagicMock(name="fake-session")

    with (
        patch("app.services.api_key_service.APIKeyRepository", return_value=repo),
        patch("app.services.api_key_service._open_db_session", _fake_session),
    ):
        yield


class TestValidateFallback:
    @pytest.mark.asyncio
    async def test_old_value_is_accepted_and_cached_under_itself_with_its_window(self) -> None:
        key = _rotated_key(days_left=2)
        key.application = Application(id=1, tenant_id=3, name="App", status=ApplicationStatus.ACTIVE)
        key.application.tenant = Tenant(
            id=3, name="T", organisation="T", email="t@example.invalid", status=TenantStatus.ACTIVE
        )
        cache = AsyncMock()
        cache.get_api_key_cache = AsyncMock(return_value=None)
        repo = AsyncMock()
        repo.get_by_api_key_if_valid = AsyncMock(return_value=key)

        async with _patched_db_fallback(repo):
            result = await APIKeyService(None, cache).validate_api_key(_OLD)

        assert result["valid"] is True
        token, ttl, _payload = cache.set_api_key_cache.await_args.args
        assert token == _OLD
        assert 0 < ttl <= 2 * 86400

    def test_db_lookup_matches_a_live_rotated_value(self) -> None:
        from sqlalchemy.dialects import postgresql

        from app.repositories.api_key_repository import APIKeyRepository

        captured = {}

        class _Session:
            async def execute(self, stmt):
                captured["sql"] = str(stmt.compile(dialect=postgresql.dialect()))
                result = MagicMock()
                result.unique.return_value.scalar_one_or_none.return_value = None
                return result

        import asyncio

        asyncio.run(APIKeyRepository(_Session()).get_by_api_key_if_valid(_OLD))
        sql = captured["sql"]
        assert "api_key.rotated_key =" in sql
        assert "api_key.rotated_key_expires_at >" in sql


@pytest.mark.asyncio
class TestRevokePreviousValueEarly:
    """DELETE /auth/api-keys/{id}/rotated-key stops the previous value before
    rotated_key_expires_at; the current value is untouched."""

    async def test_previous_value_stops_now_and_current_value_is_untouched(self) -> None:
        key = _rotated_key()
        svc, repo, cache = _service(key)

        async def _end(key_id, rotated_value, updated_by):
            key.rotated_key = None
            key.rotated_key_expires_at = None
            return True

        repo.end_rotation = AsyncMock(side_effect=_end)

        result = await svc.end_rotation_by_obj(key, "admin")

        repo.end_rotation.assert_awaited_once_with(7, _OLD, "admin")
        repo.commit.assert_awaited_once()
        assert (result.api_key, result.rotated_key, result.rotated_key_expires_at) == (_NEW, None, None)
        cache.delete_api_key_cache.assert_awaited_once_with(_OLD)   # only the old value's entry

    @pytest.mark.parametrize("key", [_key(), _rotated_key(days_left=-1)], ids=["never rotated", "window ended"])
    async def test_no_live_previous_value_is_409(self, key) -> None:
        svc, repo, cache = _service(key)
        with pytest.raises(AppError) as exc:
            await svc.end_rotation_by_obj(key, "admin")
        assert (exc.value.status_code, exc.value.code) == (409, "NO_ROTATION_IN_PROGRESS")
        repo.end_rotation.assert_not_called()
        cache.delete_api_key_cache.assert_not_called()

    async def test_losing_a_concurrent_end_or_revoke_is_409(self) -> None:
        key = _rotated_key()
        svc, repo, cache = _service(key)
        repo.end_rotation = AsyncMock(return_value=False)
        with pytest.raises(AppError) as exc:
            await svc.end_rotation_by_obj(key, "admin")
        assert exc.value.status_code == 409
        repo.commit.assert_not_called()
        cache.delete_api_key_cache.assert_not_called()

    async def test_redis_failure_after_commit_does_not_fail_the_request(self) -> None:
        key = _rotated_key()
        svc, repo, cache = _service(key)
        repo.end_rotation = AsyncMock(return_value=True)
        cache.delete_api_key_cache = AsyncMock(side_effect=RuntimeError("redis down"))
        await svc.end_rotation_by_obj(key, "admin")
        repo.commit.assert_awaited_once()


class TestLiveRotatedKeyExpiresAt:
    """What the list endpoints show as rotated_key_expires_at: the window end
    only while the key itself still works."""

    def test_live_window_on_an_active_key(self) -> None:
        key = _rotated_key()
        assert key.live_rotated_key_expires_at() == key.rotated_key_expires_at

    def test_none_on_a_revoked_key_even_inside_the_window(self) -> None:
        key = _rotated_key()
        key.is_active = False
        assert key.live_rotated_key_expires_at() is None

    def test_none_on_an_expired_key(self) -> None:
        key = _rotated_key()
        key.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        assert key.live_rotated_key_expires_at() is None

    def test_none_once_the_window_ended(self) -> None:
        assert _rotated_key(days_left=-1).live_rotated_key_expires_at() is None


@pytest.mark.asyncio
class TestRevokePreviousValueOnADeadKey:
    """A revoked or expired key has no live value, so there is nothing to
    stop early: 409, and the row is not touched."""

    @pytest.mark.parametrize("kill", ["revoked", "expired"])
    async def test_revoked_or_expired_key_is_409(self, kill) -> None:
        key = _rotated_key()
        if kill == "revoked":
            key.is_active = False
        else:
            key.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        svc, repo, cache = _service(key)
        with pytest.raises(AppError) as exc:
            await svc.end_rotation_by_obj(key, "admin")
        assert (exc.value.status_code, exc.value.code) == (409, "NO_ROTATION_IN_PROGRESS")
        repo.end_rotation.assert_not_called()
        cache.delete_api_key_cache.assert_not_called()

    async def test_end_rotation_update_requires_an_active_unexpired_row(self) -> None:
        """The UPDATE itself carries the active/expiry predicate, so a revoke
        that lands between the service check and the UPDATE still wins."""
        from sqlalchemy.dialects import postgresql

        captured = {}

        async def _execute(stmt):
            captured["sql"] = str(stmt.compile(dialect=postgresql.dialect()))
            return SimpleNamespace(rowcount=0)

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=_execute)

        assert await APIKeyRepository(db).end_rotation(7, _OLD, "admin") is False
        sql = captured["sql"]
        assert "api_key.is_active IS true" in sql
        assert "api_key.expires_at IS NULL OR api_key.expires_at >" in sql
        assert "api_key.rotated_key = " in sql


class TestResponsesShowThePreviousValueMasked:
    """Both values are visible after a rotation: the list/admin items and the
    rotate response carry the previous value masked, like api_key, only while
    it still works."""

    def test_list_item_carries_the_live_previous_value_masked(self) -> None:
        from app.routes.api_key import _key_item
        from app.utils.masking import mask_api_key

        item = _key_item(_rotated_key(), permission_names=["nmt.inference"])
        assert item.api_key == mask_api_key(_NEW)
        assert item.rotated_key == mask_api_key(_OLD)
        assert item.rotated_key != _OLD                       # never the raw value
        assert item.rotated_key_expires_at is not None

    @pytest.mark.parametrize("key", [_key(), _rotated_key(days_left=-1)], ids=["never rotated", "window ended"])
    def test_list_item_hides_a_previous_value_that_no_longer_works(self, key) -> None:
        from app.routes.api_key import _key_item

        item = _key_item(key, permission_names=[])
        assert (item.rotated_key, item.rotated_key_expires_at) == (None, None)

    @pytest.mark.asyncio
    async def test_rotate_response_returns_new_in_full_and_previous_masked(self) -> None:
        from types import SimpleNamespace
        from uuid import uuid4
        from app.routes.api_key import rotate_api_key
        from app.utils.masking import mask_api_key

        key = _rotated_key()
        svc = AsyncMock()
        svc.get_by_id_for_scope = AsyncMock(return_value=key)
        svc.rotate_by_obj = AsyncMock(return_value=(_NEW, key))
        request = MagicMock()
        request.state.user_roles = ["ADMIN"]
        from app.schemas.api_key import RotateAPIKeyRequest

        response = await rotate_api_key(
            key_id=key.id, request=request, body=RotateAPIKeyRequest(grace_days=7),
            current_user=SimpleNamespace(id=uuid4(), tenant_id=None), svc=svc,
        )
        assert svc.rotate_by_obj.await_args.kwargs["grace_days"] == 7
        assert response.data.api_key == _NEW
        assert response.data.rotated_key == mask_api_key(_OLD)
        assert response.data.rotated_key_expires_at == key.rotated_key_expires_at


# ── Grace period on rotate, extending it, and revoking the current value alone ──


def _sql(stmt) -> str:
    from sqlalchemy.dialects import postgresql

    return str(stmt.compile(dialect=postgresql.dialect()))


def _capturing_db(rowcount: int = 1):
    captured = {}

    async def _execute(stmt):
        captured["sql"] = _sql(stmt)
        return SimpleNamespace(rowcount=rowcount)

    db = AsyncMock()
    db.execute = AsyncMock(side_effect=_execute)
    return db, captured


class TestRotateGraceDays:
    @pytest.mark.asyncio
    async def test_grace_days_sets_the_window(self, monkeypatch) -> None:
        monkeypatch.setattr(APIKeyService, "generate_api_key", staticmethod(lambda: _NEW))
        key = _key()
        svc, repo, cache = _service(key)
        await svc.rotate_by_obj(key, actor_user_id="u-1", grace_days=30)
        rotated_expires_at = repo.rotate.await_args.args[3]
        expected = datetime.now(timezone.utc) + timedelta(days=30)
        assert abs((rotated_expires_at - expected).total_seconds()) < 5

    @pytest.mark.asyncio
    async def test_grace_period_past_the_key_expiry_is_422(self) -> None:
        key = _key(expires_at=datetime.now(timezone.utc) + timedelta(days=3))
        svc, repo, cache = _service(key)
        with pytest.raises(AppError) as exc:
            await svc.rotate_by_obj(key, actor_user_id="u-1", grace_days=7)
        assert (exc.value.status_code, exc.value.code) == (422, "INVALID_GRACE_PERIOD")
        repo.rotate.assert_not_called()

    @pytest.mark.asyncio
    async def test_grace_period_within_the_key_expiry_is_allowed(self, monkeypatch) -> None:
        monkeypatch.setattr(APIKeyService, "generate_api_key", staticmethod(lambda: _NEW))
        key = _key(expires_at=datetime.now(timezone.utc) + timedelta(days=3))
        svc, repo, cache = _service(key)
        await svc.rotate_by_obj(key, actor_user_id="u-1", grace_days=1)
        repo.rotate.assert_awaited_once()

    @pytest.mark.parametrize("grace_days", [-1, 36501])
    def test_grace_days_out_of_range_is_rejected(self, grace_days) -> None:
        from pydantic import ValidationError as PydanticValidationError

        from app.schemas.api_key import RotateAPIKeyRequest

        with pytest.raises(PydanticValidationError):
            RotateAPIKeyRequest(grace_days=grace_days)

    def test_grace_days_is_required(self) -> None:
        from pydantic import ValidationError as PydanticValidationError

        from app.schemas.api_key import RotateAPIKeyRequest

        with pytest.raises(PydanticValidationError):
            RotateAPIKeyRequest()


@pytest.mark.asyncio
class TestExtendRotation:
    """PATCH /auth/api-keys/{id}/rotated-key moves a live previous value's end
    later, never past the key's expiry, and never revives it."""

    def _extend_mock(self, key):
        async def _extend(key_id, rotated_value, new_expires_at, updated_by):
            key.rotated_key_expires_at = new_expires_at
            return True

        return AsyncMock(side_effect=_extend)

    async def test_window_moves_and_the_old_value_entry_gets_the_new_ttl(self) -> None:
        key = _rotated_key(days_left=1)
        svc, repo, cache = _service(key)
        repo.extend_rotation = self._extend_mock(key)
        new_end = datetime.now(timezone.utc) + timedelta(days=10)

        result = await svc.extend_rotation_by_obj(key, new_end, "admin")

        repo.extend_rotation.assert_awaited_once_with(7, _OLD, new_end, "admin")
        repo.commit.assert_awaited()          # the window, then the cached_data snapshot
        assert result.rotated_key_expires_at == new_end
        ttls = _set_values(cache)
        assert set(ttls) == {_NEW, _OLD}
        assert 9 * 86400 < ttls[_OLD] <= 10 * 86400

    @pytest.mark.parametrize(
        "key",
        [_key(), _rotated_key(days_left=-1), _key(rotated_key=_OLD, is_active=False,
                                                   rotated_key_expires_at=datetime.now(timezone.utc) + timedelta(days=3))],
        ids=["never rotated", "window ended", "key revoked"],
    )
    async def test_no_live_previous_value_is_409_and_nothing_is_revived(self, key) -> None:
        svc, repo, cache = _service(key)
        with pytest.raises(AppError) as exc:
            await svc.extend_rotation_by_obj(key, datetime.now(timezone.utc) + timedelta(days=9), "admin")
        assert (exc.value.status_code, exc.value.code) == (409, "NO_ROTATION_IN_PROGRESS")
        repo.extend_rotation.assert_not_called()

    async def test_new_end_not_later_than_the_current_one_is_422(self) -> None:
        key = _rotated_key(days_left=5)
        svc, repo, cache = _service(key)
        with pytest.raises(AppError) as exc:
            await svc.extend_rotation_by_obj(key, key.rotated_key_expires_at - timedelta(hours=1), "admin")
        assert (exc.value.status_code, exc.value.code) == (422, "INVALID_GRACE_EXTENSION")
        repo.extend_rotation.assert_not_called()

    async def test_new_end_past_the_key_expiry_is_422(self) -> None:
        key = _rotated_key(days_left=1)
        svc, repo, cache = _service(key)
        with pytest.raises(AppError) as exc:
            await svc.extend_rotation_by_obj(key, key.expires_at + timedelta(seconds=1), "admin")
        assert (exc.value.status_code, exc.value.code) == (422, "INVALID_GRACE_EXTENSION")

    async def test_end_equal_to_the_key_expiry_is_allowed(self) -> None:
        key = _rotated_key(days_left=1)
        svc, repo, cache = _service(key)
        repo.extend_rotation = self._extend_mock(key)
        await svc.extend_rotation_by_obj(key, key.expires_at, "admin")
        repo.extend_rotation.assert_awaited_once()

    async def test_losing_a_concurrent_change_is_409(self) -> None:
        key = _rotated_key(days_left=1)
        svc, repo, cache = _service(key)
        repo.extend_rotation = AsyncMock(return_value=False)
        with pytest.raises(AppError) as exc:
            await svc.extend_rotation_by_obj(key, datetime.now(timezone.utc) + timedelta(days=3), "admin")
        assert exc.value.status_code == 409
        repo.commit.assert_not_called()

    async def test_redis_failure_after_commit_does_not_fail_the_request(self) -> None:
        key = _rotated_key(days_left=1)
        svc, repo, cache = _service(key)
        repo.extend_rotation = self._extend_mock(key)
        cache.set_api_key_cache = AsyncMock(side_effect=RuntimeError("redis down"))
        await svc.extend_rotation_by_obj(key, datetime.now(timezone.utc) + timedelta(days=3), "admin")
        repo.commit.assert_awaited_once()

    async def test_update_guards_the_whole_condition_in_sql(self) -> None:
        db, captured = _capturing_db(rowcount=0)
        new_end = datetime.now(timezone.utc) + timedelta(days=3)
        assert await APIKeyRepository(db).extend_rotation(7, _OLD, new_end, "admin") is False
        sql = captured["sql"]
        assert "api_key.rotated_key = " in sql
        assert "api_key.rotated_key_expires_at > " in sql          # still live: no revive
        assert "api_key.rotated_key_expires_at < " in sql          # later than the current end
        assert "api_key.expires_at IS NULL OR api_key.expires_at >= " in sql
        assert "api_key.is_active IS true" in sql

    def test_request_requires_a_timezone(self) -> None:
        from pydantic import ValidationError as PydanticValidationError

        from app.schemas.api_key import ExtendRotationRequest

        with pytest.raises(PydanticValidationError):
            ExtendRotationRequest(rotated_key_expires_at=datetime(2030, 1, 1))


class TestNewEndpointPermissions:
    """The gateway maps every rotation endpoint to revoke's permission (33)."""

    @pytest.mark.parametrize(
        "method, path",
        [
            ("POST", "/api/v1/auth/api-keys/7/rotate"),
            ("PATCH", "/api/v1/auth/api-keys/7/rotated-key"),
            ("DELETE", "/api/v1/auth/api-keys/7/rotated-key"),
        ],
    )
    def test_maps_to_the_revoke_permission(self, method, path) -> None:
        import json
        import pathlib

        from app.core.permission_checker import PermissionChecker

        payload = json.loads((pathlib.Path(__file__).parent.parent / "api_permissions.json").read_text())
        checker = PermissionChecker()
        checker._api_permission_map = {
            m["endpoint"]: int(m["permissionRequired"]) for m in payload["apiMappings"]
        }
        assert checker.get_required_permission(method, path) == 33


@pytest.mark.asyncio
class TestNewRoutes:
    def _request(self):
        request = MagicMock()
        request.state.user_roles = ["ADMIN"]
        return request

    async def test_extend_returns_the_key_with_its_new_window(self) -> None:
        from uuid import uuid4

        from app.routes.api_key import extend_previous_api_key_value
        from app.schemas.api_key import ExtendRotationRequest
        from app.utils.masking import mask_api_key

        key = _rotated_key(days_left=9)
        svc = AsyncMock()
        svc.get_by_id_for_scope = AsyncMock(return_value=key)
        svc.extend_rotation_by_obj = AsyncMock(return_value=key)
        svc.permission_name_map_for_keys = AsyncMock(return_value={1: "nmt.inference"})
        body = ExtendRotationRequest(rotated_key_expires_at=key.rotated_key_expires_at)
        response = await extend_previous_api_key_value(
            key_id=7, body=body, request=self._request(),
            current_user=SimpleNamespace(id=uuid4(), tenant_id=None), svc=svc,
        )
        assert response.data.rotated_key == mask_api_key(_OLD)
        assert response.data.rotated_key_expires_at == key.rotated_key_expires_at

class TestRotatedAt:
    @pytest.mark.asyncio
    async def test_rotate_stamps_rotated_at_in_the_same_update(self) -> None:
        db, captured = _capturing_db()
        await APIKeyRepository(db).rotate(7, _OLD, _NEW, datetime.now(timezone.utc), "u-1")
        assert "rotated_at=now()" in captured["sql"]

    def test_list_item_carries_rotated_at(self) -> None:
        from app.routes.api_key import _key_item

        key = _rotated_key()
        key.rotated_at = datetime.now(timezone.utc) - timedelta(days=1)
        assert _key_item(key, permission_names=[]).rotated_at == key.rotated_at
