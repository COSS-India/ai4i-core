from __future__ import annotations

"""Repository for PiiPolicy CRUD and PII-type link operations (async SQLAlchemy)."""
from collections import defaultdict
from typing import Optional, Sequence
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.orm import PiiPolicy, PolicyPiiType, TenantPolicy


class PolicyRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    # Fields that are safe to update via repository update methods.
    # NOTE: Keep this tight to prevent mass-assignment of protected columns
    # (e.g. ids, timestamps) if upstream layers accidentally pass unfiltered input.
    _UPDATABLE_FIELDS: set[str] = {
        "name",
        "description",
        "is_active",
        "is_global",
        "supported_languages",
    }

    async def get(self, policy_id: UUID) -> Optional[PiiPolicy]:
        return await self.db.get(PiiPolicy, policy_id)

    async def get_with_pii_types(self, policy_id: UUID) -> Optional[PiiPolicy]:
        stmt = (
            select(PiiPolicy)
            .options(selectinload(PiiPolicy.pii_types).selectinload(PolicyPiiType.pii_type))
            .options(selectinload(PiiPolicy.tenant_policies))
            .where(PiiPolicy.policy_id == policy_id)
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_name(self, name: str) -> Optional[PiiPolicy]:
        result = await self.db.execute(select(PiiPolicy).where(PiiPolicy.name == name))
        return result.scalar_one_or_none()

    async def list(
        self,
        is_global: Optional[bool] = None,
        is_active: Optional[bool] = None,
        search: Optional[str] = None,
        page: int = 1,
        limit: int = 20,
    ) -> tuple[Sequence[PiiPolicy], int]:
        # Eager-load pii_types to avoid async lazy-load (MissingGreenlet) in route serialization/counting.
        stmt = select(PiiPolicy).options(
            selectinload(PiiPolicy.pii_types).selectinload(PolicyPiiType.pii_type),
        )
        if is_global is not None:
            stmt = stmt.where(PiiPolicy.is_global == is_global)
        if is_active is not None:
            stmt = stmt.where(PiiPolicy.is_active == is_active)
        if search:
            stmt = stmt.where(PiiPolicy.name.ilike(f"%{search}%"))

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await self.db.execute(count_stmt)).scalar_one()

        stmt = stmt.offset((page - 1) * limit).limit(limit)
        rows = (await self.db.execute(stmt)).scalars().all()
        return rows, total

    async def list_tenant_ids_for_policies(self, policy_ids: Sequence[UUID]) -> dict[UUID, list[str]]:
        if not policy_ids:
            return {}
        stmt = select(TenantPolicy.policy_id, TenantPolicy.tenant_id).where(
            TenantPolicy.policy_id.in_(policy_ids)
        )
        rows = (await self.db.execute(stmt)).all()
        out: dict[UUID, list[str]] = defaultdict(list)
        for policy_id, tenant_id in rows:
            if tenant_id:
                out[policy_id].append(tenant_id)
        return dict(out)

    async def create(self, data: dict) -> PiiPolicy:
        obj = PiiPolicy(**data)
        self.db.add(obj)
        await self.db.commit()
        await self.db.refresh(obj)
        return obj

    async def update(self, obj: PiiPolicy, data: dict) -> PiiPolicy:
        for key, value in data.items():
            if key in self._UPDATABLE_FIELDS and hasattr(obj, key):
                setattr(obj, key, value)
        self.db.add(obj)
        await self.db.commit()
        await self.db.refresh(obj)
        return obj

    async def delete(self, obj: PiiPolicy) -> None:
        await self.db.delete(obj)
        await self.db.commit()

    # ── PII type links ────────────────────────────────────────────────────────

    async def get_link(self, policy_id: UUID, pii_type_id: UUID) -> Optional[PolicyPiiType]:
        stmt = select(PolicyPiiType).where(
            PolicyPiiType.policy_id == policy_id,
            PolicyPiiType.pii_type_id == pii_type_id,
        )
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def add_pii_type_links(self, policy_id: UUID, links: Sequence[dict]) -> None:
        for link in links:
            existing = await self.get_link(policy_id, link["pii_type_id"])
            if existing:
                # Link already exists; nothing else to update
                pass
            else:
                self.db.add(PolicyPiiType(policy_id=policy_id, **link))
        await self.db.commit()

    async def replace_pii_type_links(self, policy_id: UUID, links: Sequence[dict]) -> None:
        stmt = select(PolicyPiiType).where(PolicyPiiType.policy_id == policy_id)
        existing = (await self.db.execute(stmt)).scalars().all()
        for row in existing:
            await self.db.delete(row)
        # Ensure deletes are flushed before we insert the replacement set; otherwise
        # PostgreSQL can raise uq_policy_pii_type conflicts during the same commit.
        await self.db.flush()

        # De-dupe incoming links by pii_type_id to avoid violating uq_policy_pii_type
        seen: set[UUID] = set()
        deduped: list[dict] = []
        for link in links:
            pid = link.get("pii_type_id")
            if pid and pid not in seen:
                seen.add(pid)
                deduped.append(link)

        try:
            for link in deduped:
                self.db.add(PolicyPiiType(policy_id=policy_id, **link))
            await self.db.commit()
        except IntegrityError:
            await self.db.rollback()
            # Let service layer decide the HTTP response; avoid leaking DB stacktraces as 500s.
            raise

    async def remove_pii_type_link(self, policy_id: UUID, pii_type_id: UUID) -> bool:
        link = await self.get_link(policy_id, pii_type_id)
        if not link:
            return False
        await self.db.delete(link)
        await self.db.commit()
        return True
