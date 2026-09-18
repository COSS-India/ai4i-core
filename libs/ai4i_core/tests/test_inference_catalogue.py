"""ai4i_core.ppu.catalogue — the provider chain and its failure behaviour.

The contract worth pinning is not "it reads the catalogue" but what it does when
it *cannot*. This client replaced a bundled YAML that could only fail at import,
and it now sits on the hot path of ``/auth/validate`` and of every inference
span's billing units. Every caller inherited "this never raises", so the
degradation ladder — fresh, stale, empty, but never an exception — is the thing
that must not regress.
"""

from __future__ import annotations

import asyncio
import json

import pytest

from ai4i_core.ppu.catalogue import InferenceTypeCatalogue, to_legacy_entry

# This package has no asyncio_mode config of its own, so the marker is explicit.
pytestmark = pytest.mark.asyncio

_ROWS = [
    {
        "id": 1,
        "name": "llm",
        "endpoint_patterns": ["/api/v1/chat", "/api/v1/chat/completions"],
        "unit": "tokens",
        "pricing": "per_million_tokens",
    },
    {
        "id": 2,
        "name": "asr",
        "endpoint_patterns": ["/api/v1/asr/inference"],
        "unit": "audio_minutes",
        "pricing": "per_minute",
    },
]


class _FakeRedis:
    """Only the one call the client makes."""

    def __init__(self, rows=None, *, raises=False):
        self._rows = rows
        self.raises = raises
        self.calls = 0

    async def hgetall(self, key):
        self.calls += 1
        if self.raises:
            raise RuntimeError("redis down")
        if not self._rows:
            return {}
        return {r["name"]: json.dumps(r) for r in self._rows}


def _catalogue(**kwargs) -> InferenceTypeCatalogue:
    return InferenceTypeCatalogue(**kwargs)


class TestRedisProvider:
    async def test_reads_rows_from_the_shared_key(self):
        cat = _catalogue(redis_factory=lambda: _FakeRedis(_ROWS))
        assert [r["name"] for r in await cat.get_all()] == ["asr", "llm"]

    async def test_rows_are_sorted_by_name(self):
        # Hash field order is not guaranteed; callers render these in order.
        cat = _catalogue(redis_factory=lambda: _FakeRedis(list(reversed(_ROWS))))
        assert [r["name"] for r in await cat.get_all()] == ["asr", "llm"]

    async def test_decodes_bytes_values(self):
        class _BytesRedis(_FakeRedis):
            async def hgetall(self, key):
                return {r["name"]: json.dumps(r).encode() for r in _ROWS}

        cat = _catalogue(redis_factory=lambda: _BytesRedis())
        assert len(await cat.get_all()) == 2

    async def test_absent_factory_is_not_an_error(self):
        assert await _catalogue().get_all() == []


class TestProviderFallthrough:
    async def test_empty_redis_falls_through_to_http(self):
        cat = _catalogue(redis_factory=lambda: _FakeRedis(None), http_base_url="http://pc")
        cat._from_http = lambda: _async(_ROWS)  # noqa: SLF001
        assert len(await cat.get_all()) == 2

    async def test_raising_redis_falls_through_to_http(self):
        cat = _catalogue(redis_factory=lambda: _FakeRedis(raises=True), http_base_url="http://pc")
        cat._from_http = lambda: _async(_ROWS)  # noqa: SLF001
        assert len(await cat.get_all()) == 2

    async def test_db_is_tried_before_http(self):
        order = []

        cat = _catalogue()
        cat._from_redis = lambda: _record(order, "redis", [])  # noqa: SLF001
        cat._from_db = lambda: _record(order, "db", _ROWS)  # noqa: SLF001
        cat._from_http = lambda: _record(order, "http", _ROWS)  # noqa: SLF001

        await cat.get_all()
        assert order == ["redis", "db"], "http must not be reached once the DB answers"


class TestDegradation:
    async def test_all_providers_failing_returns_the_stale_snapshot(self):
        redis = _FakeRedis(_ROWS)
        cat = _catalogue(redis_factory=lambda: redis, ttl_seconds=0)
        assert len(await cat.get_all()) == 2

        redis.raises = True
        # TTL 0 forces a re-read on every call, so this genuinely re-enters the
        # provider chain and finds nothing.
        assert len(await cat.get_all()) == 2, "a stale catalogue beats an empty one"

    async def test_never_loaded_and_unreachable_returns_empty_without_raising(self):
        cat = _catalogue(redis_factory=lambda: _FakeRedis(raises=True))
        assert await cat.get_all() == []

    async def test_get_all_never_raises_even_with_a_broken_factory(self):
        def _boom():
            raise RuntimeError("no client")

        assert await _catalogue(redis_factory=_boom).get_all() == []


class TestSnapshotAndTtl:
    async def test_within_ttl_costs_no_io(self):
        redis = _FakeRedis(_ROWS)
        cat = _catalogue(redis_factory=lambda: redis, ttl_seconds=300)
        await cat.get_all()
        await cat.get_all()
        await cat.get_all()
        assert redis.calls == 1, "the process snapshot is what keeps /auth/validate cheap"

    async def test_concurrent_misses_cost_one_fetch(self):
        redis = _FakeRedis(_ROWS)
        cat = _catalogue(redis_factory=lambda: redis, ttl_seconds=300)
        await asyncio.gather(*(cat.get_all() for _ in range(10)))
        assert redis.calls == 1, "the refresh lock must collapse a thundering herd"

    async def test_sync_snapshot_is_empty_before_the_first_read(self):
        cat = _catalogue(redis_factory=lambda: _FakeRedis(_ROWS))
        assert cat.snapshot() == []
        await cat.get_all()
        assert len(cat.snapshot()) == 2
        assert cat.unit_map_snapshot()["asr"] == "audio_minutes"


class TestLookups:
    async def test_get_by_name_is_case_insensitive(self):
        cat = _catalogue(redis_factory=lambda: _FakeRedis(_ROWS))
        assert (await cat.get_by_name("  ASR "))["id"] == 2

    async def test_get_by_name_misses_return_none(self):
        cat = _catalogue(redis_factory=lambda: _FakeRedis(_ROWS))
        assert await cat.get_by_name("nope") is None
        assert await cat.get_by_name("") is None

    async def test_get_unit_map(self):
        cat = _catalogue(redis_factory=lambda: _FakeRedis(_ROWS))
        assert await cat.get_unit_map() == {"llm": "tokens", "asr": "audio_minutes"}

    async def test_get_by_path_matches_an_alias_not_just_the_canonical_path(self):
        cat = _catalogue(redis_factory=lambda: _FakeRedis(_ROWS))
        assert (await cat.get_by_path("/api/v1/chat/completions"))["name"] == "llm"

    async def test_get_by_path_strips_query_and_trailing_slash(self):
        cat = _catalogue(redis_factory=lambda: _FakeRedis(_ROWS))
        assert (await cat.get_by_path("/api/v1/asr/inference/?x=1"))["name"] == "asr"

    async def test_unknown_path_resolves_to_none(self):
        # None means "not a metered endpoint, proceed" — never a rejection.
        cat = _catalogue(redis_factory=lambda: _FakeRedis(_ROWS))
        assert await cat.get_by_path("/api/v1/inference") is None


@pytest.mark.filterwarnings("ignore::pytest.PytestWarning")
class TestLegacyProjection:
    """Pure function — the module-level asyncio mark does not apply here."""

    def test_round_trips_the_llm_alias(self):
        legacy = to_legacy_entry(_ROWS[0])
        assert legacy["endpoint_pattern"] == "/api/v1/chat"
        assert legacy["endpoint_aliases"] == ["/api/v1/chat/completions"]

    def test_single_pattern_has_no_aliases(self):
        assert to_legacy_entry(_ROWS[1])["endpoint_aliases"] == []

    def test_endpoint_pattern_is_always_a_string(self):
        # The frontend's zod schema declares it required and non-null.
        assert to_legacy_entry({"name": "x", "endpoint_patterns": []})["endpoint_pattern"] == ""


async def _async(value):
    return value


async def _record(order, name, value):
    order.append(name)
    return value
