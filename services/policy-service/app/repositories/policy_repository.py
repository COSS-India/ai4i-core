"""Repository for PiiPolicy CRUD and PII-type link operations (async SQLAlchemy)."""
from typing import Optional, Sequence
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.orm import PiiPolicy, PolicyPiiType


class PolicyRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get(self, policy_id: UUID) -> Optional[PiiPolicy]:
        return await self.db.get(PiiPolicy, policy_id)

    async def get_with_pii_types(self, policy_id: UUID) -> Optional[PiiPolicy]:
        stmt = (
            select(PiiPolicy)
            .options(selectinload(PiiPolicy.pii_types).selectinload(PolicyPiiType.pii_type))
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
            selectinload(PiiPolicy.pii_types).selectinload(PolicyPiiType.pii_type)
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

    async def create(self, data: dict) -> PiiPolicy:
        obj = PiiPolicy(**data)
        self.db.add(obj)
        await self.db.commit()
        await self.db.refresh(obj)
        return obj

    async def update(self, obj: PiiPolicy, data: dict) -> PiiPolicy:
        for key, value in data.items():
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
        for link in links:
            self.db.add(PolicyPiiType(policy_id=policy_id, **link))
        await self.db.commit()

    async def remove_pii_type_link(self, policy_id: UUID, pii_type_id: UUID) -> bool:
        link = await self.get_link(policy_id, pii_type_id)
        if not link:
            return False
        await self.db.delete(link)
        await self.db.commit()
        return True
