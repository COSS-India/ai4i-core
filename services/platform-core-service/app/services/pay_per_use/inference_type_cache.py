"""Write-through Redis cache for the ``inference_types`` catalogue.

Keys (``core:`` is platform-core's namespace — see ``app/services/cache_service.py``).
Both are Redis **hashes**, so they read with ``HGETALL``/``HGET``, matching the other
hash-shaped caches in this stack (``ppu:svc:*``, ``auth:apikey:*``)::

    core:inference_type:<name>   HASH  id, name, endpoint_patterns, unit, pricing
    core:inference_type:all      HASH  <name> -> compact JSON of that row

``endpoint_patterns`` is a list and a hash field can only hold a string, so that one
field is JSON-encoded. JSON rather than a comma-join because it round-trips exactly and
stays correct if a path ever contains a comma::

    redis-cli HGETALL core:inference_type:asr
    redis-cli HGET    core:inference_type:llm endpoint_patterns
    redis-cli HKEYS   core:inference_type:all      # every type name, one round-trip

**Written here, read across services.** These keys are a cross-service contract:

* ``payperuse_consumer._billing.get_inference_type_id`` does
  ``HGET core:inference_type:<name> id`` to resolve the FK its quota upsert joins and
  conflicts on.
* ``ai4i_core.ppu.catalogue`` reads ``:all`` for auth-service's per-service quota
  check and inference-service's billing-unit labels.

Every reader falls back to the database (or, for inference-service, to platform-core
over HTTP) and none of them writes these keys — this module stays the single writer, so
the full-row shape cannot be corrupted by a partial write from elsewhere.

All of them must point at the same Redis host *and* logical DB. Everything defaults to
``REDIS_DB=0``; that is a real deployment prerequisite, not a formality.

Four rules govern every operation here:

1. **DB commit first, cache second.** The DB is the source of truth; a failed
   cache write is logged, never raised.
2. **Rebuild wholesale on every mutation.** Twelve rows — re-reading all of them
   into one pipeline is cheaper than reasoning about which keys a partial update
   left stale, and it cannot leave ``:all`` disagreeing with the per-name keys.
3. **TTL even though this is write-through.** Without one, a bad write is
   permanent. It is a backstop, not an invalidation mechanism — mutations
   rebuild these keys — so it is long (1 day): a short TTL only bought a
   periodic DB round-trip and rebuild on an otherwise-warm cache.
4. **Every read falls back to the DB and re-warms.** Modelled on
   ``payperuse_consumer._billing.get_service_pricing``. Not optional: these
   caches already run under ``allkeys-lru`` eviction pressure, and a cache-only
   read path would silently stop resolving ids under memory pressure.
"""

import json
import logging
from typing import Any, Dict, Iterable, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.pay_per_use.inference_type import InferenceType

logger = logging.getLogger(__name__)

_KEY_PREFIX = "core:inference_type"
_ALL_KEY = f"{_KEY_PREFIX}:all"
# 1 day. The catalogue is ~12 near-static rows and every mutation rebuilds
# these keys, so the TTL is not an invalidation mechanism — it is only a
# backstop so a bad write cannot become permanent (rule 3). A short TTL bought
# nothing and cost a DB round-trip plus a full rebuild every hour.
_TTL_SECONDS = 1 * 24 * 60 * 60


def _name_key(name: str) -> str:
    return f"{_KEY_PREFIX}:{name.lower()}"


def _to_hash(entry: Dict[str, Any]) -> Dict[str, str]:
    """Row dict -> hash mapping. Every value must be a string."""
    return {
        "id": str(entry["id"]),
        "name": entry["name"],
        "endpoint_patterns": json.dumps(list(entry.get("endpoint_patterns") or [])),
        "unit": entry["unit"],
        "pricing": entry["pricing"],
    }


def _from_hash(mapping: Dict[str, str]) -> Dict[str, Any]:
    """Hash mapping -> row dict, restoring the int id and the list field.

    The returned shape is identical to ``_to_dict``'s, so callers never see the
    wire encoding.
    """
    return {
        "id": int(mapping["id"]),
        "name": mapping["name"],
        "endpoint_patterns": json.loads(mapping.get("endpoint_patterns") or "[]"),
        "unit": mapping["unit"],
        "pricing": mapping["pricing"],
    }


def _to_dict(row: InferenceType) -> Dict[str, Any]:
    return {
        "id": row.id,
        "name": row.name,
        "endpoint_patterns": list(row.endpoint_patterns or []),
        "unit": row.unit,
        "pricing": row.pricing,
    }


def _get_redis():
    """Return the shared client, or None when Redis is not initialised.

    Mirrors the guard in ``_billing.get_service_pricing`` — ``get_redis_client``
    raises RuntimeError before ``init_redis`` has run (tests, CLI contexts).
    """
    try:
        from app.core.redis import get_redis_client

        return get_redis_client()
    except Exception:
        return None


async def _fetch_all(db: AsyncSession) -> List[Dict[str, Any]]:
    result = await db.execute(select(InferenceType).order_by(InferenceType.name))
    return [_to_dict(row) for row in result.scalars().all()]


async def rebuild(db: AsyncSession, *, sweep: bool = False) -> List[Dict[str, Any]]:
    """Re-read the catalogue and overwrite every cache key.

    ``sweep`` controls the keyspace scan that removes keys for types which no
    longer exist. It defaults to **False** because rebuild has two callers with
    opposite needs:

    * **Mutations** (create / update / delete) and startup warm-up pass
      ``sweep=True``. A rename or delete leaves a per-name key that would keep
      answering lookups for a type that is gone, so the scan is the only thing
      that removes it. This mirrors ``cache_service.invalidate_all_versions``,
      which likewise scans only on invalidation.
    * **Read-path misses** (``get_all`` falling through on a cold key) use the
      default. A TTL expiry or an LRU eviction leaves nothing stale to sweep —
      the keys are simply absent — so scanning ``core:inference_type:*`` across
      the whole shared Redis DB would be pure waste, and concurrent misses
      would each pay for their own scan.
    """
    rows = await _fetch_all(db)

    redis = _get_redis()
    if redis is None:
        return rows

    try:
        stale: List[str] = []
        if sweep:
            existing = [key async for key in redis.scan_iter(match=f"{_KEY_PREFIX}:*")]
            live = {_ALL_KEY} | {_name_key(r["name"]) for r in rows}
            stale = [
                k for k in existing
                if (k.decode() if isinstance(k, bytes) else k) not in live
            ]

        pipe = redis.pipeline()
        if stale:
            pipe.delete(*stale)

        # HSET merges into an existing hash rather than replacing it, so each key
        # is deleted immediately before it is rewritten. Without that, a field
        # dropped from the row shape — or a type removed from :all — would linger
        # until the TTL expired. Twelve rows, so the extra commands are free.
        #
        # There is no hash equivalent of SETEX either: HSET then EXPIRE. Losing
        # the EXPIRE would make these keys immortal and break rule 3 above.
        pipe.delete(_ALL_KEY)
        if rows:
            pipe.hset(
                _ALL_KEY,
                mapping={r["name"]: json.dumps(r, default=str) for r in rows},
            )
            pipe.expire(_ALL_KEY, _TTL_SECONDS)
        for row in rows:
            key = _name_key(row["name"])
            pipe.delete(key)
            pipe.hset(key, mapping=_to_hash(row))
            pipe.expire(key, _TTL_SECONDS)
        await pipe.execute()
    except Exception as exc:
        logger.warning("Inference type cache rebuild failed: %s", exc)

    return rows


async def get_all(db: AsyncSession) -> List[Dict[str, Any]]:
    """Every inference type. Cache first, DB fallback with re-warm."""
    redis = _get_redis()
    if redis is not None:
        try:
            mapping = await redis.hgetall(_ALL_KEY)
            if mapping:
                # Hash field order is not guaranteed, so sort explicitly. The
                # old JSON-list encoding preserved _fetch_all's ORDER BY name
                # for free; without this, GET /inference-types would return a
                # different order on every call.
                return sorted(
                    (json.loads(v) for v in mapping.values()),
                    key=lambda r: r["name"],
                )
        except Exception as exc:
            logger.warning("Inference type cache read failed for %s: %s", _ALL_KEY, exc)

    return await rebuild(db)


async def get_by_name(db: AsyncSession, name: str) -> Optional[Dict[str, Any]]:
    """One inference type by name. Cache first, DB fallback with re-warm.

    Returns None when the name is not in the catalogue.
    """
    if not name:
        return None
    normalized = name.lower()

    redis = _get_redis()
    if redis is not None:
        try:
            # A missing key returns {} — and Redis drops a hash once its last
            # field goes — so "empty means miss" needs no extra guard.
            mapping = await redis.hgetall(_name_key(normalized))
            if mapping:
                return _from_hash(mapping)
        except Exception as exc:
            logger.warning("Inference type cache read failed for %s: %s", normalized, exc)

    result = await db.execute(select(InferenceType).where(InferenceType.name == normalized))
    row = result.scalar_one_or_none()
    if row is None:
        return None

    entry = _to_dict(row)
    if redis is not None:
        try:
            key = _name_key(normalized)
            pipe = redis.pipeline()
            pipe.delete(key)
            pipe.hset(key, mapping=_to_hash(entry))
            pipe.expire(key, _TTL_SECONDS)
            await pipe.execute()
        except Exception as exc:
            logger.warning("Inference type cache re-warm failed for %s: %s", normalized, exc)
    return entry


async def get_id_by_name(db: AsyncSession, name: str) -> Optional[int]:
    """Resolve ``inference_type_id`` for a name, or None when unknown."""
    entry = await get_by_name(db, name)
    return entry["id"] if entry else None


async def get_name_by_id(db: AsyncSession) -> Dict[int, str]:
    """``{id: name}`` for the whole catalogue.

    The response edge needs to turn ids back into names: every API field stays a
    name string even though the storage and the joins are keyed by id. One
    ``get_all`` covers a whole response, so callers resolve the map once per
    request rather than per row.
    """
    return {entry["id"]: entry["name"] for entry in await get_all(db)}


async def get_ids_by_names(
    db: AsyncSession, names: Iterable[str]
) -> Dict[str, Optional[int]]:
    """``{requested name: id or None}`` for a batch of names.

    Built for comma-separated filters such as ``?task_types=a,b,c``: one
    ``get_all`` instead of N ``get_by_name`` round-trips. Keys are the caller's
    own (lowercased, trimmed) strings, so an unknown name maps to None and the
    caller can name it in the error rather than guess which one missed.
    """
    catalogue = {entry["name"]: entry["id"] for entry in await get_all(db)}
    return {
        normalized: catalogue.get(normalized)
        for normalized in (str(n).strip().lower() for n in names)
        if normalized
    }


async def get_unit_map(db: AsyncSession) -> Dict[str, str]:
    """``{name: billing unit}`` for the whole catalogue.

    Replaces ``get_inference_unit_map()``'s import-time YAML snapshot, which
    could not see a type added after the process started.
    """
    return {entry["name"]: entry["unit"] for entry in await get_all(db)}


async def get_unit_map_standalone() -> Dict[str, str]:
    """``get_unit_map`` for callers that hold no session of their own.

    ``MeteringService`` is constructed with repositories and an optional auth DB
    but no primary session, so it cannot call the session-taking variant. Opens
    one from the primary factory, the same way ``cache_warmup`` does.

    Returns ``{}`` rather than raising: an empty map makes
    ``_native_unit_suffix_for_metering_task`` fall through to
    ``SERVICE_BREAKDOWN_CONFIG``, which is the behaviour that predates PPU units
    and is correct-if-static. A metering dashboard must not 500 because the
    catalogue is briefly unreachable.
    """
    try:
        from app.core.database import get_primary_session_factory

        async with get_primary_session_factory()() as session:
            return await get_unit_map(session)
    except Exception as exc:
        logger.warning("Inference type unit map unavailable: %s", exc)
        return {}
