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

2. **The upsert must still key off ``inference_name``.** ``inference_type_id``
   is written but never joined or conflicted on. If someone "finishes the
   migration" by moving the JOIN or the ON CONFLICT target onto the FK while any
   tier_quotas row still carries a NULL id, quota_upsert returns no row →
   ``quota_recorded=False`` → ``quota_exhausted`` defaults to True → tenants get
   429'd on a working tier. TestUpsertStillKeysOffInferenceName is the guard.

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
    deduct_balance_and_update_quota,
    get_inference_type_id,
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
        inference_name="asr",
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

    async def test_do_update_backfills_the_id(self):
        db = _upsert_session()
        await _run_upsert(db, tier_id="tier-1", inference_type_id=2)
        # Rows written before this change carry NULL; the DO UPDATE clause lets
        # them backfill themselves on the next billing event.
        assert "inference_type_id = EXCLUDED.inference_type_id" in db.sql


class TestUpsertStillKeysOffInferenceName:
    """Phase-1 regression guard. See this module's docstring for the failure."""

    async def test_join_predicate_is_inference_name(self):
        db = _upsert_session()
        await _run_upsert(db, tier_id="tier-1", inference_type_id=2)
        assert "tq.inference_name = CAST(:inference_name AS text)" in db.sql

    async def test_join_predicate_is_not_the_fk(self):
        db = _upsert_session()
        await _run_upsert(db, tier_id="tier-1", inference_type_id=2)
        assert "tq.inference_type_id" not in db.sql

    async def test_conflict_target_is_inference_name(self):
        db = _upsert_session()
        await _run_upsert(db, tier_id="tier-1", inference_type_id=2)
        assert "ON CONFLICT (tenant_id, inference_name, billing_month, tier_id)" in db.sql

    async def test_conflict_target_is_not_the_fk(self):
        db = _upsert_session()
        await _run_upsert(db, tier_id="tier-1", inference_type_id=2)
        assert "ON CONFLICT (tenant_id, inference_type_id" not in db.sql


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

    def test_memo_ttl_is_shorter_than_the_pricing_cache_ttl(self):
        # The memo has no invalidation hook, so it must expire quickly enough
        # that a catalogue change is picked up while Redis is cold.
        assert 0 < Constants.INFERENCE_TYPE_MEMO_TTL < Constants.PRICING_CACHE_TTL
