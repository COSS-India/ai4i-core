"""Write-through Redis cache for per-user column preferences.

Keys (``core:`` is platform-core's namespace — see ``app/services/cache_service.py``).
One Redis **hash** per user; any later per-user preference adds a field to it
rather than a new key::

    core:user:<user_id>:prefs   HASH  columns:<view_key> -> JSON list of stored ids, or "null"

``"null"`` caches "nothing saved", so users who never customise their columns
don't reach the DB on every page load either::

    redis-cli HGETALL core:user:<user_id>:prefs

The raw stored ids are cached, not the response: role filtering still runs on
every read, so a role change applies at once.

Rules:

1. **DB commit first, cache second.** The DB is the source of truth; a Redis
   error is logged (exception type only), never raised. Reads fall back to the DB.
2. **TTL even though this is write-through.** It bounds how long a bad entry can
   last and lets idle users' keys expire; every write refreshes it.
3. **A failed write deletes the field** (best effort), so an old value isn't served.
"""

import json
import logging
from typing import List

logger = logging.getLogger(__name__)

_TTL_SECONDS = 24 * 60 * 60


class _Miss:
    def __repr__(self) -> str:
        return "MISS"


# Not cached — distinct from a cached "nothing saved" (None).
MISS = _Miss()


def _key(user_id: str) -> str:
    return f"core:user:{user_id}:prefs"


def _field(view_key: str) -> str:
    return f"columns:{view_key}"


def _get_redis():
    """Return the shared client, or None when Redis is not initialised.

    Mirrors ``inference_type_cache._get_redis`` — ``get_redis_client`` raises
    RuntimeError before ``init_redis`` has run (tests, CLI contexts).
    """
    try:
        from app.core.redis import get_redis_client

        return get_redis_client()
    except Exception:
        return None


async def get_columns(user_id: str, view_key: str) -> List[str] | None | _Miss:
    """Cached column ids, None for a cached "nothing saved", or MISS."""
    redis = _get_redis()
    if redis is None:
        return MISS
    try:
        raw = await redis.hget(_key(user_id), _field(view_key))
        return MISS if raw is None else json.loads(raw)
    except Exception as exc:
        logger.warning("Column preference cache read failed: %s", type(exc).__name__)
        return MISS


async def set_columns(user_id: str, view_key: str, columns: List[str] | None) -> None:
    """Cache the stored column ids (None for "nothing saved")."""
    redis = _get_redis()
    if redis is None:
        return
    key, field = _key(user_id), _field(view_key)
    try:
        pipe = redis.pipeline()
        pipe.hset(key, field, json.dumps(columns))
        pipe.expire(key, _TTL_SECONDS)
        await pipe.execute()
    except Exception as exc:
        logger.warning("Column preference cache write failed: %s", type(exc).__name__)
        try:
            await redis.hdel(key, field)
        except Exception as del_exc:
            logger.warning("Column preference cache delete failed: %s", type(del_exc).__name__)
