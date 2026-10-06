"""Tiered cache: L1 in-process memory -> L2 Redis -> L3 Postgres.

One read() serves a whole request: L1 first, then ONE Redis pipeline for all
its misses, then one DB query per key kind for what Redis did not have, then
ONE fill pipeline. Concurrent misses of the same key in one process share one
future (single flight). Only the shared settings snapshot is filled under a
cross-pod lock. Cold fillers write with SET NX; writers that just changed the
DB write with plain SET and PUBLISH an invalidation.
"""

import asyncio
import hashlib
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Mapping, Optional, Sequence, Tuple

from cachetools import TTLCache

from . import constants as c
from . import metrics
from .config import NotificationSettings
from .constants import CacheLayer, CacheName, CacheResult, FailureCode, FailureStage, InvalidationKind, Operation
from .failure_log import FailureLogger
from .invalidation import InvalidationMessage, build_message
from .keys import subscription_key
from .ledger import read_states
from .models import LedgerRef, LedgerState, SettingsSnapshot, TenantSubscriptions
from .settings import load_settings_snapshot, load_subscriptions_many

logger = logging.getLogger(__name__)

#: notification_name of CACHE failure rows not tied to one notification.
ANY_NOTIFICATION = "*"


class SettingsUnavailable(Exception):
    """No settings snapshot: Redis, the DB and the stale copy all failed."""


@dataclass
class CacheRead:
    settings: Optional[SettingsSnapshot] = None
    subscriptions: Dict[str, TenantSubscriptions] = field(default_factory=dict)
    ledger: Dict[str, LedgerState] = field(default_factory=dict)
    settings_error: Optional[BaseException] = None
    subscription_error: Optional[BaseException] = None
    ledger_error: Optional[BaseException] = None


def _count(cache: CacheName, layer: CacheLayer, result: CacheResult, n: int = 1) -> None:
    if n:
        metrics.CACHE_REQUESTS.labels(cache.value, layer.value, result.value).inc(n)


def _text(raw) -> Optional[str]:
    if raw is None:
        return None
    return raw.decode("utf-8") if isinstance(raw, bytes) else str(raw)


def _parse(raw, loader):
    """Parse a Redis value; None when absent or malformed (treated as a miss)."""
    value = _text(raw)
    if value is None:
        return None
    try:
        return loader(json.loads(value))
    except Exception:
        logger.warning("Ignoring a malformed notification cache value")
        return None


class TieredCache:
    def __init__(
        self,
        *,
        redis,
        session_factory,
        config: NotificationSettings,
        failure_log: FailureLogger,
        origin: str,
        clock: Callable[[], float] = time.monotonic,
    ):
        self._redis = redis
        self._session_factory = session_factory
        self._config = config
        self._failures = failure_log
        self._origin = origin
        self._clock = clock
        self._settings_l1: TTLCache = TTLCache(maxsize=1, ttl=config.notif_l1_settings_ttl_s, timer=clock)
        self._subs_l1: TTLCache = TTLCache(maxsize=config.notif_l1_sub_max, ttl=config.notif_l1_sub_ttl_s, timer=clock)
        self._ledger_l1: TTLCache = TTLCache(maxsize=config.notif_l1_ledger_max, ttl=config.notif_l1_ledger_ttl_s, timer=clock)
        #: Last good snapshot and when it was loaded — served only when Redis
        #: and the DB are both down.
        self._last_good: Optional[Tuple[SettingsSnapshot, float]] = None
        self._settings_fill_failed_at: Optional[float] = None
        self._inflight: Dict[str, asyncio.Future] = {}
        self._release_sha = hashlib.sha1(c.LOCK_RELEASE_SCRIPT.encode("utf-8")).hexdigest()

    # ── L1 access ─────────────────────────────────────────────────────────

    def peek_settings(self) -> Optional[SettingsSnapshot]:
        """The L1 settings snapshot, without any I/O."""
        return self._settings_l1.get(c.SETTINGS_KEY)

    def peek_subscriptions(self, tenant_id: str) -> Optional[TenantSubscriptions]:
        """One tenant's L1 subscriptions, without any I/O."""
        return self._subs_l1.get(str(tenant_id))

    def _set_settings_l1(self, snapshot: SettingsSnapshot) -> None:
        self._settings_l1[c.SETTINGS_KEY] = snapshot
        self._last_good = (snapshot, self._clock())

    def drop_settings(self) -> None:
        self._settings_l1.pop(c.SETTINGS_KEY, None)

    def drop_subscription(self, tenant_id: str) -> None:
        self._subs_l1.pop(str(tenant_id), None)

    def drop_ledger(self, keys: Sequence[str]) -> None:
        for key in keys:
            self._ledger_l1.pop(key, None)

    def drop_all(self) -> None:
        self._settings_l1.clear()
        self._subs_l1.clear()
        self._ledger_l1.clear()

    def apply_invalidation(self, message: InvalidationMessage) -> None:
        if message.kind is InvalidationKind.SETTINGS:
            self.drop_settings()
        elif message.kind is InvalidationKind.SUBSCRIPTION and message.tenant_id is not None:
            self.drop_subscription(message.tenant_id)
        elif message.kind is InvalidationKind.LEDGER:
            self.drop_ledger(message.keys)
        else:
            self.drop_all()

    # ── Single flight ─────────────────────────────────────────────────────

    def _claim(self, key: str, owned: Dict[str, asyncio.Future], waits: Dict[str, asyncio.Future]) -> bool:
        """True when this call owns loading `key`; False when it waits for the
        call already loading it."""
        future = self._inflight.get(key)
        if future is not None:
            waits[key] = future
            return False
        future = asyncio.get_running_loop().create_future()
        self._inflight[key] = future
        owned[key] = future
        return True

    # ── Read ──────────────────────────────────────────────────────────────

    async def read(
        self,
        *,
        tenant_ids: Sequence[str] = (),
        ledger_refs: Sequence[LedgerRef] = (),
        context_name=ANY_NOTIFICATION,
    ) -> CacheRead:
        """Settings snapshot, plus the subscriptions of `tenant_ids` and the
        ledger states of `ledger_refs`. Per-kind errors are returned, not
        raised."""
        out = CacheRead()
        tenants = list(dict.fromkeys(str(t) for t in tenant_ids))
        refs = list({ref.key: ref for ref in ledger_refs}.values())

        # 1. L1
        snapshot = self.peek_settings()
        _count(CacheName.SETTINGS, CacheLayer.L1, CacheResult.HIT if snapshot else CacheResult.MISS)
        subs_missing: List[str] = []
        for tenant in tenants:
            value = self._subs_l1.get(tenant)
            if value is None:
                subs_missing.append(tenant)
            else:
                out.subscriptions[tenant] = value
        refs_missing: List[LedgerRef] = []
        for ref in refs:
            value = self._ledger_l1.get(ref.key)
            if value is None:
                refs_missing.append(ref)
            else:
                out.ledger[ref.key] = value
        _count(CacheName.SUBSCRIPTION, CacheLayer.L1, CacheResult.HIT, len(tenants) - len(subs_missing))
        _count(CacheName.SUBSCRIPTION, CacheLayer.L1, CacheResult.MISS, len(subs_missing))
        _count(CacheName.LEDGER, CacheLayer.L1, CacheResult.HIT, len(refs) - len(refs_missing))
        _count(CacheName.LEDGER, CacheLayer.L1, CacheResult.MISS, len(refs_missing))

        # 2. single flight
        owned: Dict[str, asyncio.Future] = {}
        waits: Dict[str, asyncio.Future] = {}
        own_settings = snapshot is None and self._claim(c.SETTINGS_KEY, owned, waits)
        own_subs = [t for t in subs_missing if self._claim(subscription_key(t), owned, waits)]
        own_refs = [r for r in refs_missing if self._claim(r.key, owned, waits)]

        try:
            if owned:
                snapshot = await self._load_owned(
                    out, snapshot, own_settings, own_subs, own_refs, owned, context_name,
                    settings_wait=waits.get(c.SETTINGS_KEY),
                )
        finally:
            for key, future in owned.items():
                if not future.done():
                    future.set_exception(RuntimeError("notification cache load did not complete"))
                    future.exception()  # mark retrieved
                self._inflight.pop(key, None)

        # 3. wait for loads owned by other coroutines
        for key, future in waits.items():
            try:
                value = await asyncio.shield(future)
            except Exception as exc:
                if key == c.SETTINGS_KEY:
                    out.settings_error = out.settings_error or exc
                elif key.startswith(c.SUBSCRIPTION_KEY_PREFIX):
                    out.subscription_error = out.subscription_error or exc
                else:
                    out.ledger_error = out.ledger_error or exc
                continue
            if key == c.SETTINGS_KEY:
                snapshot = snapshot or value
            elif key.startswith(c.SUBSCRIPTION_KEY_PREFIX):
                out.subscriptions[value.tenant_id] = value
            else:
                out.ledger[key] = value

        out.settings = snapshot
        if snapshot is None and out.settings_error is None:
            out.settings_error = SettingsUnavailable("no settings snapshot")
        return out

    async def _load_owned(
        self,
        out: CacheRead,
        snapshot: Optional[SettingsSnapshot],
        own_settings: bool,
        own_subs: List[str],
        own_refs: List[LedgerRef],
        owned: Dict[str, asyncio.Future],
        context_name,
        settings_wait: Optional[asyncio.Future] = None,
    ) -> Optional[SettingsSnapshot]:
        # Redis: one pipeline for every owned miss
        redis_ok = True
        raw_settings = None
        raw_subs: List = [None] * len(own_subs)
        raw_refs: List = [None] * len(own_refs)
        try:
            pipe = self._redis.pipeline(transaction=False)
            if own_settings:
                pipe.get(c.SETTINGS_KEY)
            for tenant in own_subs:
                pipe.get(subscription_key(tenant))
            if own_refs:
                pipe.mget([r.key for r in own_refs])
            results = list(await pipe.execute())
            if own_settings:
                raw_settings = results.pop(0)
            raw_subs = results[: len(own_subs)]
            if own_refs:
                raw_refs = list(results[len(own_subs)])
        except Exception as exc:
            redis_ok = False
            _count(CacheName.SETTINGS, CacheLayer.L2, CacheResult.ERROR)
            await self._failures.record(
                FailureStage.CACHE, FailureCode.CACHE_READ_FAILED,
                notification_name=context_name, operation=Operation.CACHE_READ, error=exc,
            )

        fills: List[Tuple[str, str, int]] = []  # (key, json, ttl) written with SET NX

        # Settings
        lock_token = None
        if own_settings:
            snapshot = _parse(raw_settings, SettingsSnapshot.from_json)
            if snapshot is not None:
                _count(CacheName.SETTINGS, CacheLayer.L2, CacheResult.HIT)
                self._set_settings_l1(snapshot)
            else:
                if redis_ok:
                    _count(CacheName.SETTINGS, CacheLayer.L2, CacheResult.MISS)
                try:
                    snapshot, lock_token, from_db = await self._fill_settings(redis_ok, context_name)
                    if from_db:
                        fills.append((c.SETTINGS_KEY, json.dumps(snapshot.to_json()), self._config.notif_redis_settings_ttl_s))
                except Exception as exc:
                    out.settings_error = exc
                    owned[c.SETTINGS_KEY].set_exception(exc)
                    owned[c.SETTINGS_KEY].exception()
            if snapshot is not None and not owned[c.SETTINGS_KEY].done():
                owned[c.SETTINGS_KEY].set_result(snapshot)

        # Subscriptions
        subs_db: List[str] = []
        for tenant, raw in zip(own_subs, raw_subs):
            value = _parse(raw, TenantSubscriptions.from_json)
            if value is None:
                subs_db.append(tenant)
                continue
            self._subs_l1[tenant] = value
            out.subscriptions[tenant] = value
            owned[subscription_key(tenant)].set_result(value)
        _count(CacheName.SUBSCRIPTION, CacheLayer.L2, CacheResult.HIT, len(own_subs) - len(subs_db))
        _count(CacheName.SUBSCRIPTION, CacheLayer.L2, CacheResult.MISS, len(subs_db))
        if subs_db:
            try:
                async with self._session_factory() as session:
                    loaded = await load_subscriptions_many(session, subs_db)
                _count(CacheName.SUBSCRIPTION, CacheLayer.L3, CacheResult.HIT, len(subs_db))
                for tenant in subs_db:
                    value = loaded[tenant]
                    self._subs_l1[tenant] = value
                    out.subscriptions[tenant] = value
                    owned[subscription_key(tenant)].set_result(value)
                    fills.append((subscription_key(tenant), json.dumps(value.to_json()), self._config.notif_redis_sub_ttl_s))
            except Exception as exc:
                _count(CacheName.SUBSCRIPTION, CacheLayer.L3, CacheResult.ERROR, len(subs_db))
                out.subscription_error = exc
                for tenant in subs_db:
                    owned[subscription_key(tenant)].set_exception(exc)
                    owned[subscription_key(tenant)].exception()

        # Ledger
        refs_db: List[LedgerRef] = []
        for ref, raw in zip(own_refs, raw_refs):
            value = _parse(raw, LedgerState.from_json)
            if value is None:
                refs_db.append(ref)
                continue
            self._ledger_l1[ref.key] = value
            out.ledger[ref.key] = value
            owned[ref.key].set_result(value)
        _count(CacheName.LEDGER, CacheLayer.L2, CacheResult.HIT, len(own_refs) - len(refs_db))
        _count(CacheName.LEDGER, CacheLayer.L2, CacheResult.MISS, len(refs_db))
        if refs_db:
            try:
                if snapshot is None and settings_wait is not None:
                    # Another coroutine is loading settings; the catalog ids come from it.
                    snapshot = await asyncio.shield(settings_wait)
                if snapshot is None:
                    raise SettingsUnavailable("ledger state needs the settings snapshot")
                pairs = []
                for ref in refs_db:
                    row = snapshot.get(ref.name)
                    if row is None:
                        raise KeyError(f"{ref.name.value} is not in the catalog")
                    pairs.append((row.id, ref))
                async with self._session_factory() as session:
                    states = await read_states(session, pairs)
                _count(CacheName.LEDGER, CacheLayer.L3, CacheResult.HIT, len(refs_db))
                for ref in refs_db:
                    value = states[ref.key]
                    self._ledger_l1[ref.key] = value
                    out.ledger[ref.key] = value
                    owned[ref.key].set_result(value)
                    fills.append((ref.key, json.dumps(value.to_json()), self._config.notif_redis_ledger_ttl_s))
            except Exception as exc:
                _count(CacheName.LEDGER, CacheLayer.L3, CacheResult.ERROR, len(refs_db))
                out.ledger_error = exc
                for ref in refs_db:
                    owned[ref.key].set_exception(exc)
                    owned[ref.key].exception()

        # One fill pipeline: SET NX for every filled key, and the lock release
        if redis_ok and (fills or lock_token):
            await self._fill(fills, lock_token, context_name)
        return snapshot

    async def _fill_settings(self, redis_ok: bool, context_name) -> Tuple[SettingsSnapshot, Optional[str], bool]:
        """(snapshot, lock token to release, loaded from the DB). Serves the
        stale snapshot when the DB fails; raises when there is none."""
        now = self._clock()
        if self._settings_fill_failed_at is not None and now - self._settings_fill_failed_at < c.SETTINGS_FILL_BACKOFF_S:
            return self._stale(), None, False

        token = None
        if redis_ok:
            try:
                candidate = f"{self._origin}:{uuid.uuid4()}"
                if await self._redis.set(c.SETTINGS_FILL_LOCK_KEY, candidate, nx=True, px=c.SETTINGS_FILL_LOCK_TTL_MS):
                    token = candidate
                else:
                    for _ in range(c.SETTINGS_FILL_POLL_ATTEMPTS):
                        await asyncio.sleep(c.SETTINGS_FILL_POLL_INTERVAL_S)
                        snapshot = _parse(await self._redis.get(c.SETTINGS_KEY), SettingsSnapshot.from_json)
                        if snapshot is not None:
                            _count(CacheName.SETTINGS, CacheLayer.L2, CacheResult.HIT)
                            self._set_settings_l1(snapshot)
                            return snapshot, None, False
            except Exception as exc:
                await self._failures.record(
                    FailureStage.CACHE, FailureCode.CACHE_READ_FAILED, notification_name=context_name,
                    operation=Operation.CACHE_READ, error=exc, redis_key=c.SETTINGS_FILL_LOCK_KEY,
                )

        try:
            async with self._session_factory() as session:
                snapshot = await load_settings_snapshot(session)
        except Exception as exc:
            self._settings_fill_failed_at = self._clock()
            _count(CacheName.SETTINGS, CacheLayer.L3, CacheResult.ERROR)
            if token is not None:
                await self._release(token)
            logger.warning("Notification settings fill failed: %s", exc)
            stale = self._stale(exc)
            await self._failures.record(
                FailureStage.SETTINGS, FailureCode.SETTINGS_UNAVAILABLE, notification_name=context_name,
                operation=Operation.SETTINGS_FILL, error=exc, message="serving the last good settings snapshot",
            )
            return stale, None, False
        self._settings_fill_failed_at = None
        _count(CacheName.SETTINGS, CacheLayer.L3, CacheResult.HIT)
        self._set_settings_l1(snapshot)
        return snapshot, token, True

    def _stale(self, cause: Optional[BaseException] = None) -> SettingsSnapshot:
        if self._last_good is not None and self._clock() - self._last_good[1] < c.STALE_SETTINGS_MAX_AGE_S:
            return self._last_good[0]
        raise SettingsUnavailable("settings unavailable and no recent snapshot") from cause

    async def _fill(self, fills: List[Tuple[str, str, int]], lock_token: Optional[str], context_name) -> None:
        try:
            pipe = self._redis.pipeline(transaction=False)
            for key, value, ttl in fills:
                pipe.set(key, value, nx=True, ex=ttl)
            if lock_token is not None:
                pipe.evalsha(self._release_sha, 1, c.SETTINGS_FILL_LOCK_KEY, lock_token)
            results = await pipe.execute(raise_on_error=False)
            if lock_token is not None and isinstance(results[-1], Exception):
                # Script not cached on this Redis yet: plain EVAL once.
                await self._release(lock_token)
        except Exception as exc:
            await self._failures.record(
                FailureStage.CACHE, FailureCode.CACHE_WRITE_FAILED, notification_name=context_name,
                operation=Operation.CACHE_WRITE, error=exc,
            )

    async def _release(self, token: str) -> None:
        try:
            await self._redis.eval(c.LOCK_RELEASE_SCRIPT, 1, c.SETTINGS_FILL_LOCK_KEY, token)
        except Exception:
            logger.debug("Settings fill lock release failed; it expires on its own", exc_info=True)

    # ── Writers: plain SET (overwrite) + PUBLISH ──────────────────────────

    async def write_settings(self, snapshot: SettingsSnapshot, names: Sequence[str]) -> None:
        """After a catalog commit: SET K1, PUBLISH SETTINGS, update own L1."""
        self._set_settings_l1(snapshot)
        message = build_message(InvalidationKind.SETTINGS, self._origin, names=names)
        await self._write(
            {c.SETTINGS_KEY: (json.dumps(snapshot.to_json()), self._config.notif_redis_settings_ttl_s)},
            [message], context_name=names[0] if names else ANY_NOTIFICATION,
        )

    async def write_subscriptions(self, values: Sequence[TenantSubscriptions]) -> None:
        """After a subscription commit: SET K2 and PUBLISH SUBSCRIPTION for
        every tenant in one pipeline, update own L1."""
        if not values:
            return
        for value in values:
            self._subs_l1[value.tenant_id] = value
        await self._write(
            {
                subscription_key(v.tenant_id): (json.dumps(v.to_json()), self._config.notif_redis_sub_ttl_s)
                for v in values
            },
            [build_message(InvalidationKind.SUBSCRIPTION, self._origin, tenant_id=v.tenant_id) for v in values],
            context_name=ANY_NOTIFICATION,
            tenant_id=values[0].tenant_id if len(values) == 1 else None,
        )

    async def write_ledger(
        self,
        changed: Mapping[str, LedgerState],
        refreshed: Mapping[str, LedgerState],
        names: Sequence[str],
    ) -> None:
        """After claims/resets: SET every changed and refreshed K3 key, and one
        PUBLISH LEDGER listing the changed keys. Updates own L1."""
        values: Dict[str, Tuple[str, int]] = {}
        for key, state in list(refreshed.items()) + list(changed.items()):
            self._ledger_l1[key] = state
            values[key] = (json.dumps(state.to_json()), self._config.notif_redis_ledger_ttl_s)
        if not values:
            return
        messages = (
            [build_message(InvalidationKind.LEDGER, self._origin, names=names, keys=list(changed))]
            if changed else []
        )
        await self._write(values, messages, context_name=names[0] if names else ANY_NOTIFICATION)

    async def _write(
        self,
        values: Mapping[str, Tuple[str, int]],
        messages: Sequence[str],
        *,
        context_name,
        tenant_id: Optional[str] = None,
    ) -> None:
        keys = list(values)
        try:
            pipe = self._redis.pipeline(transaction=False)
            for key, (value, ttl) in values.items():
                pipe.set(key, value, ex=ttl)
            for message in messages:
                pipe.publish(c.INVALIDATION_CHANNEL, message)
            results = list(await pipe.execute(raise_on_error=False))
        except Exception as exc:
            results = [exc] * (len(keys) + len(messages))
        failed_keys = [key for key, result in zip(keys, results) if isinstance(result, Exception)]
        publish_error = next((r for r in results[len(keys):] if isinstance(r, Exception)), None)
        for key in failed_keys:
            await self._failures.record(
                FailureStage.CACHE, FailureCode.CACHE_WRITE_FAILED, notification_name=context_name,
                operation=Operation.CACHE_WRITE, error=results[keys.index(key)], redis_key=key, tenant_id=tenant_id,
            )
        if publish_error is not None:
            await self._failures.record(
                FailureStage.CACHE, FailureCode.INVALIDATION_PUBLISH_FAILED, notification_name=context_name,
                operation=Operation.INVALIDATION_PUBLISH, error=publish_error,
                redis_key=c.INVALIDATION_CHANNEL, tenant_id=tenant_id,
            )
        stale_keys = keys if publish_error is not None else failed_keys
        if stale_keys:
            try:
                await self._redis.delete(*stale_keys)
            except Exception:
                logger.debug("Could not delete notification cache keys after a failed write", exc_info=True)
