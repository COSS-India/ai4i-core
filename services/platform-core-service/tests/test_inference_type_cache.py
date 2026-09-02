"""app/services/pay_per_use/inference_type_cache.py — the write-through cache.

What is worth pinning here is not "it reads Redis" but the four rules in the
module docstring, each of which fails silently when broken:

1. **A cache failure never reaches the caller.** The DB is the source of truth;
   Redis is an accelerator. Every operation swallows Redis errors.
2. **Rebuild is wholesale.** Partial updates let ``:all`` disagree with the
   per-name keys, and nothing would ever notice.
3. **Keys carry a TTL** even though writes are write-through, so a bad write
   cannot become permanent.
4. **Every read falls back to the DB and re-warms.** These keys live under
   ``allkeys-lru`` pressure — a cache-only path would stop resolving ids under
   memory pressure with no error anywhere.

The encoding is also load-bearing and easy to break by accident: both keys are
Redis **hashes**, and ``endpoint_patterns`` is a list, so that one field is
JSON-encoded. payperuse_consumer reads ``HGET core:inference_type:<name> id``
from the same keys, so a shape change here silently breaks billing in another
service.

No Redis or database is needed — the client and the session are both faked.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from app.services.pay_per_use import inference_type_cache as cache


# ── fakes ────────────────────────────────────────────────────────────────────


class _Row:
    """An InferenceType ORM row, as _to_dict reads it."""

    def __init__(self, id, name, endpoint_patterns, unit, pricing):
        self.id = id
        self.name = name
        self.endpoint_patterns = endpoint_patterns
        self.unit = unit
        self.pricing = pricing


_ROWS = [
    _Row(2, "asr", ["/api/v1/asr/inference"], "audio_minutes", "per_minute"),
    _Row(1, "llm", ["/api/v1/chat", "/api/v1/chat/completions"], "tokens", "per_million_tokens"),
]


class _FakeSession:
    """Returns _ROWS for a select(InferenceType), filtered when a name is bound."""

    def __init__(self, rows=None):
        self._rows = _ROWS if rows is None else rows
        self.executes = 0

    async def execute(self, stmt):
        self.executes += 1
        # get_by_name binds the name it wants; _fetch_all binds nothing. Read it
        # off the compiled statement — the ORM expression tree does not expose
        # bindparams the way a text() clause does, and a fake that quietly
        # ignores the WHERE would pass every lookup regardless of the value.
        params = dict(stmt.compile().params)
        wanted = params.get("name_1")

        rows = self._rows
        if wanted is not None:
            rows = [r for r in self._rows if r.name == wanted]

        result = MagicMock()
        result.scalars.return_value.all.return_value = rows
        result.scalar_one_or_none.return_value = rows[0] if rows else None
        return result


class _FakePipeline:
    """Records commands instead of issuing them."""

    def __init__(self, store, log):
        self._store, self._log = store, log

    def delete(self, *keys):
        self._log.append(("delete", keys))
        for k in keys:
            # Redis does not distinguish b"key" from "key"; scan_iter yields
            # bytes unless decode_responses is set, so the fake must not either.
            self._store.pop(k.decode() if isinstance(k, bytes) else k, None)

    def hset(self, key, mapping=None):
        self._log.append(("hset", key, mapping))
        self._store.setdefault(key, {}).update(mapping or {})

    def expire(self, key, ttl):
        self._log.append(("expire", key, ttl))

    async def execute(self):
        self._log.append(("execute",))


class _FakeRedis:
    def __init__(self, *, existing_keys=(), fail_on=None):
        self.store: dict = {}
        self.log: list = []
        self._existing = list(existing_keys)
        self._fail_on = fail_on or set()

    def pipeline(self):
        if "pipeline" in self._fail_on:
            raise RuntimeError("redis down")
        return _FakePipeline(self.store, self.log)

    async def scan_iter(self, match=None):
        for key in self._existing:
            yield key

    async def hgetall(self, key):
        if "hgetall" in self._fail_on:
            raise RuntimeError("redis down")
        return dict(self.store.get(key, {}))

    def ttl_for(self, key):
        for entry in self.log:
            if entry[0] == "expire" and entry[1] == key:
                return entry[2]
        return None


# conftest installs an autouse fixture that stubs get_all / get_unit_map /
# get_unit_map_standalone, so route and metering tests see a fixed catalogue
# without a database. This module tests those very functions, so it puts the
# real implementations back. Captured at import, before any fixture runs.
_REAL = {
    name: getattr(cache, name)
    for name in ("get_all", "get_unit_map", "get_unit_map_standalone")
}


@pytest.fixture(autouse=True)
def _use_the_real_cache(monkeypatch):
    for name, fn in _REAL.items():
        monkeypatch.setattr(cache, name, fn)


@pytest.fixture
def redis(monkeypatch):
    """Install a fake client. Returns it so tests can inspect what was written."""
    client = _FakeRedis()
    monkeypatch.setattr(cache, "_get_redis", lambda: client)
    return client


@pytest.fixture
def no_redis(monkeypatch):
    """_get_redis returns None before init_redis has run (tests, CLI contexts)."""
    monkeypatch.setattr(cache, "_get_redis", lambda: None)


# ── encoding: the cross-service contract ─────────────────────────────────────


class TestEncoding:
    """payperuse_consumer HGETs `id` off these keys. The shape is a contract."""

    def test_key_prefix_is_the_documented_one(self):
        assert cache._KEY_PREFIX == "core:inference_type"
        assert cache._ALL_KEY == "core:inference_type:all"

    def test_name_key_lowercases(self):
        assert cache._name_key("ASR") == "core:inference_type:asr"

    def test_hash_values_are_all_strings(self):
        # A hash field cannot hold a list or an int; redis-py would raise.
        mapping = cache._to_hash(cache._to_dict(_ROWS[1]))
        assert all(isinstance(v, str) for v in mapping.values())

    def test_endpoint_patterns_json_round_trips(self):
        # JSON rather than a comma-join, so a path containing a comma survives.
        entry = cache._to_dict(_ROWS[1])
        assert cache._from_hash(cache._to_hash(entry)) == entry

    def test_id_survives_as_an_int(self):
        # The consumer does int(HGET ... "id"); a str here would still work, but
        # platform-core's own readers compare it to an int column.
        restored = cache._from_hash(cache._to_hash(cache._to_dict(_ROWS[0])))
        assert restored["id"] == 2 and isinstance(restored["id"], int)


# ── rule 2: rebuild is wholesale ─────────────────────────────────────────────


@pytest.mark.asyncio
class TestRebuild:
    async def test_writes_every_per_name_key_and_the_all_key(self, redis):
        await cache.rebuild(_FakeSession())
        assert "core:inference_type:asr" in redis.store
        assert "core:inference_type:llm" in redis.store
        assert set(redis.store["core:inference_type:all"]) == {"asr", "llm"}

    async def test_all_key_holds_whole_rows_not_just_names(self, redis):
        await cache.rebuild(_FakeSession())
        row = json.loads(redis.store["core:inference_type:all"]["llm"])
        assert row["unit"] == "tokens"
        assert row["endpoint_patterns"] == ["/api/v1/chat", "/api/v1/chat/completions"]

    async def test_each_key_is_deleted_before_it_is_rewritten(self, redis):
        # HSET merges. Without the delete, a field dropped from the row shape
        # would linger until the TTL expired.
        await cache.rebuild(_FakeSession())
        for key in ("core:inference_type:all", "core:inference_type:asr"):
            ops = [e for e in redis.log if len(e) > 1 and key in str(e[1])]
            assert ops[0][0] == "delete", f"{key} was written before being cleared"

    async def test_every_key_gets_a_ttl(self, redis):
        # Rule 3: write-through with no TTL makes a bad write permanent.
        await cache.rebuild(_FakeSession())
        for key in ("core:inference_type:all", "core:inference_type:asr",
                    "core:inference_type:llm"):
            assert redis.ttl_for(key) == cache._TTL_SECONDS

    async def test_returns_db_rows_even_when_redis_is_absent(self, no_redis):
        # Rule 1: the DB is the source of truth; callers still get their data.
        assert len(await cache.rebuild(_FakeSession())) == 2

    async def test_redis_failure_is_swallowed_not_raised(self, monkeypatch):
        monkeypatch.setattr(cache, "_get_redis", lambda: _FakeRedis(fail_on={"pipeline"}))
        assert len(await cache.rebuild(_FakeSession())) == 2


@pytest.mark.asyncio
class TestRebuildSweep:
    """sweep=True is the only thing that removes a key for a deleted type."""

    _STALE = "core:inference_type:deleted-type"

    async def test_sweep_removes_keys_for_types_that_no_longer_exist(self, monkeypatch):
        client = _FakeRedis(existing_keys=[self._STALE, "core:inference_type:asr"])
        client.store[self._STALE] = {"id": "99"}
        monkeypatch.setattr(cache, "_get_redis", lambda: client)

        await cache.rebuild(_FakeSession(), sweep=True)
        assert self._STALE not in client.store

    async def test_sweep_keeps_live_keys(self, monkeypatch):
        client = _FakeRedis(existing_keys=[self._STALE, "core:inference_type:asr"])
        monkeypatch.setattr(cache, "_get_redis", lambda: client)

        await cache.rebuild(_FakeSession(), sweep=True)
        assert "core:inference_type:asr" in client.store

    async def test_sweep_handles_bytes_keys_from_redis(self, monkeypatch):
        # scan_iter yields bytes unless decode_responses is set.
        client = _FakeRedis(existing_keys=[self._STALE.encode()])
        client.store[self._STALE] = {"id": "99"}
        monkeypatch.setattr(cache, "_get_redis", lambda: client)

        await cache.rebuild(_FakeSession(), sweep=True)
        assert self._STALE not in client.store

    async def test_default_does_not_scan(self, monkeypatch):
        # Read-path misses use the default: a TTL expiry leaves nothing stale,
        # so scanning the whole shared keyspace would be pure waste.
        client = _FakeRedis(existing_keys=[self._STALE])
        client.store[self._STALE] = {"id": "99"}
        monkeypatch.setattr(cache, "_get_redis", lambda: client)

        await cache.rebuild(_FakeSession())
        assert self._STALE in client.store


# ── rule 4: every read falls back to the DB ──────────────────────────────────


@pytest.mark.asyncio
class TestGetAll:
    async def test_served_from_cache_without_touching_the_db(self, redis):
        await cache.rebuild(_FakeSession())
        db = _FakeSession()
        assert len(await cache.get_all(db)) == 2
        assert db.executes == 0

    async def test_sorted_by_name(self, redis):
        # Hash field order is not guaranteed; GET /inference-types must be stable.
        await cache.rebuild(_FakeSession())
        assert [e["name"] for e in await cache.get_all(_FakeSession())] == ["asr", "llm"]

    async def test_cold_cache_falls_back_to_the_db(self, redis):
        db = _FakeSession()
        assert len(await cache.get_all(db)) == 2
        assert db.executes > 0

    async def test_cold_cache_re_warms(self, redis):
        await cache.get_all(_FakeSession())
        assert "core:inference_type:all" in redis.store

    async def test_redis_read_failure_falls_back_instead_of_raising(self, monkeypatch):
        monkeypatch.setattr(cache, "_get_redis", lambda: _FakeRedis(fail_on={"hgetall"}))
        assert len(await cache.get_all(_FakeSession())) == 2

    async def test_no_redis_at_all_still_serves(self, no_redis):
        assert len(await cache.get_all(_FakeSession())) == 2


@pytest.mark.asyncio
class TestGetByName:
    async def test_hit(self, redis):
        await cache.rebuild(_FakeSession())
        assert (await cache.get_by_name(_FakeSession(), "asr"))["id"] == 2

    async def test_lookup_is_case_insensitive_on_the_cache_path(self, redis):
        await cache.rebuild(_FakeSession())
        assert (await cache.get_by_name(_FakeSession(), "ASR"))["id"] == 2

    async def test_lookup_is_case_insensitive_on_the_db_path_too(self, redis):
        # Distinct from the test above: _name_key lowercases on its own, so the
        # cache path stays case-insensitive even if the function stops
        # normalising. Only a cold-cache lookup exercises the DB comparison,
        # which is `InferenceType.name == normalized` against a lowercase column.
        db = _FakeSession()
        got = await cache.get_by_name(db, "ASR")
        assert db.executes > 0, "this must reach the DB, not the cache"
        assert got is not None and got["id"] == 2

    async def test_empty_name_is_none_without_any_lookup(self, redis):
        db = _FakeSession()
        assert await cache.get_by_name(db, "") is None
        assert db.executes == 0

    async def test_miss_falls_back_to_the_db(self, redis):
        db = _FakeSession()
        assert (await cache.get_by_name(db, "asr"))["id"] == 2
        assert db.executes > 0

    async def test_db_fallback_re_warms_that_one_key(self, redis):
        await cache.get_by_name(_FakeSession(), "asr")
        assert redis.store["core:inference_type:asr"]["id"] == "2"

    async def test_unknown_name_returns_none(self, redis):
        assert await cache.get_by_name(_FakeSession(rows=[]), "nope") is None


@pytest.mark.asyncio
class TestResolvers:
    """The helpers the read paths were migrated onto."""

    async def test_get_id_by_name(self, redis):
        assert await cache.get_id_by_name(_FakeSession(), "asr") == 2

    async def test_get_id_by_name_unknown_is_none(self, redis):
        assert await cache.get_id_by_name(_FakeSession(rows=[]), "nope") is None

    async def test_get_name_by_id_maps_back_for_the_response_edge(self, redis):
        assert await cache.get_name_by_id(_FakeSession()) == {1: "llm", 2: "asr"}

    async def test_get_ids_by_names_resolves_a_whole_filter_list(self, redis):
        got = await cache.get_ids_by_names(_FakeSession(), ["asr", "llm"])
        assert got == {"asr": 2, "llm": 1}

    async def test_get_ids_by_names_reports_unknowns_as_none(self, redis):
        # The caller names the offending value in its 422; it must not guess.
        got = await cache.get_ids_by_names(_FakeSession(), ["asr", "nope"])
        assert got == {"asr": 2, "nope": None}

    async def test_get_ids_by_names_normalises_input(self, redis):
        got = await cache.get_ids_by_names(_FakeSession(), ["  ASR  "])
        assert got == {"asr": 2}

    async def test_get_ids_by_names_drops_blanks(self, redis):
        assert await cache.get_ids_by_names(_FakeSession(), ["", "  "]) == {}

    async def test_get_ids_by_names_costs_one_read_not_n(self, redis):
        # The whole reason it exists: ?task_types=a,b,c must not be N round-trips.
        await cache.rebuild(_FakeSession())
        db = _FakeSession()
        await cache.get_ids_by_names(db, ["asr", "llm", "asr", "llm"])
        assert db.executes == 0

    async def test_get_unit_map(self, redis):
        got = await cache.get_unit_map(_FakeSession())
        assert got == {"asr": "audio_minutes", "llm": "tokens"}


@pytest.mark.asyncio
class TestUnitMapStandalone:
    """MeteringService holds no session, so this one opens its own."""

    async def test_returns_empty_rather_than_raising_when_unavailable(self, monkeypatch):
        # An empty map makes the metering suffix fall through to
        # SERVICE_BREAKDOWN_CONFIG — the pre-PPU behaviour. A dashboard must not
        # 500 because the catalogue is briefly unreachable.
        #
        # The import is lazy, inside the function, so the module is swapped in
        # sys.modules rather than patched as an attribute.
        import sys
        import types

        broken = types.ModuleType("app.core.database")

        def _boom():
            raise RuntimeError("no engine")

        broken.get_primary_session_factory = _boom
        monkeypatch.setitem(sys.modules, "app.core.database", broken)

        assert await cache.get_unit_map_standalone() == {}

    async def test_opens_its_own_session_when_one_is_available(self, monkeypatch, redis):
        # MeteringService is constructed with repositories but no primary
        # session, which is the whole reason this variant exists.
        import sys
        import types
        from contextlib import asynccontextmanager

        working = types.ModuleType("app.core.database")

        @asynccontextmanager
        async def _session():
            yield _FakeSession()

        working.get_primary_session_factory = lambda: _session
        monkeypatch.setitem(sys.modules, "app.core.database", working)

        assert await cache.get_unit_map_standalone() == {
            "asr": "audio_minutes", "llm": "tokens",
        }
