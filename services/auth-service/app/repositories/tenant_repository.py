from typing import Optional
from uuid import UUID

from sqlalchemy import Text, cast, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import load_only

from app.models.tenant import Tenant, TenantStatus
from app.repositories.base import BaseRepository


class TenantRepository(BaseRepository):
    def __init__(self, db: AsyncSession) -> None:
        super().__init__(db)

    async def get_by_id(self, tenant_id: int) -> Optional[Tenant]:
        result = await self._db.execute(
            select(Tenant).where(Tenant.id == tenant_id)
        )
        return result.scalar_one_or_none()

    async def get_operational_fields(self, tenant_id: int) -> Optional[Tenant]:
        """Same row as ``get_by_id``, but ``load_only``-restricted to the
        columns APIKeyService's access/budget checks actually read: id,
        status, tier_id, allocated_budget, budget_effective_to. Every other
        caller of ``get_by_id`` (email_helpers, auth_service's login flow,
        TenantService, RoleService) genuinely needs name/organisation/email/
        phone_number too, so this is a second, narrower method rather than a
        change to ``get_by_id`` itself.

        The real cost this skips isn't the extra columns' bytes, it's the
        AES decrypt ``EncryptedEmail``/``EncryptedPhone`` run in their result
        processor on every row — paid on every one of these calls (created
        on create_api_key's hot path) even though none of them ever read
        tenant.email/phone_number.

        Still returns a full ``Tenant`` ORM instance (not a Row/tuple), so
        every existing ``tenant.status`` / ``tenant.allocated_budget`` call
        site keeps working unchanged. The columns NOT listed below are
        deferred, not omitted: touching one later would trigger a lazy
        load — which raises under AsyncSession (lazy I/O is disabled outside
        an explicit await) rather than silently running an extra query. Only
        reach for this where every attribute the caller touches is one of
        the five loaded here; add to the list rather than falling back to
        ``get_by_id`` if a caller ever needs one more.
        """
        result = await self._db.execute(
            select(Tenant)
            .options(
                load_only(
                    Tenant.id,
                    Tenant.status,
                    Tenant.tier_id,
                    Tenant.allocated_budget,
                    Tenant.budget_effective_to,
                )
            )
            .where(Tenant.id == tenant_id)
        )
        return result.scalar_one_or_none()

    async def get_by_id_for_update(self, tenant_id: int) -> Optional[Tenant]:
        """Load tenant with ``SELECT … FOR UPDATE`` (blocks concurrent status changes).

        ``populate_existing()`` — without it, a tenant already present in the
        session's identity map (e.g. an earlier unlocked ``get_by_id`` in the
        same request) is returned as-is: the lock is genuinely acquired on
        the DB row, but the in-memory attributes are NOT refreshed from it,
        so a caller reading e.g. ``allocated_budget`` off the "locked" object
        can still see a pre-revision value. This forces a refresh from the
        just-locked row every time.
        """
        result = await self._db.execute(
            select(Tenant)
            .where(Tenant.id == tenant_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        return result.scalar_one_or_none()

    async def get_by_email(self, email: str) -> Optional[Tenant]:
        # Match either storage form so the seeded/legacy plaintext default
        # tenant email keeps working alongside encrypted rows:
        #   * ``Tenant.email == email`` encrypts the parameter via the column's
        #     bind processor, matching deterministic-ciphertext rows.
        #   * ``cast(Tenant.email, Text) == <normalised>`` compares the raw
        #     stored value as plain text (bypassing the encrypting bind
        #     processor), matching un-encrypted rows.
        result = await self._db.execute(
            select(Tenant).where(
                or_(
                    Tenant.email == email,
                    cast(Tenant.email, Text) == email.strip().lower(),
                )
            )
        )
        return result.scalar_one_or_none()

    async def get_by_organisation(self, organisation: str) -> Optional[Tenant]:
        result = await self._db.execute(
            select(Tenant)
            .where(func.lower(Tenant.organisation) == organisation.lower())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def list_all(
        self,
        offset: int = 0,
        limit: int = 100,
        status: Optional[TenantStatus] = None,
    ) -> list[Tenant]:
        stmt = select(Tenant)
        if status is not None:
            stmt = stmt.where(Tenant.status == status)
        stmt = (
            stmt.order_by(func.lower(Tenant.organisation).asc(), Tenant.id.asc())
            .offset(offset)
            .limit(limit)
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def list_with_tier(self, tier_id: Optional[UUID] = None) -> list[Tenant]:
        """Tenants with a tier assigned (tier_id IS NOT NULL), optionally
        filtered to one tier — backs GET /auth/tenants/tier/list."""
        stmt = select(Tenant).where(Tenant.tier_id.isnot(None))
        if tier_id is not None:
            stmt = stmt.where(Tenant.tier_id == tier_id)
        stmt = stmt.order_by(Tenant.id.asc())
        result = await self._db.execute(stmt)
        return list(result.scalars().all())
