"""
PolicySyncService — in-memory cache of domain policies and tenant→domain
mappings, kept fresh via Redis pub/sub.

Lifecycle
---------
1. startup: call refresh(db) to populate from the database.
2. startup: call start_listener(redis) to subscribe to "policy_updates" channel.
   Any published message triggers a full refresh.
3. shutdown: call stop_listener() to cleanly cancel the background task.
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional, Set

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.pii_management.policy_repository import PolicyRepository
from app.repositories.pii_management.tenant_map_repository import TenantMapRepository

logger = logging.getLogger(__name__)

_POLICY_UPDATES_CHANNEL = "policy_updates"


class PolicySyncService:
    """
    Thread-safe (asyncio-safe) in-memory cache for domain policies.

    Attributes
    ----------
    ready : bool — True after the first successful refresh().
    """

    def __init__(self) -> None:
        self._policies: Dict[str, Any] = {}          # domain_id -> policy_json dict
        self._active_domain_ids: Set[str] = set()
        self._tenant_domain: Dict[str, str] = {}     # tenant_id -> domain_id
        self._listener_task: Optional[asyncio.Task] = None
        self.ready: bool = False

    # ── Cache access ──────────────────────────────────────────────────────

    def get_policy(self, domain_id: str) -> Optional[Dict[str, Any]]:
        return self._policies.get(domain_id)

    def list_active_domains(self) -> List[str]:
        return sorted(self._active_domain_ids)

    def resolve_domain_for_tenant(self, tenant_id: Optional[str]) -> Optional[str]:
        if not tenant_id:
            return None
        return self._tenant_domain.get(str(tenant_id).strip())

    # ── Refresh ───────────────────────────────────────────────────────────

    async def refresh(self, db: AsyncSession) -> None:
        """Reload all policies and tenant mappings from the database."""
        policy_repo = PolicyRepository(db)
        tenant_repo = TenantMapRepository(db)

        try:
            rows = await policy_repo.get_all()
            self._policies = {
                row.domain_id: row.policy_json
                for row in rows
            }
            self._active_domain_ids = {
                row.domain_id for row in rows if row.is_active
            }
            self._tenant_domain = await tenant_repo.get_all_as_dict()
            self.ready = True
            logger.info(
                "PolicySync refreshed: %d domains (%d active), %d tenant mappings",
                len(self._policies),
                len(self._active_domain_ids),
                len(self._tenant_domain),
            )
        except Exception as exc:
            logger.error("PolicySync refresh failed: %s", exc)

    # ── Redis pub/sub listener ────────────────────────────────────────────

    async def start_listener(self, redis_client, db_factory) -> None:
        """
        Subscribe to the Redis policy_updates channel and refresh on each message.

        Parameters
        ----------
        redis_client : aioredis client instance
        db_factory   : async callable that returns an AsyncSession context manager,
                       e.g. a bound version of get_pii_db
        """
        self._listener_task = asyncio.create_task(
            self._listen(redis_client, db_factory),
            name="pii_policy_sync_listener",
        )

    async def stop_listener(self) -> None:
        if self._listener_task and not self._listener_task.done():
            self._listener_task.cancel()
            try:
                await self._listener_task
            except asyncio.CancelledError:
                pass
        self._listener_task = None

    async def _listen(self, redis_client, db_factory) -> None:
        while True:
            try:
                pubsub = redis_client.pubsub()
                await pubsub.subscribe(_POLICY_UPDATES_CHANNEL)
                logger.info("PolicySync listening on Redis channel '%s'", _POLICY_UPDATES_CHANNEL)
                async for message in pubsub.listen():
                    if message.get("type") == "message":
                        logger.debug("PolicySync received update signal, refreshing…")
                        async with db_factory() as db:
                            await self.refresh(db)
            except asyncio.CancelledError:
                return
            except Exception as exc:
                logger.warning("PolicySync listener error (reconnecting in 5 s): %s", exc)
                await asyncio.sleep(5)
