"""Repository for PiiType CRUD operations (async SQLAlchemy)."""
from typing import Optional, Sequence
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.orm import PiiType


class PiiTypeRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get(self, pii_type_id: UUID) -> Optional[PiiType]:
        result = await self.db.get(PiiType, pii_type_id)
        return result

    async def get_by_label(self, pii_type_label: str) -> Optional[PiiType]:
        stmt = select(PiiType).where(PiiType.pii_type_label == pii_type_label)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def list(
        self,
        search: Optional[str] = None,
        page: int = 1,
        limit: int = 20,
    ) -> tuple[Sequence[PiiType], int]:
        stmt = select(PiiType)
        if search:
            like = f"%{search}%"
            stmt = stmt.where(
                (PiiType.pii_type_label.ilike(like))
            )

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await self.db.execute(count_stmt)).scalar_one()

        stmt = stmt.offset((page - 1) * limit).limit(limit)
        rows = (await self.db.execute(stmt)).scalars().all()
        return rows, total

    async def create(self, data: dict) -> PiiType:
        obj = PiiType(**data)
        self.db.add(obj)
        await self.db.commit()
        await self.db.refresh(obj)
        return obj

    async def update(self, obj: PiiType, data: dict) -> PiiType:
        for key, value in data.items():
            setattr(obj, key, value)
        self.db.add(obj)
        await self.db.commit()
        await self.db.refresh(obj)
        return obj

    async def delete(self, obj: PiiType) -> None:
        await self.db.delete(obj)
        await self.db.commit()

    async def has_active_policy_links(self, pii_type_id: UUID) -> bool:
        from app.models.orm import PolicyPiiType, PiiPolicy
        stmt = (
            select(func.count())
            .select_from(PolicyPiiType)
            .join(PiiPolicy, PiiPolicy.policy_id == PolicyPiiType.policy_id)
            .where(
                PolicyPiiType.pii_type_id == pii_type_id,
                PiiPolicy.is_active == True,  # noqa: E712
            )
        )
        count = (await self.db.execute(stmt)).scalar_one()
        return count > 0
