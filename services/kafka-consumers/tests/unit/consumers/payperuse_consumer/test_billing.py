"""consumers/payperuse_consumer/_billing.py — inference_type_id resolution and
the quota upsert that carries it

Two contracts are pinned here, and both are the kind that fail *silently* if
broken:

1. **``get_inference_type_id`` must never be cache-only.** It reads the hash
   ``core:inference_type:<name>`` that platform-core writes. Those keys live
   under ``allkeys-lru`` pressure (see config.py's BILLED_KEY_TTL comment — the
   dedup keys once evicted unrelated caches), so a cache-only path would stop
   resolving ids under memory pressure with no error anywhere. The DB fallback
   and the process-local memo are load-bearing, not belt-and-braces.

2. **The upsert must key off ``inference_type_id``.** The JOIN and the
   ON CONFLICT target are both on the FK now, and ``inference_name`` is written
   from the joined catalogue row rather than a bound parameter — that is what
   keeps the name-keyed and id-keyed unique constraints equivalent while both
   exist on the table. Regressing either back to the name would silently
   reintroduce free-text writes. TestUpsertKeysOffInferenceTypeId is the guard.

   The failure this replaced is still live, just moved: an unresolved task type
   now yields no quota row, so ``quota_recorded=False``. Reading that as
   exhaustion would 429 every tenant on a working tier, which is why
   handler._bill_usage fails open — see test_handler.py.

It also pins that this consumer never *writes* the shared cache keys: it selects
only ``id``, so writing a partial ``{"id": n}`` back would corrupt the full-row
shape platform-core reads from the same key.

Nothing here needs a broker, database, or Redis.
"""
from __future__ import annotations

import time
from decimal import Decimal

import pytest

from consumers.payperuse_consumer import _billing
from consumers.payperuse_consumer._billing import (
    ServicePricing,
    deduct_balance_and_update_quota,
    fetch_tenant_budget_status,
    get_inference_type_id,
    get_service_pricing,
)
from consumers.payperuse_consumer.config import Constants


# ── Fakes ────────────────────────────────────────────────────────────────────


class _FakeRow:
    def __init__(self, **kw):
        self.__dict__.update(kw)


class _FakeResult:
    def __init__(self, row):
        self._row = row

    def first(self):
        return self._row


class _RecordingSession:
    """Records every execute() as (sql_string, params) and returns queued rows.

    Deliberately not a MagicMock: the SQL text is the thing under test in
    TestUpsertStillKeysOffInferenceName, so it has to be captured verbatim.
    """

    def __init__(self, rows=None):
        self.calls: list[tuple[str, dict | None]] = []
        self._rows = list(rows or [])

    async def execute(self, stmt, params=None):
        self.calls.append((str(stmt), params))
        row = self._rows.pop(0) if self._rows else None
        return _FakeResult(row)

    @property
    def sql(self) -> str:
        return self.calls[-1][0]

    @property
    def params(self) -> dict:
        return self.calls[-1][1]


class _FakeRedis:
    def __init__(self, values=None, hget_raises: Exception | None = None):
        self.values = values or {}
        self.hget_calls: list[tuple[str, str]] = []
        self.writes: list[str] = []
        self._hget_raises = hget_raises

    async def hget(self, key, field):
        self.hget_calls.append((key, field))
        if self._hget_raises is not None:
            raise self._hget_raises
        return self.values.get((key, field))

    # Any write attempt is a bug — platform-core owns these keys.
    async def hset(self, *a, **k):
        self.writes.append("hset")

    async def set(self, *a, **k):
        self.writes.append("set")

    async def setex(self, *a, **k):
        self.writes.append("setex")


@pytest.fixture(autouse=True)
def _clear_inference_type_memo():
    """The memo is module-level mutable state and nothing clears it.

    Without this, a test that populates it leaks into every later test — the
    DB-fallback assertions would pass or fail depending on collection order.
    """
    _billing._inference_type_ids.clear()
    yield
    _billing._inference_type_ids.clear()


def _use_redis(monkeypatch, redis) -> None:
    monkeypatch.setattr(_billing, "get_redis_client", lambda: redis)


def _no_redis(monkeypatch) -> None:
    """get_redis_client raises RuntimeError before init_redis has run."""

    def _raise():
        raise RuntimeError("redis not initialised")

    monkeypatch.setattr(_billing, "get_redis_client", _raise)


# ── get_inference_type_id ────────────────────────────────────────────────────


class TestGetInferenceTypeIdEmptyName:
    async def test_empty_name_returns_none_without_touching_redis_or_db(self, monkeypatch):
        redis = _FakeRedis()
        _use_redis(monkeypatch, redis)
        db = _RecordingSession()

        assert await get_inference_type_id(db, "") is None
        # An empty task_type is the documented "mm_services.task_type unset"
        # case; it must be a cheap no-op, not a wasted round-trip per message.
        assert redis.hget_calls == []
        assert db.calls == []

    async def test_none_name_returns_none(self, monkeypatch):
        _use_redis(monkeypatch, _FakeRedis())
        db = _RecordingSession()
        assert await get_inference_type_id(db, None) is None
        assert db.calls == []


class TestGetInferenceTypeIdFromRedis:
    async def test_cache_hit_returns_int_and_skips_db(self, monkeypatch):
        key = f"{Constants.INFERENCE_TYPE_CACHE_PREFIX}asr"
        redis = _FakeRedis({(key, "id"): "2"})
        _use_redis(monkeypatch, redis)
        db = _RecordingSession()

        assert await get_inference_type_id(db, "asr") == 2
        assert db.calls == [], "cache hit must not hit the DB"

    async def test_reads_only_the_id_field(self, monkeypatch):
        key = f"{Constants.INFERENCE_TYPE_CACHE_PREFIX}llm"
        redis = _FakeRedis({(key, "id"): "1"})
        _use_redis(monkeypatch, redis)

        await get_inference_type_id(_RecordingSession(), "llm")
        # HGET of one field, not HGETALL: the row carries endpoint_patterns/unit/
        # pricing this consumer has no use for.
        assert redis.hget_calls == [(key, "id")]

    async def test_name_is_lowercased_into_the_cache_key(self, monkeypatch):
        key = f"{Constants.INFERENCE_TYPE_CACHE_PREFIX}asr"
        redis = _FakeRedis({(key, "id"): "2"})
        _use_redis(monkeypatch, redis)

        # platform-core stores names lowercased; a mixed-case task_type from
        # mm_services must still resolve.
        assert await get_inference_type_id(_RecordingSession(), "ASR") == 2
        assert redis.hget_calls == [(key, "id")]

    async def test_returned_value_is_an_int_not_the_raw_string(self, monkeypatch):
        key = f"{Constants.INFERENCE_TYPE_CACHE_PREFIX}nmt"
        _use_redis(monkeypatch, _FakeRedis({(key, "id"): "3"}))

        got = await get_inference_type_id(_RecordingSession(), "nmt")
        assert got == 3
        assert isinstance(got, int), "the SQL bind is CAST(:inference_type_id AS int)"

    async def test_never_writes_back_to_redis(self, monkeypatch):
        redis = _FakeRedis()  # cold cache
        _use_redis(monkeypatch, redis)
        db = _RecordingSession([_FakeRow(id=5)])

        await get_inference_type_id(db, "tts")
        # Writing {"id": n} here would clobber the full catalogue row that
        # platform-core reads back from this same key.
        assert redis.writes == []


class TestGetInferenceTypeIdDbFallback:
    async def test_cache_miss_falls_back_to_db(self, monkeypatch):
        _use_redis(monkeypatch, _FakeRedis())
        db = _RecordingSession([_FakeRow(id=7)])

        assert await get_inference_type_id(db, "ocr") == 7
        assert len(db.calls) == 1
        assert "FROM inference_types" in db.sql
        assert db.params == {"name": "ocr"}

    async def test_redis_unavailable_falls_back_to_db(self, monkeypatch):
        _no_redis(monkeypatch)
        db = _RecordingSession([_FakeRow(id=9)])

        # RuntimeError from get_redis_client must not propagate — it means
        # init_redis has not run, which is not a billing failure.
        assert await get_inference_type_id(db, "ner") == 9

    async def test_redis_error_falls_back_to_db(self, monkeypatch):
        redis = _FakeRedis(hget_raises=ConnectionError("boom"))
        _use_redis(monkeypatch, redis)
        db = _RecordingSession([_FakeRow(id=11)])

        # A live-but-broken Redis is the eviction/outage case this fallback
        # exists for; it is logged, never raised.
        assert await get_inference_type_id(db, "pipeline") == 11

    async def test_db_param_is_lowercased(self, monkeypatch):
        _no_redis(monkeypatch)
        db = _RecordingSession([_FakeRow(id=4)])

        await get_inference_type_id(db, "TTS")
        assert db.params == {"name": "tts"}

    async def test_unknown_name_returns_none(self, monkeypatch):
        _no_redis(monkeypatch)
        db = _RecordingSession([None])

        # None is safe: quota_usage.inference_type_id is nullable in phase 1.
        assert await get_inference_type_id(db, "does-not-exist") is None


class TestGetInferenceTypeIdMemo:
    async def test_second_call_uses_memo_not_db(self, monkeypatch):
        _no_redis(monkeypatch)
        db = _RecordingSession([_FakeRow(id=2)])

        assert await get_inference_type_id(db, "asr") == 2
        assert await get_inference_type_id(db, "asr") == 2
        # The memo exists so a cold Redis costs one query per task type per
        # process, not one per Kafka message.
        assert len(db.calls) == 1

    async def test_negative_result_is_memoised(self, monkeypatch):
        _no_redis(monkeypatch)
        db = _RecordingSession([None])

        assert await get_inference_type_id(db, "ghost") is None
        assert await get_inference_type_id(db, "ghost") is None
        # A missing type must not re-query on every message either.
        assert len(db.calls) == 1

    async def test_expired_memo_requeries_db(self, monkeypatch):
        _no_redis(monkeypatch)
        _billing._inference_type_ids["asr"] = (99, time.monotonic() - 1)
        db = _RecordingSession([_FakeRow(id=2)])

        # Stale entry must not win, or a rename/re-seed would never be picked up
        # while Redis stays cold.
        assert await get_inference_type_id(db, "asr") == 2
        assert len(db.calls) == 1

    async def test_redis_is_checked_before_the_memo(self, monkeypatch):
        key = f"{Constants.INFERENCE_TYPE_CACHE_PREFIX}asr"
        _use_redis(monkeypatch, _FakeRedis({(key, "id"): "2"}))
        _billing._inference_type_ids["asr"] = (99, time.monotonic() + 300)
        db = _RecordingSession()

        # Redis is authoritative over the memo, so a mutation in platform-core
        # takes effect within one message rather than one memo TTL.
        assert await get_inference_type_id(db, "asr") == 2
        assert db.calls == []

    async def test_memo_is_keyed_lowercased(self, monkeypatch):
        _no_redis(monkeypatch)
        db = _RecordingSession([_FakeRow(id=2)])

        await get_inference_type_id(db, "ASR")
        await get_inference_type_id(db, "asr")
        assert len(db.calls) == 1, "case variants must share one memo entry"


# ── deduct_balance_and_update_quota ─────────────────────────────────────────


def _upsert_session(row=None) -> _RecordingSession:
    return _RecordingSession([row])


async def _run_upsert(db, **overrides):
    kwargs = dict(
        tenant_id="tenant-1",
        billing_month="2026-08",
        units=Decimal("10"),
        cost=Decimal("1.5"),
    )
    kwargs.update(overrides)
    return await deduct_balance_and_update_quota(db, **kwargs)


class TestUpsertBindsInferenceTypeId:
    async def test_id_is_bound_into_params(self):
        db = _upsert_session()
        await _run_upsert(db, tier_id="tier-1", inference_type_id=2)
        assert db.params["inference_type_id"] == 2

    async def test_defaults_to_none_when_not_passed(self):
        db = _upsert_session()
        await _run_upsert(db, tier_id="tier-1")
        # Callers that cannot resolve a type must still be able to bill.
        assert db.params["inference_type_id"] is None

    async def test_none_is_bound_not_omitted(self):
        db = _upsert_session()
        await _run_upsert(db, tier_id="tier-1", inference_type_id=None)
        # The bind must exist even when None — a missing key raises on execute.
        assert "inference_type_id" in db.params

    async def test_column_and_cast_are_in_the_insert(self):
        db = _upsert_session()
        await _run_upsert(db, tier_id="tier-1", inference_type_id=2)
        assert "inference_type_id" in db.sql
        # int, not text: the FK column is INT REFERENCES inference_types(id).
        assert "CAST(:inference_type_id AS int)" in db.sql

    async def test_name_is_not_bound_at_all(self):
        db = _upsert_session()
        await _run_upsert(db, tier_id="tier-1", inference_type_id=2)
        # The kwarg is gone and the parameter with it: the persisted name comes
        # from the catalogue join, never from the caller.
        assert "inference_name" not in db.params
        assert ":inference_name" not in db.sql

    async def test_do_update_backfills_the_name(self):
        db = _upsert_session()
        await _run_upsert(db, tier_id="tier-1", inference_type_id=2)
        # The id is the conflict target now, so it is already correct. The name
        # is what self-heals — a legacy case-variant row is rewritten to the
        # catalogue spelling on its next billing event.
        assert "inference_name = EXCLUDED.inference_name" in db.sql


class TestUpsertKeysOffInferenceTypeId:
    """Phase-2 regression guard, against reverting to the free-text name."""

    async def test_join_predicate_is_the_fk(self):
        db = _upsert_session()
        await _run_upsert(db, tier_id="tier-1", inference_type_id=2)
        assert "tq.inference_type_id = CAST(:inference_type_id AS int)" in db.sql

    async def test_join_predicate_is_not_the_name(self):
        db = _upsert_session()
        await _run_upsert(db, tier_id="tier-1", inference_type_id=2)
        assert "tq.inference_name" not in db.sql

    async def test_conflict_target_is_the_fk(self):
        db = _upsert_session()
        await _run_upsert(db, tier_id="tier-1", inference_type_id=2)
        assert "ON CONFLICT (tenant_id, inference_type_id, billing_month, tier_id)" in db.sql

    async def test_conflict_target_is_not_the_name(self):
        db = _upsert_session()
        await _run_upsert(db, tier_id="tier-1", inference_type_id=2)
        assert "ON CONFLICT (tenant_id, inference_name" not in db.sql

    async def test_persisted_name_comes_from_the_catalogue(self):
        db = _upsert_session()
        await _run_upsert(db, tier_id="tier-1", inference_type_id=2)
        # The join exists solely to source the canonical name inside the CTE.
        assert "JOIN inference_types it ON it.id = tq.inference_type_id" in db.sql
        assert "it.name" in db.sql

    async def test_inserted_id_comes_from_the_joined_row(self):
        db = _upsert_session()
        await _run_upsert(db, tier_id="tier-1", inference_type_id=2)
        # Equal to the bound value by the join predicate, but sourcing it from
        # tier_quotas makes it NOT NULL by construction — that is what replaces a
        # NOT NULL constraint on quota_usage.inference_type_id.
        assert "tq.inference_type_id, :billing_month" in db.sql


class TestUpsertResultUnaffected:
    async def test_quota_recorded_true_when_row_returned(self):
        row = _FakeRow(
            api_key_budget_used=Decimal("5"),
            api_key_budget_snap=Decimal("100"),
            monthly_quota_used=Decimal("10"),
            monthly_quota_snap=Decimal("500"),
            tier_id="tier-1",
        )
        result = await _run_upsert(_upsert_session(row), tier_id="tier-1", inference_type_id=2)

        # The signal that the join matched. If a future change moves the join
        # onto the FK and this flips False, tenants start getting spurious 429s.
        assert result.quota_recorded is True
        assert result.quota_exhausted is False

    async def test_quota_exhausted_when_used_reaches_snap(self):
        row = _FakeRow(
            api_key_budget_used=Decimal("0"),
            api_key_budget_snap=None,
            monthly_quota_used=Decimal("500"),
            monthly_quota_snap=Decimal("500"),
            tier_id="tier-1",
        )
        result = await _run_upsert(_upsert_session(row), tier_id="tier-1", inference_type_id=2)
        assert result.quota_exhausted is True

    async def test_no_row_means_not_recorded(self):
        result = await _run_upsert(_upsert_session(None), tier_id="tier-1", inference_type_id=2)
        assert result.quota_recorded is False
        # "not entitled" default — handler overrides it when task_type is empty.
        assert result.quota_exhausted is True


# ── get_service_pricing / the pricing-cache-staleness bug ───────────────────
#
# get_service_pricing caches mm_services' pricing columns under
# ``ppu:svc:{service_id}`` for PRICING_CACHE_TTL (1 hour) with no invalidation
# hook of its own — platform-core's CacheService.invalidate_pricing deletes
# that key from the *other* side after a pricing edit commits (see
# platform-core-service/tests/test_cache_service_pricing.py and
# test_service_update.py for that half of the contract). What is pinned here
# is this consumer's half: a cache hit must skip the DB entirely (so the
# scenario below is actually possible), and deleting the key must be
# sufficient — on its own, with no code change on this side — to make the
# very next call observe the new price.


class _FakePricingRedis:
    """Enough of the redis-py hash/pipeline surface for get_service_pricing:
    HGETALL for the read, a HSET+EXPIRE pipeline for the write-on-miss, and
    a plain DELETE — standing in for what
    platform-core's CacheService.invalidate_pricing does on the real shared
    Redis after a price edit commits.
    """

    def __init__(self, seed: dict | None = None):
        # key -> {field: value}, mirroring a real Redis hash.
        self.hashes: dict[str, dict[str, str]] = dict(seed or {})
        self.hgetall_calls: list[str] = []
        self.deletes: list[str] = []

    async def hgetall(self, key):
        self.hgetall_calls.append(key)
        return dict(self.hashes.get(key, {}))

    def pipeline(self):
        return _FakePipeline(self)

    async def delete(self, *keys):
        for key in keys:
            self.deletes.append(key)
            self.hashes.pop(key, None)
        return len(keys)


class _FakePipeline:
    def __init__(self, redis: _FakePricingRedis):
        self._redis = redis
        self._key: str | None = None

    async def hset(self, key, mapping):
        self._key = key
        self._redis.hashes[key] = dict(mapping)

    async def expire(self, key, ttl):
        # TTL expiry isn't modeled — these tests only assert presence/absence
        # of the key, which invalidate_pricing's DELETE controls directly.
        pass

    async def execute(self):
        return None


def _pricing_row(task_type="asr", unit_rate=None, cost_per_unit=None, unit_size=None):
    return _FakeRow(
        task_type=task_type,
        unit_rate=unit_rate,
        cost_per_unit=cost_per_unit,
        unit_size=unit_size,
    )


class TestGetServicePricingCacheHit:
    async def test_cache_hit_returns_cached_values_without_touching_db(self, monkeypatch):
        redis = _FakePricingRedis(
            seed={
                "ppu:svc:svc-1": {
                    "task_type": "asr",
                    "unit_rate": "2.00",
                    "cost_per_unit": "",
                    "unit_size": "",
                }
            }
        )
        _use_redis(monkeypatch, redis)
        db = _RecordingSession()

        pricing = await get_service_pricing(db, "svc-1")

        assert pricing == ServicePricing(
            task_type="asr", unit_rate=Decimal("2.00"), cost_per_unit=None, unit_size=None
        )
        assert db.calls == []  # the whole point of the cache


class TestGetServicePricingCacheMiss:
    async def test_cache_miss_reads_db_and_warms_cache_with_ttl(self, monkeypatch):
        redis = _FakePricingRedis()
        _use_redis(monkeypatch, redis)
        db = _RecordingSession(rows=[_pricing_row(unit_rate=Decimal("1.50"))])

        pricing = await get_service_pricing(db, "svc-1")

        assert pricing.unit_rate == Decimal("1.50")
        assert len(db.calls) == 1
        assert redis.hashes["ppu:svc:svc-1"]["unit_rate"] == "1.50"

    async def test_empty_task_type_is_not_cached(self, monkeypatch):
        """Documented in _billing.py: caching an empty task_type would block
        billing for up to an hour after an admin first sets pricing on a
        service that had none configured yet."""
        redis = _FakePricingRedis()
        _use_redis(monkeypatch, redis)
        db = _RecordingSession(rows=[_pricing_row(task_type="")])

        await get_service_pricing(db, "svc-1")

        assert redis.hashes == {}

    async def test_unknown_service_returns_none(self, monkeypatch):
        redis = _FakePricingRedis()
        _use_redis(monkeypatch, redis)
        db = _RecordingSession(rows=[None])

        assert await get_service_pricing(db, "svc-missing") is None
        assert redis.hashes == {}


class TestPricingCacheStalenessBugScenario:
    """The exact scenario this fix addresses.

    1. A service is priced at unit_rate=1.00 and billed once — that warms
       the cache.
    2. An admin changes the price to unit_rate=2.00 in mm_services (the DB
       row changes; nothing here does that, it stands in for
       ServiceService.update_service's commit).
    3. A consumption request comes in immediately after.

    Without invalidation, step 3 must return the *stale* 1.00 — proving the
    bug is real, not hypothetical. Once the same key is deleted (exactly
    what CacheService.invalidate_pricing does), the very next call must
    return the *new* 2.00 with no other change and no TTL wait.
    """

    async def test_stale_price_is_served_until_the_cache_key_is_invalidated(
        self, monkeypatch
    ):
        redis = _FakePricingRedis()
        _use_redis(monkeypatch, redis)
        service_id = "svc-1"

        # 1. First billing event: DB has the old price, warms the cache.
        db_old = _RecordingSession(rows=[_pricing_row(unit_rate=Decimal("1.00"))])
        first = await get_service_pricing(db_old, service_id)
        assert first.unit_rate == Decimal("1.00")
        assert redis.hashes[f"ppu:svc:{service_id}"]["unit_rate"] == "1.00"

        # 2. Admin revises the price. The DB row is now 2.00 — but nothing
        # has told Redis, so the hash still holds the pre-edit value.
        db_new = _RecordingSession(rows=[_pricing_row(unit_rate=Decimal("2.00"))])

        # 3a. THE BUG: a consumption request right after the edit still
        # gets billed at the old rate, and never even reaches the DB row
        # that already has the correct price.
        stale = await get_service_pricing(db_new, service_id)
        assert stale.unit_rate == Decimal("1.00")
        assert db_new.calls == []  # confirms it was the cache serving this, not db_new

        # 3b. THE FIX: platform-core's CacheService.invalidate_pricing does
        # exactly this DELETE right after the price-edit commit.
        await redis.delete(f"ppu:svc:{service_id}")

        # 4. The very next request — no TTL wait, no restart — gets the new price.
        fixed = await get_service_pricing(db_new, service_id)
        assert fixed.unit_rate == Decimal("2.00")
        assert len(db_new.calls) == 1  # this time it actually fell through to the DB


# ── Cross-service cache-key contract ────────────────────────────────────────


class TestCacheKeyContract:
    def test_prefix_matches_platform_core(self):
        # platform-core's inference_type_cache writes core:inference_type:<name>.
        # Renaming either side silently stops every lookup resolving — there is
        # no error, just a permanent DB fallback and NULL ids on a cold memo.
        assert Constants.INFERENCE_TYPE_CACHE_PREFIX == "core:inference_type:"

    def test_prefix_is_not_this_consumers_namespace(self):
        # Deliberately "core:" and not "ppu:" — the key is owned by
        # platform-core, this consumer is only a reader.
        assert not Constants.INFERENCE_TYPE_CACHE_PREFIX.startswith("ppu:")

    def test_pricing_prefix_matches_platform_cores_invalidator(self):
        # platform-core's CacheService.invalidate_pricing deletes
        # f"ppu:svc:{service_id}" — hardcoded there (cross-service, so no
        # shared import). Renaming this prefix silently stops that DELETE
        # from ever hitting the key this consumer actually reads, and a
        # price edit goes back to waiting out the full TTL with no error.
        assert Constants.PRICING_CACHE_PREFIX == "ppu:svc:"

    def test_memo_ttl_is_shorter_than_the_pricing_cache_ttl(self):
        # The memo has no invalidation hook, so it must expire quickly enough
        # that a catalogue change is picked up while Redis is cold.
        assert 0 < Constants.INFERENCE_TYPE_MEMO_TTL < Constants.PRICING_CACHE_TTL


# ── fetch_tenant_budget_status — BUDGET_THRESHOLD/BUDGET_EXHAUSTED are now
# tenant-level events, never one API key's/Application's own allocation
# running out on its own (design doc §4's subject rule already specified
# ``{}`` — the whole Tenant, not one key — for these two events; the old
# per-key check had drifted from that). See handler.py's
# _publish_usage_crossing_events for where this feeds in. ──────────────────


class _FakeAllResult:
    """Enough of an AsyncSession result for the auth-side query (.all()) —
    distinct from _FakeResult above, which only supports .first()."""

    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _FakeAuthDb:
    """Records the one query fetch_tenant_budget_status sends to auth_db and
    returns pre-seeded rows for it."""

    def __init__(self, rows):
        self._rows = rows
        self.calls: list[tuple[str, dict | None]] = []

    async def execute(self, stmt, params=None):
        self.calls.append((str(stmt), params))
        return _FakeAllResult(self._rows)


class _FakeCoreDb:
    """Records the one query fetch_tenant_budget_status sends to this
    consumer's own DB (the SUM over budget_usage, both used and snap) and
    returns pre-seeded totals for it."""

    def __init__(self, used_total, snap_total=None):
        self._used_total = used_total
        self._snap_total = snap_total
        self.calls: list[tuple[str, dict | None]] = []

    async def execute(self, stmt, params=None):
        self.calls.append((str(stmt), params))
        return _FakeResult(_FakeRow(used_total=self._used_total, snap_total=self._snap_total))


class TestFetchTenantBudgetStatus:
    async def test_no_tenant_row_returns_none(self):
        """Unknown tenant_id — auth_db's query returns nothing at all."""
        auth_db = _FakeAuthDb(rows=[])
        core_db = _FakeCoreDb(used_total=Decimal("0"))

        result = await fetch_tenant_budget_status(auth_db, core_db, "999")

        assert result is None
        # No key ids to sum over — the core_db SUM query must never even fire.
        assert core_db.calls == []

    async def test_tenant_with_no_allocated_budget_returns_none(self):
        """allocated_budget is nullable — a tenant that never had one set
        must degrade to "no ceiling, don't enforce", same as the per-key
        check's own None-snap convention."""
        auth_db = _FakeAuthDb(rows=[_FakeRow(allocated_budget=None, api_key_id=1)])
        core_db = _FakeCoreDb(used_total=Decimal("0"))

        result = await fetch_tenant_budget_status(auth_db, core_db, "1")

        assert result is None
        assert core_db.calls == []

    async def test_tenant_id_not_a_plain_integer_returns_none(self):
        """This consumer never validates the OTel tenantId attribute's shape
        upstream (handler._get_otel_attributes just strips it), and
        tenants.id is an integer column — int() on a non-numeric value would
        raise ValueError *after* the billing write already committed
        (handler._bill_usage), causing a redelivery to re-bill the same
        span. Guarding here, the same way usage_repository.py's
        get_tenant_budgets does with .isdigit(), must return None instead."""
        auth_db = _FakeAuthDb(rows=[])
        core_db = _FakeCoreDb(used_total=Decimal("0"))

        result = await fetch_tenant_budget_status(auth_db, core_db, "not-a-number")

        assert result is None
        # Bails out before ever touching either DB.
        assert auth_db.calls == []
        assert core_db.calls == []

    async def test_tenant_with_no_keys_yet_is_zero_used_no_ceiling(self):
        """A tenant with a budget configured but zero Applications/Keys so
        far (LEFT JOIN yields one row with api_key_id NULL) is real, valid
        tenant-level state — 0 used. snap is None (no ceiling yet), not
        tenants.allocated_budget: with no keys, nothing is reachable."""
        auth_db = _FakeAuthDb(rows=[_FakeRow(allocated_budget=Decimal("100000"), api_key_id=None)])
        core_db = _FakeCoreDb(used_total=Decimal("0"))

        result = await fetch_tenant_budget_status(auth_db, core_db, "1")

        assert result.used == Decimal("0")
        assert result.snap is None
        # Nothing to sum over — the core_db SUM query must never even fire.
        assert core_db.calls == []

    async def test_sums_every_sibling_keys_spend(self):
        """The whole point: two (or more) API keys under the same tenant —
        their spend must be pooled, not read off just one of them."""
        auth_db = _FakeAuthDb(
            rows=[
                _FakeRow(allocated_budget=Decimal("1000"), api_key_id=1),
                _FakeRow(allocated_budget=Decimal("1000"), api_key_id=2),
                _FakeRow(allocated_budget=Decimal("1000"), api_key_id=3),
            ]
        )
        # pre-summed by the fake DB's own SUM() — snap_total is the SUM of
        # the three keys' own api_key_budget_snap, not tenants.allocated_budget.
        core_db = _FakeCoreDb(used_total=Decimal("750"), snap_total=Decimal("900"))

        result = await fetch_tenant_budget_status(auth_db, core_db, "1")

        assert result.used == Decimal("750")
        assert result.snap == Decimal("900")
        # Every sibling key id reached the core_db query — this is what
        # actually pools their spend instead of reading just one key's row.
        assert core_db.calls[0][1]["key_ids"] == [1, 2, 3]

    async def test_ceiling_is_reachable_even_when_under_allocated(self):
        """The bug this guards against: Application/key allocations are only
        rejected when they'd exceed 100% (application_service.py's
        ALLOCATION_TOTAL_EXCEEDED), never when they undershoot it. A tenant
        allocated only 60% of its budget to keys must be able to actually
        reach BUDGET_THRESHOLD/BUDGET_EXHAUSTED once those keys are fully
        spent — comparing against the full tenants.allocated_budget instead
        would make the bands permanently unreachable."""
        auth_db = _FakeAuthDb(rows=[_FakeRow(allocated_budget=Decimal("100000"), api_key_id=1)])
        # This key's own snap (600) is fully spent — 100% of the reachable
        # ceiling — even though it's only 60% of the tenant's allocated_budget.
        core_db = _FakeCoreDb(used_total=Decimal("600"), snap_total=Decimal("600"))

        result = await fetch_tenant_budget_status(auth_db, core_db, "1")

        assert result.used == Decimal("600")
        assert result.snap == Decimal("600")

    async def test_uncapped_keys_contribute_no_ceiling(self):
        """SQL SUM ignores NULL rows — a tenant whose every key is uncapped
        (no Application budget, see CreateAPIKeyRequest.budget's docstring)
        must come back with snap=None (all-NULL sum), same "no ceiling,
        don't enforce" convention as a single NULL per-key snap."""
        auth_db = _FakeAuthDb(rows=[_FakeRow(allocated_budget=Decimal("100000"), api_key_id=1)])
        core_db = _FakeCoreDb(used_total=Decimal("0"), snap_total=None)

        result = await fetch_tenant_budget_status(auth_db, core_db, "1")

        assert result.snap is None

    async def test_revoked_keys_are_not_excluded(self):
        """Same reasoning as auth-service's _sync_ppu_wallet_and_exhaustion:
        a revoked key's past spend still counts against the tenant's pooled
        ceiling — this function has no is_active filter at all, and must
        not gain one."""
        auth_db = _FakeAuthDb(
            rows=[
                _FakeRow(allocated_budget=Decimal("1000"), api_key_id=1),
                _FakeRow(allocated_budget=Decimal("1000"), api_key_id=2),  # revoked, still counted
            ]
        )
        core_db = _FakeCoreDb(used_total=Decimal("900"), snap_total=Decimal("1000"))

        result = await fetch_tenant_budget_status(auth_db, core_db, "1")

        assert core_db.calls[0][1]["key_ids"] == [1, 2]
        assert result.used == Decimal("900")

    async def test_tenant_id_is_cast_to_int_for_the_auth_query(self):
        """ctx.tenant_id travels as a string (OTel attributes) — tenants.id
        is an integer column; binding the raw string would raise on the
        real driver even though this fake doesn't care."""
        auth_db = _FakeAuthDb(rows=[_FakeRow(allocated_budget=Decimal("1"), api_key_id=None)])
        core_db = _FakeCoreDb(used_total=Decimal("0"))

        await fetch_tenant_budget_status(auth_db, core_db, "42")

        assert auth_db.calls[0][1]["tenant_id"] == 42
        assert isinstance(auth_db.calls[0][1]["tenant_id"], int)
