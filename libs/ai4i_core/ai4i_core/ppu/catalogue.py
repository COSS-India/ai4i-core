"""Client for the ``inference_types`` catalogue.

Replaces the bundled ``inference_types.yaml``, which could only change by
publishing this package and redeploying every service that pinned it. The
catalogue now lives in platform-core's database, with a write-through Redis
cache in front of it, so an admin adding a type through ``POST /inference-types``
is visible everywhere within one TTL.

**Canonical spelling.** The ``inference_types.name`` column is authoritative:
lowercase, hyphen-separated, ``audio-lang-detection`` (not
``audio-language-detection``). This client normalises nothing beyond ``.lower()``
— the same rule platform-core's ``inference_type_cache._name_key`` applies.
Anything cleverer would paper over the naming dialects that exist elsewhere in
the stack instead of surfacing them; those keep their own explicit bridge tables.

Configure once at startup, then read from anywhere::

    configure_catalogue(redis_factory=get_redis_client)   # inference-service
    await get_catalogue().refresh()                       # warm it in lifespan
    ...
    unit_map = await get_catalogue().get_unit_map()

Providers are tried in order and each is optional — a service wires up whichever
transport it actually has:

1. **Process snapshot**, within ``ttl_seconds``. Zero I/O. This is what keeps
   auth-service's ``/auth/validate`` hot path free of a round-trip per request,
   which is what its previous ``@lru_cache`` did.
2. **Redis** ``HGETALL core:inference_type:all``. Same key, encoding and logical
   DB that payperuse_consumer already reads, so no new cross-service contract is
   invented here. Requires the service to share platform-core's Redis host *and*
   logical DB.
3. **Database**, raw SQL. This package cannot import platform-core's ORM.
4. **HTTP** ``GET /api/v1/inference-types``, un-projecting the legacy scalar
   shape back into ``endpoint_patterns``.
5. **Stale snapshot**, past its TTL, if every configured provider failed. A
   twenty-minute-old catalogue is better than a spurious 429 or a zeroed bill.
6. **Empty list**, only when there has never been a successful read.

``get_all`` never raises. Every caller inherited that from the YAML loader, which
could only fail at import, and a catalogue outage must not take inference down
with it.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

DEFAULT_KEY_PREFIX = "core:inference_type"
DEFAULT_TTL_SECONDS = 300


def to_legacy_entry(entry: Dict[str, Any]) -> Dict[str, Any]:
    """Project a catalogue row into the scalar shape the HTTP API returns.

    ``endpoint_patterns[0]`` is canonical and the rest are aliases — the same
    projection platform-core's ``inference_type_service._to_item`` performs, kept
    here so consumers that already speak that dialect need not reshape.
    """
    patterns = list(entry.get("endpoint_patterns") or [])
    return {
        "name": entry["name"],
        "endpoint_pattern": patterns[0] if patterns else "",
        "endpoint_aliases": patterns[1:],
        "unit": entry.get("unit", ""),
        "pricing": entry.get("pricing", ""),
    }


class InferenceTypeCatalogue:
    """Reads the catalogue through whichever providers it was given."""

    def __init__(
        self,
        *,
        redis_factory: Optional[Callable[[], Any]] = None,
        session_factory: Optional[Callable[[], Any]] = None,
        http_base_url: Optional[str] = None,
        http_timeout: float = 5.0,
        ttl_seconds: int = DEFAULT_TTL_SECONDS,
        key_prefix: str = DEFAULT_KEY_PREFIX,
    ) -> None:
        self._redis_factory = redis_factory
        self._session_factory = session_factory
        self._http_base_url = (http_base_url or "").rstrip("/") or None
        self._http_timeout = http_timeout
        self._ttl = ttl_seconds
        self._key_prefix = key_prefix

        self._snapshot: List[Dict[str, Any]] = []
        self._snapshot_at: float = 0.0
        self._has_loaded = False
        self._warned_at: float = 0.0
        # One refresh at a time: N concurrent misses cost one fetch, not N.
        self._lock = asyncio.Lock()

    # ── public API ──────────────────────────────────────────────────────────

    async def get_all(self) -> List[Dict[str, Any]]:
        """Every catalogue row, sorted by name. Never raises."""
        if self._has_loaded and (time.monotonic() - self._snapshot_at) < self._ttl:
            return self._snapshot
        return await self.refresh()

    async def get_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        if not name:
            return None
        normalized = name.strip().lower()
        for entry in await self.get_all():
            if entry["name"] == normalized:
                return entry
        return None

    async def get_unit_map(self) -> Dict[str, str]:
        """``{name: billing unit}``."""
        return {e["name"]: e.get("unit", "") for e in await self.get_all()}

    async def get_by_path(self, uri: str) -> Optional[Dict[str, Any]]:
        """Resolve a request path to its catalogue row, or None.

        None means "this path is not a metered inference endpoint", which is how
        callers already treat an unmatched path — so an empty catalogue degrades
        to skipping per-service quota checks, never to a spurious rejection.
        """
        if not uri:
            return None
        path = uri.split("?", 1)[0].rstrip("/")
        for entry in await self.get_all():
            for pattern in entry.get("endpoint_patterns") or []:
                if pattern.rstrip("/") == path:
                    return entry
        return None

    async def refresh(self) -> List[Dict[str, Any]]:
        """Force a re-read through the provider chain. Never raises."""
        async with self._lock:
            # A concurrent caller may have refreshed while we waited.
            if self._has_loaded and (time.monotonic() - self._snapshot_at) < self._ttl:
                return self._snapshot

            for provider in (self._from_redis, self._from_db, self._from_http):
                try:
                    rows = await provider()
                except Exception as exc:
                    logger.warning(
                        "Inference type catalogue provider %s failed: %s",
                        provider.__name__, exc,
                    )
                    continue
                if rows:
                    self._snapshot = sorted(rows, key=lambda r: r["name"])
                    self._snapshot_at = time.monotonic()
                    self._has_loaded = True
                    return self._snapshot

            return self._stale_or_empty()

    def snapshot(self) -> List[Dict[str, Any]]:
        """Last known good rows, without I/O.

        Empty until the first successful read — callers that cannot await must
        tolerate that.
        """
        return self._snapshot

    def unit_map_snapshot(self) -> Dict[str, str]:
        return {e["name"]: e.get("unit", "") for e in self._snapshot}

    # ── providers ───────────────────────────────────────────────────────────

    async def _from_redis(self) -> List[Dict[str, Any]]:
        if self._redis_factory is None:
            return []
        redis = self._redis_factory()
        if redis is None:
            return []
        mapping = await redis.hgetall(f"{self._key_prefix}:all")
        if not mapping:
            return []
        rows = []
        for value in mapping.values():
            if isinstance(value, bytes):
                value = value.decode()
            rows.append(json.loads(value))
        return rows

    async def _from_db(self) -> List[Dict[str, Any]]:
        if self._session_factory is None:
            return []
        # Imported lazily: a service configured for Redis or HTTP only should not
        # need SQLAlchemy installed to use this client.
        from sqlalchemy import text

        async with self._session_factory() as session:
            result = await session.execute(
                text(
                    "SELECT id, name, endpoint_patterns, unit, pricing"
                    "  FROM inference_types ORDER BY name"
                )
            )
            return [
                {
                    "id": row.id,
                    "name": row.name,
                    "endpoint_patterns": list(row.endpoint_patterns or []),
                    "unit": row.unit,
                    "pricing": row.pricing,
                }
                for row in result.all()
            ]

    async def _from_http(self) -> List[Dict[str, Any]]:
        if self._http_base_url is None:
            return []
        import httpx

        url = f"{self._http_base_url}/api/v1/inference-types"
        async with httpx.AsyncClient(timeout=self._http_timeout) as client:
            response = await client.get(url)
            response.raise_for_status()
            payload = response.json()

        items = (payload.get("data") or {}).get("inference_types") or []
        rows = []
        for item in items:
            # The wire shape is the legacy scalar projection; rebuild the array.
            patterns = [item["endpoint_pattern"]] if item.get("endpoint_pattern") else []
            patterns += list(item.get("endpoint_aliases") or [])
            rows.append(
                {
                    "id": item.get("id"),
                    "name": item["name"],
                    "endpoint_patterns": patterns,
                    "unit": item.get("unit", ""),
                    "pricing": item.get("pricing", ""),
                }
            )
        return rows

    # ── fallback ────────────────────────────────────────────────────────────

    def _stale_or_empty(self) -> List[Dict[str, Any]]:
        now = time.monotonic()
        if self._has_loaded:
            # Warn once per TTL window rather than once per call: this path is
            # hit on every request while the outage lasts.
            if now - self._warned_at >= self._ttl:
                self._warned_at = now
                logger.warning(
                    "Inference type catalogue unreachable; serving a snapshot %.0fs old",
                    now - self._snapshot_at,
                )
            return self._snapshot

        if now - self._warned_at >= self._ttl:
            self._warned_at = now
            logger.error(
                "Inference type catalogue unreachable and never loaded — "
                "returning an empty catalogue"
            )
        return []


_catalogue: Optional[InferenceTypeCatalogue] = None


def configure_catalogue(**kwargs: Any) -> InferenceTypeCatalogue:
    """Install the process-wide catalogue. Call once, at startup."""
    global _catalogue
    _catalogue = InferenceTypeCatalogue(**kwargs)
    return _catalogue


def get_catalogue() -> InferenceTypeCatalogue:
    """The process-wide catalogue.

    Returns an unconfigured instance rather than raising if ``configure_catalogue``
    was never called — that one degrades to an empty catalogue, which every
    caller already handles, instead of turning a wiring mistake into a crash on
    the request path.
    """
    global _catalogue
    if _catalogue is None:
        logger.warning(
            "Inference type catalogue used before configure_catalogue(); "
            "no providers are wired, so it will read empty"
        )
        _catalogue = InferenceTypeCatalogue()
    return _catalogue
