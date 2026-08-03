"""Unit tests: RefreshingCache base class and its two subclasses,
TenantNameCache and RolePermissionCache.

No real DB — ``get_db`` is monkeypatched with a fake async generator per test.
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.exc import SQLAlchemyError

from app.services.refreshing_cache import RefreshingCache
from app.services.role_permission_cache import RolePermissionCache
from app.services.tenant_name_cache import TenantNameCache


def _fake_get_db(session):
    """Build a ``get_db``-shaped async generator yielding a single session."""
    async def _get_db():
        yield session
    return _get_db


def _db_result(rows: list[tuple]) -> MagicMock:
    result = MagicMock()
    result.all.return_value = rows
    return result


class _CountingCache(RefreshingCache):
    """Minimal RefreshingCache subclass for exercising start/stop/_refresh_loop
    without a real data source."""

    def __init__(self, *, fail_on: frozenset = frozenset(), error: Exception = None, **kwargs):
        super().__init__(**kwargs)
        self.reload_calls = 0
        self._fail_on = fail_on
        self._error = error or RuntimeError("boom")

    def _loaded_count(self) -> int:
        return self.reload_calls

    async def reload(self) -> None:
        self.reload_calls += 1
        if self.reload_calls in self._fail_on:
            raise self._error


@pytest.mark.asyncio
class TestRefreshingCacheBase:
    async def test_start_loads_once_and_starts_background_task(self):
        cache = _CountingCache(refresh_interval_seconds=1000)
        await cache.start()
        try:
            assert cache.reload_calls == 1
            assert cache._task is not None and not cache._task.done()
        finally:
            await cache.stop()

    async def test_stop_cancels_task_and_clears_it(self):
        cache = _CountingCache(refresh_interval_seconds=1000)
        await cache.start()
        await cache.stop()
        assert cache._task is None

    async def test_stop_without_start_is_a_no_op(self):
        cache = _CountingCache(refresh_interval_seconds=1000)
        await cache.stop()  # must not raise
        assert cache._task is None

    async def test_refresh_loop_keeps_running_after_sqlalchemy_error(self):
        # reload() #1 (start) succeeds; #2 (first refresh tick) fails; the
        # loop must survive that and keep ticking.
        cache = _CountingCache(
            fail_on=frozenset({2}), error=SQLAlchemyError("db down"),
            refresh_interval_seconds=0.01,
        )
        await cache.start()
        try:
            await asyncio.sleep(0.1)
            assert cache.reload_calls >= 3
        finally:
            await cache.stop()

    async def test_refresh_loop_keeps_running_after_unexpected_error(self):
        cache = _CountingCache(
            fail_on=frozenset({2}), error=ValueError("unexpected"),
            refresh_interval_seconds=0.01,
        )
        await cache.start()
        try:
            await asyncio.sleep(0.1)
            assert cache.reload_calls >= 3
        finally:
            await cache.stop()

    async def test_restart_does_not_spawn_a_second_task(self):
        cache = _CountingCache(refresh_interval_seconds=1000)
        await cache.start()
        first_task = cache._task
        await cache.start()
        try:
            assert cache._task is first_task
            assert cache.reload_calls == 2  # both start() calls reload
        finally:
            await cache.stop()


@pytest.mark.asyncio
class TestTenantNameCache:
    async def test_get_name_is_none_before_any_load(self):
        cache = TenantNameCache()
        assert cache.get_name(1) is None

    async def test_set_name_pushes_immediate_update(self):
        cache = TenantNameCache()
        cache.set_name(1, "Acme Corp")
        assert cache.get_name(1) == "Acme Corp"

    async def test_reload_builds_id_to_organisation_map(self, monkeypatch):
        session = AsyncMock()
        session.execute = AsyncMock(
            return_value=_db_result([(1, "Acme Corp"), (2, "टाटा समूह")])
        )
        monkeypatch.setattr(
            "app.services.tenant_name_cache.get_db", _fake_get_db(session)
        )

        cache = TenantNameCache()
        await cache.reload()

        assert cache.get_name(1) == "Acme Corp"
        assert cache.get_name(2) == "टाटा समूह"
        assert cache.get_name(999) is None

    async def test_reload_replaces_stale_entries_not_merges(self, monkeypatch):
        cache = TenantNameCache()
        cache.set_name(1, "Old Name")

        session = AsyncMock()
        session.execute = AsyncMock(return_value=_db_result([(2, "Only This One")]))
        monkeypatch.setattr(
            "app.services.tenant_name_cache.get_db", _fake_get_db(session)
        )
        await cache.reload()

        # tenant 1 was set via push (e.g. a create that happened after the
        # snapshot query ran) — reload's full rebuild drops it, matching the
        # documented eventual-consistency window.
        assert cache.get_name(1) is None
        assert cache.get_name(2) == "Only This One"

    async def test_loaded_count_reflects_names_size(self, monkeypatch):
        session = AsyncMock()
        session.execute = AsyncMock(return_value=_db_result([(1, "A"), (2, "B"), (3, "C")]))
        monkeypatch.setattr(
            "app.services.tenant_name_cache.get_db", _fake_get_db(session)
        )
        cache = TenantNameCache()
        await cache.start()
        try:
            assert cache._loaded_count() == 3
        finally:
            await cache.stop()


@pytest.mark.asyncio
class TestRolePermissionCache:
    async def test_get_user_permission_ids_empty_before_load(self):
        cache = RolePermissionCache()
        assert cache.get_user_permission_ids([1, 2]) == []

    async def test_reload_builds_role_to_permissions_map(self, monkeypatch):
        session = AsyncMock()
        session.execute = AsyncMock(
            return_value=_db_result([(1, 10), (1, 11), (2, 20)])
        )
        monkeypatch.setattr(
            "app.services.role_permission_cache.get_db", _fake_get_db(session)
        )

        cache = RolePermissionCache()
        await cache.reload()

        assert cache.get_user_permission_ids([1]) == [10, 11]
        assert cache.get_user_permission_ids([2]) == [20]

    async def test_get_user_permission_ids_unions_and_sorts_across_roles(self, monkeypatch):
        session = AsyncMock()
        session.execute = AsyncMock(
            return_value=_db_result([(1, 30), (1, 10), (2, 20), (2, 10)])
        )
        monkeypatch.setattr(
            "app.services.role_permission_cache.get_db", _fake_get_db(session)
        )

        cache = RolePermissionCache()
        await cache.reload()

        assert cache.get_user_permission_ids([1, 2]) == [10, 20, 30]

    async def test_get_user_permission_ids_ignores_unknown_role(self, monkeypatch):
        session = AsyncMock()
        session.execute = AsyncMock(return_value=_db_result([(1, 10)]))
        monkeypatch.setattr(
            "app.services.role_permission_cache.get_db", _fake_get_db(session)
        )

        cache = RolePermissionCache()
        await cache.reload()

        assert cache.get_user_permission_ids([999]) == []
