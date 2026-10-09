"""Repository for the policy table."""

from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.policy_management.policy import Policy


_ID_PREFIX = "PID-"


class PolicyRepository:
    """CRUD for policy."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get_all(
        self,
        name: Optional[str] = None,
        sub_category_id: Optional[int] = None,
        offset: int = 0,
        limit: int = 100,
    ) -> Tuple[List[Policy], int]:
        base = select(Policy)
        if name is not None:
            base = base.where(Policy.name.ilike(f"%{name}%"))
        if sub_category_id is not None:
            base = base.where(Policy.sub_category_id == sub_category_id)

        total_result = await self._db.execute(select(func.count()).select_from(base.subquery()))
        total = total_result.scalar_one()

        rows_result = await self._db.execute(base.order_by(Policy.id).offset(offset).limit(limit))
        return list(rows_result.scalars().all()), total

    async def get_by_id(self, policy_id: int) -> Optional[Policy]:
        result = await self._db.execute(select(Policy).where(Policy.id == policy_id))
        return result.scalar_one_or_none()

    async def get_by_name(self, name: str) -> Optional[Policy]:
        result = await self._db.execute(
            select(Policy).where(func.lower(Policy.name) == name.lower())
        )
        return result.scalar_one_or_none()

    async def get_next_policy_id(self) -> str:
        """Generate the next SPP-XXXX identifier by reading the current max."""
        from sqlalchemy import text
        result = await self._db.execute(
            text(
                "SELECT MAX(CAST(SUBSTRING(policy_id FROM 5) AS INTEGER)) "
                "FROM policy WHERE policy_id ~ '^PID-[0-9]+$'"
            )
        )
        last_num = result.scalar() or 0
        return f"{_ID_PREFIX}{last_num + 1:04d}"

    async def create(self, data: Dict[str, Any]) -> Policy:
        row = Policy(**data)
        self._db.add(row)
        await self._db.commit()
        await self._db.refresh(row)
        return row

    async def update(self, policy_id: int, data: Dict[str, Any]) -> Optional[Policy]:
        await self._db.execute(
            update(Policy).where(Policy.id == policy_id).values(**data)
        )
        await self._db.commit()
        return await self.get_by_id(policy_id)

    async def delete(self, policy_id: int) -> bool:
        result = await self._db.execute(
            delete(Policy).where(Policy.id == policy_id)
        )
        await self._db.commit()
        return result.rowcount > 0
