"""Write-through Redis cache in front of per-user column preferences.

No Redis or database is needed — the client is an in-memory fake and the
repository is mocked.
"""
from __future__ import annotations

import json
import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.exceptions import ValidationError
from app.services.user_preferences import column_preference_service as svc
from app.services.user_preferences import preference_cache as cache

_REPO = "app.services.user_preferences.column_preference_service.repo"
VIEW = "service-list"
FIELD = f"columns:{VIEW}"
USER = "user-7f3a"
NON_ADMIN_DEFAULTS = ["name", "actions", "task_type", "status"]


def _key(user_id=USER):
    return f"core:user:{user_id}:prefs"


# ── fakes ────────────────────────────────────────────────────────────────────


class _FakePipeline:
    def __init__(self, redis):
        self._redis = redis
        self._ops = []

    def hset(self, key, field, value):
        self._ops.append(("hset", key, field, value))

    def expire(self, key, ttl):
        self._ops.append(("expire", key, ttl))

    async def execute(self):
        if "execute" in self._redis.fail_on:
            raise RuntimeError("redis down")
        for op in self._ops:
            if op[0] == "hset":
                self._redis.store.setdefault(op[1], {})[op[2]] = op[3]
            else:
                self._redis.ttls[op[1]] = op[2]


class _FakeRedis:
    def __init__(self, *, fail_on=()):
        self.store: dict = {}
        self.ttls: dict = {}
        self.fail_on = set(fail_on)

    def pipeline(self):
        return _FakePipeline(self)

    async def hget(self, key, field):
        if "hget" in self.fail_on:
            raise RuntimeError("redis down")
        value = self.store.get(key, {}).get(field)
        # The real client returns bytes unless decode_responses is set.
        return value.encode() if value is not None else None

    async def hdel(self, key, field):
        self.store.get(key, {}).pop(field, None)


def _repo(stored=None):
    repo = MagicMock()
    repo.get = AsyncMock(return_value=stored)
    repo.upsert = AsyncMock()
    repo.delete_preference = AsyncMock()
    return repo


@pytest.fixture
def redis(monkeypatch):
    client = _FakeRedis()
    monkeypatch.setattr(cache, "_get_redis", lambda: client)
    return client


# ── read path ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestRead:
    async def test_miss_reads_db_once_then_serves_from_cache(self, redis):
        repo = _repo(["name", "actions", "service_id"])
        with patch(_REPO, repo):
            first = await svc.get_preference(MagicMock(), USER, VIEW, False)
            second = await svc.get_preference(MagicMock(), USER, VIEW, False)
        assert first == second
        assert first["visibleColumns"] == ["name", "actions", "service_id"]
        repo.get.assert_awaited_once()
        assert json.loads(redis.store[_key()][FIELD]) == ["name", "actions", "service_id"]
        assert redis.ttls[_key()] == 24 * 60 * 60

    async def test_nothing_saved_is_cached_as_null(self, redis):
        repo = _repo(None)
        with patch(_REPO, repo):
            for _ in range(2):
                out = await svc.get_preference(MagicMock(), USER, VIEW, False)
        assert out == {"viewKey": VIEW, "visibleColumns": NON_ADMIN_DEFAULTS, "isDefault": True}
        assert redis.store[_key()][FIELD] == "null"
        repo.get.assert_awaited_once()

    async def test_cached_ids_are_still_role_filtered(self, redis):
        redis.store[_key()] = {FIELD: json.dumps(["name", "actions", "task_type", "input_price"])}
        repo = _repo()
        with patch(_REPO, repo):
            admin = await svc.get_preference(MagicMock(), USER, VIEW, True)
            non_admin = await svc.get_preference(MagicMock(), USER, VIEW, False)
        assert "input_price" in admin["visibleColumns"]
        assert non_admin["visibleColumns"] == ["name", "actions", "task_type"]
        repo.get.assert_not_called()

    async def test_users_get_separate_keys(self, redis):
        with patch(_REPO, _repo(["task_type"])):
            await svc.get_preference(MagicMock(), "alice", VIEW, False)
        with patch(_REPO, _repo(None)):
            await svc.get_preference(MagicMock(), "bob", VIEW, False)
        assert json.loads(redis.store[_key("alice")][FIELD]) == ["task_type"]
        assert redis.store[_key("bob")][FIELD] == "null"

    async def test_no_redis_reads_db(self, monkeypatch):
        monkeypatch.setattr(cache, "_get_redis", lambda: None)
        repo = _repo(["task_type"])
        with patch(_REPO, repo):
            await svc.get_preference(MagicMock(), USER, VIEW, False)
            await svc.get_preference(MagicMock(), USER, VIEW, False)
        assert repo.get.await_count == 2

    async def test_read_error_falls_back_to_db(self, monkeypatch):
        client = _FakeRedis(fail_on={"hget"})
        monkeypatch.setattr(cache, "_get_redis", lambda: client)
        repo = _repo(["service_id"])
        with patch(_REPO, repo):
            out = await svc.get_preference(MagicMock(), USER, VIEW, False)
        assert out["visibleColumns"] == ["name", "actions", "service_id"]
        repo.get.assert_awaited_once()


# ── write path ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestWrite:
    async def test_put_writes_through_and_next_get_skips_db(self, redis):
        repo = _repo()
        with patch(_REPO, repo):
            saved = await svc.save_preference(MagicMock(), USER, VIEW, ["service_id", "task_type"], False)
            out = await svc.get_preference(MagicMock(), USER, VIEW, False)
        assert out == saved
        assert json.loads(redis.store[_key()][FIELD]) == saved["visibleColumns"]
        assert redis.ttls[_key()] == 24 * 60 * 60
        repo.get.assert_not_called()

    async def test_delete_caches_null(self, redis):
        redis.store[_key()] = {FIELD: json.dumps(["name", "actions", "service_id"])}
        repo = _repo()
        with patch(_REPO, repo):
            await svc.reset_preference(MagicMock(), USER, VIEW, False)
            out = await svc.get_preference(MagicMock(), USER, VIEW, False)
        assert redis.store[_key()][FIELD] == "null"
        assert out["isDefault"] is True
        repo.get.assert_not_called()

    async def test_failed_validation_leaves_cache_untouched(self, redis):
        redis.store[_key()] = {FIELD: json.dumps(["name", "actions", "service_id"])}
        with patch(_REPO, _repo()):
            with pytest.raises(ValidationError):
                await svc.save_preference(MagicMock(), USER, VIEW, ["bogus"], False)
        assert json.loads(redis.store[_key()][FIELD]) == ["name", "actions", "service_id"]

    async def test_failed_write_deletes_field_and_save_succeeds(self, monkeypatch, caplog):
        client = _FakeRedis(fail_on={"execute"})
        client.store[_key()] = {FIELD: json.dumps(["name", "actions", "service_id"])}
        monkeypatch.setattr(cache, "_get_redis", lambda: client)
        repo = _repo()
        with caplog.at_level(logging.WARNING), patch(_REPO, repo):
            saved = await svc.save_preference(MagicMock(), USER, VIEW, ["task_type"], False)
        assert saved["visibleColumns"] == ["name", "actions", "task_type"]
        repo.upsert.assert_awaited_once()
        assert FIELD not in client.store[_key()]
        assert "RuntimeError" in caplog.text


def test_logs_never_contain_the_user_id(monkeypatch, caplog):
    import asyncio

    client = _FakeRedis(fail_on={"hget", "execute"})
    monkeypatch.setattr(cache, "_get_redis", lambda: client)
    with caplog.at_level(logging.WARNING):
        assert asyncio.run(cache.get_columns(USER, VIEW)) is cache.MISS
        asyncio.run(cache.set_columns(USER, VIEW, ["name"]))
    assert caplog.records
    assert USER not in caplog.text
    assert "redis down" not in caplog.text
